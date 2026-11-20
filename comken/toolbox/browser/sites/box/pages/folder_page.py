"""comken/toolbox/browser/sites/box/pages/folder_page.py — Box のフォルダ画面。

Box のファイル一覧は遅延読み込み（末尾までスクロールすると次のページが
読み込まれる）なので、``items()`` は末尾までスクロールして件数が増えなくなる
まで読んでから返す。

セレクターは実機未確認の推測。実機（F12）で確かめた値へ書き換えること。
各定数のコメントに「根拠」（参照したファイル・URL）を書いてあるので、
根拠が無いものは ``# 未確認: 推測`` と書いてある。
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import urlsplit

from selenium.webdriver.remote.webelement import WebElement

from comken.exceptions import BrowserError
from comken.toolbox.browser import Locator
from comken.toolbox.browser.sites.box.pages.app_page import AppPage

logger = logging.getLogger(__name__)

# 項目の種類。ファイルかフォルダのどちらか
BoxItemKind = Literal["file", "folder"]


def _item_not_found_error(name: str) -> BrowserError:
    """``BrowserError`` の「その名前の項目が見つからない」文言。"""
    return BrowserError(
        f"フォルダ内に「{name}」が見つかりません。\n"
        "次を確認してください:\n"
        "  1. 名前が大文字小文字・全角半角も含めて一致しているか\n"
        "  2. 開いているフォルダが正しいか（go_folder() の folder_id）\n"
        "  3. 一覧の読み込みが遅くて、まだ表示されていないだけではないか\n"
        "\n対処: 名前か folder_id を確認してから、もう一度実行してください。"
    )


def _duplicate_name_error(name: str, count: int) -> BrowserError:
    """``BrowserError`` の「同じ名前の項目が複数ある」文言。"""
    return BrowserError(
        f"フォルダ内に「{name}」が {count} 件あります。"
        "どれを指すか決められないため、処理を止めます。\n"
        "次を確認してください:\n"
        "  1. 本当に同じ名前のファイル／フォルダが複数あるか\n"
        "  2. 別のフォルダを見ていないか（go_folder() の folder_id）\n"
        "\n対処: フォルダを整理するか、項目の ID（BoxItem.id）を見て個別に操作してください。"
    )


def _not_a_file_error(name: str) -> BrowserError:
    """``BrowserError`` の「その項目はファイルではない」文言。"""
    return BrowserError(
        f"「{name}」はファイルではありません（フォルダです）。\n"
        "ダウンロードはファイルにだけできます。\n"
        "\n対処: ダウンロードしたいファイルの名前を確認してください。"
    )


def _not_a_folder_error(name: str) -> BrowserError:
    """``BrowserError`` の「その項目はフォルダではない」文言。"""
    return BrowserError(
        f"「{name}」はフォルダではありません（ファイルです）。\n"
        "フォルダを開く操作はフォルダにだけできます。\n"
        "\n対処: 開きたいフォルダの名前を確認してください。"
    )


def _same_name_file_error(name: str) -> BrowserError:
    """``BrowserError`` の「同名のファイルが既にあってフォルダを作れない」文言。"""
    return BrowserError(
        f"「{name}」という名前のファイルが既に存在します。\n"
        "既存ファイルと同じ名前のフォルダは作りません（どちらを使うか決められないため）。\n"
        "次を確認してください:\n"
        "  1. 作りたいフォルダの名前が既存ファイルと違っているか\n"
        "  2. 既存ファイルをゴミ箱へ入れてから作り直したいか\n"
        "\n対処: 別の名前で作り直すか、既存ファイルを削除してから実行してください。"
    )


def _upload_source_not_found_error(path: Path) -> BrowserError:
    """``BrowserError`` の「アップロードするファイルが無い」文言。"""
    return BrowserError(
        f"アップロードするファイルが見つかりません: {path}\n"
        "次を確認してください:\n"
        "  1. パスが正しいか（相対パスは実行中の作業フォルダからの相対）\n"
        "  2. ファイルが別のPC・共有フォルダ側に無いか\n"
        "\n対処: パスを確認してから、もう一度実行してください。"
    )


def _item_not_appeared_error(name: str, timeout: float) -> BrowserError:
    """``BrowserError`` の「操作した項目が一覧に現れない」文言。"""
    return BrowserError(
        f"「{name}」が一覧に現れませんでした（{timeout:.0f} 秒待ちました）。\n"
        "次を確認してください:\n"
        "  1. Box 側の処理が途中で止まっていないか（容量・権限・同名ファイル）\n"
        "  2. 操作したフォルダが今開いているフォルダと同じか\n"
        "\n対処: もう一度実行してください。"
    )


def _row_not_found_error(name: str) -> BrowserError:
    """``BrowserError`` の「その項目の行が見つからない」文言。"""
    return BrowserError(
        f"「{name}」の行が見つかりません。\n"
        "次を確認してください:\n"
        "  1. 一覧が読み込み直中で、行がまだ描画されていないだけではないか\n"
        "  2. 一覧の表示方法（表・タイル）が変わっただけではないか\n"
        "\n対処: もう一度実行してください。"
    )


# 項目リンクの href から id と種類を取り出す正規表現。
# Box の項目 URL は /file/{id} と /folder/{id}（id は数字）。
# /files/0 のように数えられない部分や /folder/ だけのものは拾わない
_ITEM_HREF_PATTERN = re.compile(r"/(?P<kind>file|folder)/(?P<id>\d+)(?:[/?#]|$)")

# 読み込み・出現待ちの合間に状態を確かめる間隔（秒）
_POLL_INTERVAL_SECONDS = 0.5

# 遅延読み込みが落ち着いたとみなす連続回数
_LOAD_STABLE_CHECKS = 2

# 操作した項目が一覧に現れるまでの待ち時間（秒）
_ITEM_APPEAR_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class BoxItem:
    """Box 上の 1 つのファイル／フォルダ。

    Attributes:
        id: Box が振り付けた ID。リンクの href（/file/{id} / /folder/{id}）から取る。
        name: 表示されている名前。
        kind: ファイルかフォルダか。
    """

    id: str
    name: str
    kind: BoxItemKind


class FolderPage(AppPage):
    """Box のフォルダ画面（/folder/{id}）。

    一覧の中身を読む操作（``items`` / ``find``）と、
    ファイル・フォルダに対する操作（``upload`` / ``create_folder`` /
    ``download`` / ``delete`` / ``open_folder``）を持つ。
    """

    PATH = "/folder"

    # ── セレクター ──
    # 一覧の1行。行の中に「名前へのリンク」と「削除ボタン」がある
    # 根拠: https://github.com/veerDS/automation_test_jenkins の
    # BoxAppHomePage.java（``By.xpath("//div[@data-item-index='0']")`` で
    # 行を掴み、``data-resin-folder_id`` 属性で ID を取り出している）。
    # 表示方法（表・タイル）ごとに class 名が変わると壊れるため、
    # class ではなく属性で指定している。
    ROWS = Locator.css("div[data-item-index]")

    # 行の中の項目リンク。ファイルとフォルダで href の形が変わる
    # 根拠: https://github.com/bhandigare/UIAutomation の
    # src/main/java/.../pageObjects/HomePage.java
    # （``@FindBy(css = "a.item-link")``）と
    # https://github.com/robertdavidgraham/box-scrape の get-urls.js
    # （``document.querySelectorAll('a.item-link')``）。
    # 2 つの独立した事例が同じ class を使っている。
    # class 名は Box が変更することがあるため、href の形でも拾えるように
    # なぞっている（行の中で使うので、サイドバーの /folder/0 とは混ざらない）。
    ITEM_LINK = Locator.css("a.item-link, a[href*='/file/'], a[href*='/folder/']")

    # 行の「…」メニューから trash へ移すボタン
    # 依頼では「行の「…」メニュー → 削除 → 確認」の順だが、公開資料から
    # 確認できるのは行に直接出ている trash ボタンの方なので、そちらを掴む
    # （「…」メニューを開く手順にするなら、ここを行の「…」ボタンに
    # 差し替えて、メニュー内の削除項目を押す形に直す）。
    # 根拠: https://github.com/veerDS/automation_test_jenkins の
    # BoxAppHomePage.java（``By.xpath("//button[@data-resin-target='trash']")``）。
    # 表示文字列ではなく data-resin-target なので UI の言語に依存しない。
    ROW_TRASH_BTN = Locator.css("button[data-resin-target='trash']")

    # 「新規 +」ボタン（アップロード・新規フォルダのメニューを開く）
    # 根拠: https://github.com/bhandigare/UIAutomation の HomePage.java
    # （``@FindBy(css="button.create-dropdown-menu-toggle-button")``）と
    # https://github.com/veerDS/automation_test_jenkins の BoxAppHomePage.java
    # （``button.create-dropdown-menu-toggle-button:not([aria-disabled])``）。
    NEW_BTN = Locator.css("button.create-dropdown-menu-toggle-button")

    # メニューの中の「新規フォルダ」
    # 根拠: https://github.com/bhandigare/UIAutomation の HomePage.java と
    # https://github.com/veerDS/automation_test_jenkins の BoxAppHomePage.java
    # の ``//li[@aria-label='Create a new Folder']``。
    # aria-label は UI の言語で変わるため、英語のときの表示文字列
    # （"New Folder"）と日本語のときの表示文字列（"新規フォルダ"）の
    # どちらでも当たるようにしている。日本語の aria-label は未確認。
    NEW_FOLDER_MENU_ITEM = Locator.xpath(
        "//li[@role='menuitem']"
        "[contains(@aria-label, 'Create a new Folder')"
        " or contains(@aria-label, '新しいフォルダ')"
        " or contains(., 'New Folder') or contains(., '新規フォルダ')]"
    )

    # フォルダ名を入力する欄
    # 根拠: https://github.com/bhandigare/UIAutomation の
    # src/main/java/.../pageObjects/NewFolderPage.java
    # （``@FindBy(css = "input[name='folder-name']")``）と
    # veerDS/automation_test_jenkins の ``//input[@name='folder-name']``。
    FOLDER_NAME_INPUT = Locator.css("input[name='folder-name']")

    # 「作成」ボタン（ダイアログの主ボタン）
    # 根拠: https://github.com/bhandigare/UIAutomation の NewFolderPage.java と
    # veerDS/automation_test_jenkins の
    # ``//button[@data-resin-target='primarybutton']``。
    CREATE_FOLDER_BTN = Locator.css("button[data-resin-target='primarybutton']")

    # アップロードするファイルを選ぶ入力欄
    # 根拠: https://github.com/bhandigare/UIAutomation の HomePage.java
    # （``driver.findElement(By.cssSelector("input[type='file']")).sendKeys(...)``）。
    # ファイル選択ダイアログは開かずに、この要素へ直接パスを送る。
    FILE_INPUT = Locator.css("input[type='file']")

    # メニューの中の「ファイルをアップロード」
    # 根拠: https://github.com/JanSteinhauer/UTBoxUpload の index.js
    # （``await page.click('.menu-item.UploadMenuItem')``）と
    # https://github.com/bhandigare/UIAutomation の HomePage.java
    # （``@FindBy(css = "li.UploadMenuItem:nth-child(1)")``）。
    # 別の入口の uploading ボタン
    # （``[data-resin-target="uploadmenubutton"]``、JanSteinhauer/UTBoxUpload）
    # を使う画面なら、ここをそのボタンに差し替える。
    UPLOAD_MENU_ITEM = Locator.css("li.UploadMenuItem")

    # 同名ファイルがあるときの確認ダイアログの
    # 「新しいバージョンとしてアップロード」
    # 根拠: ボタンの表示文字列は Box の公式ヘルプで裏付けが取れている
    # （英語 "Upload New Version"、日本語「新しいバージョンをアップロード」:
    # https://docs.box.com/ja/box-fundamentals/for-users/getting-started/collaborate-on-files
    # ）。ダイアログの DOM 構造は公開資料から確認できなかったため、
    # 要素の属性ではなく表示文字列で拾っている（英語と日本語の両方）。
    UPLOAD_NEW_VERSION_BTN = Locator.xpath(
        "//button[contains(., 'Upload New Version') or contains(., '新しいバージョン')]"
    )

    # 削除確認ダイアログの「削除」（ゴミ箱へ移す）
    # 根拠: https://github.com/bhandigare/UIAutomation の HomePage.java
    # （``@FindBy(css = "button[data-resin-target='primarybutton']")``
    # が削除確認の OK ボタン）と
    # veerDS/automation_test_jenkins の ``//button[@data-resin-target='primarybutton']``。
    CONFIRM_DELETE_BTN = Locator.css("button[data-resin-target='primarybutton']")

    def items(self) -> list[BoxItem]:
        """表示中のフォルダの中身（読み込みが終わるまで読み切った分）を返す。

        Box のファイル一覧は遅延読み込み（末尾までスクロールすると次の
        ページが読み込まれる）ので、末尾までスクロールして件数が増えなく
        なるまで読んでから返す。

        Returns:
            フォルダ内の項目。ファイルもフォルダも ``BoxItem`` で返す。
        """
        self._load_all_items()
        return self._read_items()

    def find(self, name: str) -> BoxItem | None:
        """名前が完全一致する項目を返す。見つからなければ ``None``。

        同じ名前が複数あるとどれを指すか決められないため、エラーにする。

        Args:
            name: 完全一致で探す名前。

        Raises:
            BrowserError: 同じ名前の項目が複数ある場合。
        """
        matched = [item for item in self.items() if item.name == name]
        if len(matched) > 1:
            raise _duplicate_name_error(name, len(matched))
        if not matched:
            return None
        return matched[0]

    def upload(self, path: Path) -> BoxItem:
        """ファイルをアップロードして、アップロードした項目を返す。

        同名のファイルが既にあれば、確認ダイアログで「新しいバージョンとして
        アップロード」を選ぶ（旧版は Box の版履歴に残り、完全に置き換わる）。
        ファイル選択ダイアログは開かない（ページの中の
        ``input[type=file]`` へ直接パスを送る）。

        Args:
            path: アップロードするローカルファイルのパス。

        Returns:
            アップロード後の項目。

        Raises:
            BrowserError: ファイルが見つからない場合、一覧に現れない場合。
        """
        if not path.is_file():
            raise _upload_source_not_found_error(path)

        # 同名のファイルが既にあるかを先に確かめる（確認ダイアログを出すか
        # どうかの判断に使う）
        existing = self.find(path.name)
        self._open_upload_dialog()

        file_input = self.find_element(self.FILE_INPUT)
        file_input.send_keys(str(path.resolve()))

        if existing is not None and existing.kind == "file":
            # 旧版を残したまま差し替える
            self.wait_visible(self.UPLOAD_NEW_VERSION_BTN)
            self.click(self.UPLOAD_NEW_VERSION_BTN)

        return self._wait_for_item(path.name)

    def create_folder(self, name: str) -> BoxItem:
        """フォルダを作る。既に同じ名前のフォルダがあればそれを返す。

        何度呼んでも同じ結果になる（既にあれば、作成操作はしない）。

        Args:
            name: フォルダ名。

        Returns:
            できたフォルダ（既にあった場合は既存のフォルダ）。

        Raises:
            BrowserError: 同名のファイルが既に存在する場合。
        """
        existing = self.find(name)
        if existing is not None:
            if existing.kind != "folder":
                raise _same_name_file_error(name)
            return existing

        self.click(self.NEW_BTN)
        self.click(self.NEW_FOLDER_MENU_ITEM)
        self.input(self.FOLDER_NAME_INPUT, name)
        self.click(self.CREATE_FOLDER_BTN)
        return self._wait_for_item(name)

    def download(self, name: str) -> Path:
        """ファイルをダウンロードし、保存されたファイルのパスを返す。

        Args:
            name: ダウンロードするファイルの名前。

        Returns:
            ダウンロード先（セッションのダウンロードフォルダ）に保存されたパス。

        Raises:
            BrowserError: ファイルが見つからない場合、フォルダだった場合、
                ダウンロードが終わる前に時間切れになった場合。
        """
        item = self.find(name)
        if item is None:
            raise _item_not_found_error(name)
        if item.kind != "file":
            raise _not_a_file_error(name)

        from comken.toolbox.browser.sites.box.pages.file_page import FilePage

        return self.to(FilePage).go(f"/file/{item.id}").download()

    def delete(self, name: str) -> None:
        """その項目をゴミ箱へ移す（完全削除はしない）。

        行にある trash ボタン（Box の「…」メニューに当たる操作）を押し、
        確認ダイアログでも trash へ移す方を選ぶ。Box 側はゴミ箱へ移すだけ
        なので、誤操作しても元に戻せる。

        Args:
            name: ゴミ箱へ移す項目の名前。

        Raises:
            BrowserError: 項目が見つからない場合。
        """
        item = self.find(name)
        if item is None:
            raise _item_not_found_error(name)

        self._open_item_menu(item)
        self.click(self.CONFIRM_DELETE_BTN)

    def open_folder(self, name: str) -> FolderPage:
        """子フォルダの画面へ移る。

        Args:
            name: 開くフォルダの名前。

        Returns:
            開いたフォルダの画面。

        Raises:
            BrowserError: フォルダが見つからない場合、ファイルだった場合。
        """
        item = self.find(name)
        if item is None:
            raise _item_not_found_error(name)
        if item.kind != "folder":
            raise _not_a_folder_error(name)
        return self.to(FolderPage).go(f"/folder/{item.id}")

    def _load_all_items(self) -> None:
        """遅延読み込みで増える項目がなくなるまで、末尾までスクロールする。"""
        previous_count = -1
        stable_count = 0
        while stable_count < _LOAD_STABLE_CHECKS:
            count = self.count_elements(self.ROWS)
            if count == previous_count:
                stable_count += 1
            else:
                stable_count = 0
                previous_count = count
            if stable_count < _LOAD_STABLE_CHECKS:
                self.scroll_bottom()
                time.sleep(_POLL_INTERVAL_SECONDS)

    def _read_items(self) -> list[BoxItem]:
        """画面に出ている項目を読み取る（スクロールはしない）。"""
        if self.count_elements(self.ROWS) == 0:
            return []
        result = []
        for row in self.find_elements(self.ROWS):
            for link in row.find_elements(*self.ITEM_LINK):
                parsed = _parse_item_href(link.get_attribute("href") or "")
                if parsed is None:
                    # Box の項目では無いリンク（共有リンク等）は無視する
                    continue
                item_id, kind = parsed
                result.append(BoxItem(id=item_id, name=link.text.strip(), kind=kind))
        return result

    def _find_row(self, item: BoxItem) -> WebElement:
        """指定の項目の行を返す。"""
        for row in self.find_elements(self.ROWS):
            for link in row.find_elements(*self.ITEM_LINK):
                parsed = _parse_item_href(link.get_attribute("href") or "")
                if parsed is not None and parsed[0] == item.id:
                    return row
        raise _row_not_found_error(item.name)

    def _open_item_menu(self, item: BoxItem) -> None:
        """項目の行にある trash への操作を出す（行の「…」メニュー）。"""
        row = self._find_row(item)
        row.find_element(*self.ROW_TRASH_BTN).click()

    def _open_upload_dialog(self) -> None:
        """アップロード用のファイル入力欄を出す（既にあれば何もしない）。"""
        if self.has_element(self.FILE_INPUT):
            return
        self.click(self.NEW_BTN)
        self.click(self.UPLOAD_MENU_ITEM)

    def _wait_for_item(
        self,
        name: str,
        timeout: float = _ITEM_APPEAR_TIMEOUT_SECONDS,
    ) -> BoxItem:
        """指定の名前が一覧に現れるまで待って、項目を返す。"""
        deadline = time.monotonic() + timeout
        while True:
            for item in self._read_items():
                if item.name == name:
                    return item
            if time.monotonic() >= deadline:
                raise _item_not_appeared_error(name, timeout)
            time.sleep(_POLL_INTERVAL_SECONDS)


def _parse_item_href(href: str) -> tuple[str, BoxItemKind] | None:
    """リンクの href から Box の項目（id と種類）を取り出す。

    項目リンクでなければ ``None`` を返す（Box の項目では無いリンクを
    無視するために使う）。

    Args:
        href: リンクの href。相対でも絶対でもよい。

    Returns:
        ``(id, 種類)``。項目リンクでなければ ``None``。
    """
    parts = urlsplit(href)
    for candidate in (parts.path, parts.fragment):
        match = _ITEM_HREF_PATTERN.search(candidate)
        if match is None:
            continue
        return match.group("id"), cast(BoxItemKind, match.group("kind"))
    return None
