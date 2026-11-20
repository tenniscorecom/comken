"""認証情報の登録画面（GUI）のテスト。

入力値を検証する純粋関数と、画面が組み立てられること（一覧の選択・値の表示が
望みどおりに動くこと）を確認する。
保存先は tmp_path へ逃がし、実際に登録済みの認証情報には触らない。
"""

import time
import tkinter as tk

import pytest

from comken.toolbox.credentials.gui import _MASK_CHARACTER, build_credential_name

# 画面を作り直すときの待ち秒数と回数。
_TK_RETRY_SECONDS = 0.2
_TK_RETRY_COUNT = 3


def _make_root() -> tk.Tk:
    """画面を用意する（画面には出さない）。

    1 つ目のウィンドウを破棄した直後に 2 つ目を作ると、 Tcl 側の初期化に失敗する
    ことがある（invalid command name "tcl_findLibrary"）。 何度か作り直せば必ず
    成功するので、 失敗したときは作り直す。
    """
    for _ in range(_TK_RETRY_COUNT):
        try:
            root = tk.Tk()
        except tk.TclError:
            time.sleep(_TK_RETRY_SECONDS)
            continue
        root.withdraw()  # 画面には出さない
        return root
    pytest.skip("画面のない環境では GUI を起動できない")


class TestBuildCredentialName:
    """フォームの入力を検証して、 ``(サイト名, 項目名)`` を組み立てる。"""

    def test_builds_pair(self):
        pair, error = build_credential_name("site_a", "client_secret")
        assert pair == ("site_a", "client_secret")
        assert error is None

    def test_strips_whitespace(self):
        """前後の空白は取る（コピペで混ざりやすい）。"""
        pair, _ = build_credential_name(" site_a ", " client_id ")
        assert pair == ("site_a", "client_id")

    def test_empty_site_returns_error(self):
        pair, error = build_credential_name("", "client_id")
        assert pair is None
        assert error is not None
        assert "サイト名" in error

    def test_empty_field_returns_error(self):
        pair, error = build_credential_name("site_a", "")
        assert pair is None
        assert error is not None
        assert "項目名" in error

    def test_japanese_site_returns_error(self):
        """日本語やスペースは使えない（名前は半角英数字とアンダースコアだけ）。"""
        pair, error = build_credential_name("サイトA", "client_id")
        assert pair is None
        assert error is not None
        assert "半角英数字" in error

    def test_japanese_field_returns_error(self):
        pair, error = build_credential_name("site_a", "クライアントID")
        assert pair is None
        assert error is not None
        assert "半角英数字" in error


class TestWindow:
    """画面が組み立てられること（表示はしない）。"""

    def test_window_builds_and_closes(self, tmp_path):
        from comken.toolbox.credentials.gui import CredentialsApp

        root = _make_root()
        try:
            app = CredentialsApp(root, path=tmp_path / "system-id.enc")
            app._refresh()  # 一覧の更新が例外なく動くこと
            assert app.tree.get_children() == ()  # 空の保存先なので1件もない
        finally:
            root.destroy()

    def test_selecting_an_existing_pair_fills_the_form(self, tmp_path):
        """左の一覧から ``site.field`` を選ぶと、 サイト名・項目名が自動入力され、 値欄は空になる。

        登録し直すときに site/field を手で打ち直させない、が狙い
        （手で打つと typo で別キーとして新規登録されてしまう）。
        """
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)
            app.value_var.set("残っていたら失敗")

            app.tree.selection_set("salesforce.password")
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == "password"
            assert app.value_var.get() == ""  # 値は保持していないので空にする
        finally:
            root.destroy()

    def test_grouping_multiple_fields_under_one_site(self, tmp_path):
        """同じサイトの複数項目は、1つの親ノードの下にまとまる。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credentials

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credentials(
                {
                    "salesforce": {"client_id": "a", "client_secret": "b"},
                    "kintai": {"password": "c"},
                },
                path,
            )
            app = CredentialsApp(root, path=path)

            # list_names() は (サイト名, 項目名) でソートして返すため、
            # サイト名のアルファベット順（kintai → salesforce）で並ぶ
            assert app.tree.get_children() == ("kintai", "salesforce")
            assert app.tree.get_children("salesforce") == (
                "salesforce.client_id",
                "salesforce.client_secret",
            )
            assert app.tree.item("salesforce", "text") == "salesforce（2件）"
        finally:
            root.destroy()

    def test_selecting_a_site_node_fills_only_the_site_name(self, tmp_path):
        """サイト行（親）を選んだだけでは項目名は定まらないので、空のままにする。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce")
            app._on_select_existing(tk.Event())

            assert app.system_var.get() == "salesforce"
            assert app.field_var.get() == ""
        finally:
            root.destroy()


class TestShowValue:
    """「値を表示」で選んだ項目の値だけを読み出して、伏せ字の欄に表示する。"""

    def test_shows_the_selected_value_masked(self, tmp_path):
        """子を選んで「値を表示」→ 欄に値が入る。既定は伏せ字。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce.password")
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER  # 読む前は伏せ字

            app._on_show_value()

            assert app.read_value_entry.get() == "old-value"
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_checkbox_unmasks_only_the_read_field(self, tmp_path):
        """「値を表示する」で伏せ字を外す。登録フォームの欄は変わらない。"""
        from comken.toolbox.credentials.gui import CredentialsApp

        root = _make_root()
        try:
            app = CredentialsApp(root, path=tmp_path / "system-id.enc")

            app.read_value_show_var.set(True)
            app._on_toggle_read_value_show()

            assert app.read_value_entry.cget("show") == ""
            assert app.value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_form_checkbox_does_not_unmask_the_read_field(self, tmp_path):
        """登録フォーム側のチェックは、読み出した値の欄に影響しない。"""
        from comken.toolbox.credentials.gui import CredentialsApp

        root = _make_root()
        try:
            app = CredentialsApp(root, path=tmp_path / "system-id.enc")

            app.show_var.set(True)
            app._on_toggle_show()

            assert app.value_entry.cget("show") == ""
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_clears_the_value_when_the_selection_changes(self, tmp_path):
        """別の項目を選ぶと、前の値は消えて伏せ字に戻る。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credentials

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credentials(
                {"salesforce": {"password": "old-value"}, "kintai": {"password": "other-value"}},
                path,
            )
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce.password")
            app._on_show_value()
            assert app.read_value_entry.get() == "old-value"

            app.tree.selection_set("kintai.password")
            root.update()  # 選択が変わったイベントを処理する

            assert app.read_value_entry.get() == ""
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_clears_the_value_when_the_list_is_refreshed(self, tmp_path):
        """一覧を更新するとき（登録・削除・取り込みのあと）も、欄は空になる。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce.password")
            app._on_show_value()
            assert app.read_value_entry.get() == "old-value"

            app._refresh()

            assert app.read_value_entry.get() == ""
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_does_not_read_the_value_when_nothing_is_selected(self, tmp_path):
        """何も選んでいないときは値を読み出さない。"""
        from unittest.mock import patch

        from comken.toolbox.credentials.gui import CredentialsApp

        root = _make_root()
        try:
            app = CredentialsApp(root, path=tmp_path / "system-id.enc")

            with (
                patch("comken.toolbox.credentials.gui.load_credential") as mock_load,
                patch("comken.toolbox.credentials.gui.messagebox.showinfo") as mock_info,
            ):
                app._on_show_value()

            mock_load.assert_not_called()
            mock_info.assert_called_once()
        finally:
            root.destroy()

    def test_does_not_read_the_value_of_a_site_row(self, tmp_path):
        """サイト行（親）を選んだときは値を読み出さない。"""
        from unittest.mock import patch

        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            with (
                patch("comken.toolbox.credentials.gui.load_credential") as mock_load,
                patch("comken.toolbox.credentials.gui.messagebox.showinfo") as mock_info,
            ):
                app.tree.selection_set("salesforce")
                app._on_show_value()

            mock_load.assert_not_called()
            # 削除ボタンと同じ流儀で、案内だけ出して何もしない
            mock_info.assert_called_once()
        finally:
            root.destroy()

    def test_shows_an_error_when_the_value_cannot_be_read(self, tmp_path):
        """復号できないときはエラー表示にして、欄は空のまま。"""
        from unittest.mock import patch

        from comken.exceptions import CredentialError
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)
            app.tree.selection_set("salesforce.password")

            with (
                patch(
                    "comken.toolbox.credentials.gui.load_credential",
                    side_effect=CredentialError("認証情報を復号できませんでした"),
                ),
                patch("comken.toolbox.credentials.gui.messagebox.showerror") as mock_error,
            ):
                app._on_show_value()

            mock_error.assert_called_once()
            assert "認証情報を復号できませんでした" in mock_error.call_args.args[1]
            assert app.read_value_entry.get() == ""
            assert app.read_value_entry.cget("show") == _MASK_CHARACTER
        finally:
            root.destroy()

    def test_status_bar_does_not_contain_the_value(self, tmp_path):
        """ステータスバーには値そのものが出ない（キー名と文字数だけ出る）。"""
        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)

            app.tree.selection_set("salesforce.password")
            app._on_show_value()

            status = app.status_var.get()
            assert "old-value" not in status
            assert "salesforce.password" in status
            assert "9 文字" in status
        finally:
            root.destroy()

    def test_log_does_not_contain_the_value(self, tmp_path, caplog):
        """ログにも値そのものは出さない（キー名と文字数だけ出す）。"""
        import logging

        from comken.toolbox.credentials.gui import CredentialsApp
        from comken.toolbox.credentials.store import save_credential

        root = _make_root()
        try:
            path = tmp_path / "system-id.enc"
            save_credential("salesforce", "password", "old-value", path)
            app = CredentialsApp(root, path=path)
            app.tree.selection_set("salesforce.password")

            with caplog.at_level(logging.DEBUG, logger="comken.toolbox.credentials.gui"):
                app._on_show_value()

            assert "old-value" not in caplog.text
        finally:
            root.destroy()
