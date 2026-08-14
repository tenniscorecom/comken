"""
utils モジュールのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

import datetime
import os
import time
from unittest.mock import patch

import pytest

from comken.browser.download import DownloadDir
from comken.constants import SortBy
from comken.exceptions import ColumnNotFoundError, DownloadTimeoutError
from comken.utils import (
    diff_row,
    diff_rows,
    normalize,
    now,
    remove_spaces,
    strip_spaces,
    today,
    wait,
)
from comken.utils.files import (
    DateNameBuilder,
    FileFinder,
    Paths,
    copy_file,
    date_in_name,
    move_file,
)


class TestClock:
    def test_now_has_timezone(self):
        assert now().tzinfo is not None

    def test_today_returns_date(self):
        assert isinstance(today(), datetime.date)

    def test_now_returns_local_time_not_utc(self):
        """UTC ではなく PC のローカル時刻を返す。

        now() を UTC のままにすると、日本時間の 0:00〜9:00 の間は date() が前日になり、
        「今日のファイル」の判定や日付付きファイル名が1日ずれる。
        うっかり .astimezone() を削られたときに、この検証で気づけるようにしておく。
        """
        # OS が持つローカルのUTCオフセット（夏時間の有無も考慮する）
        is_dst = time.daylight and time.localtime().tm_isdst > 0
        expected_offset = datetime.timedelta(seconds=-(time.altzone if is_dst else time.timezone))

        assert now().utcoffset() == expected_offset

    def test_today_matches_the_date_on_the_pc_clock(self):
        """today() が PC の時計どおりの日付になる（1日ずれない）。"""
        year, month, day = time.localtime()[:3]

        assert today() == datetime.date(year, month, day)


def test_date_in_name_is_available_from_public_package() -> None:
    assert date_in_name("売上_20260729.csv") == datetime.date(2026, 7, 29)
    assert date_in_name("日付なし.csv") is None


class TestMoveFile:
    """move_file のテスト。"""

    def test_moves_into_existing_folder(self, tmp_path):
        """dst が既存フォルダなら、その中に同名で移動する。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")
        folder = tmp_path / "output"
        folder.mkdir()

        result = move_file(src, folder)

        assert result == folder / "report.xlsx"
        assert result.read_text(encoding="utf-8") == "data"
        assert not src.exists()

    def test_moves_to_file_path_with_auto_mkdir(self, tmp_path):
        """ファイルパス指定なら親フォルダを自動作成して移動する。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")
        target = tmp_path / "out" / "sub" / "売上.xlsx"

        result = move_file(src, target)

        assert result == target
        assert target.exists()

    def test_overwrites_existing_file(self, tmp_path):
        """移動先に同名ファイルがあれば上書きする。"""
        src = tmp_path / "report.xlsx"
        src.write_text("new", encoding="utf-8")
        target = tmp_path / "out" / "report.xlsx"
        target.parent.mkdir()
        target.write_text("old", encoding="utf-8")

        move_file(src, target)

        assert target.read_text(encoding="utf-8") == "new"

    def test_same_file_is_left_unchanged(self, tmp_path):
        """移動元と移動先が同じファイルなら、何もせずそのパスを返す。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")

        result = move_file(src, tmp_path)

        assert result == src
        assert src.read_text(encoding="utf-8") == "data"

    def test_copy_failure_preserves_source_and_existing_target(self, tmp_path):
        """ドライブ間コピーが失敗しても移動元と既存の移動先を残す。"""
        src = tmp_path / "report.xlsx"
        src.write_text("new", encoding="utf-8")
        target = tmp_path / "out" / "report.xlsx"
        target.parent.mkdir()
        target.write_text("old", encoding="utf-8")

        with (
            patch.object(type(src), "replace", side_effect=OSError),
            patch("comken.utils.files.ops.shutil.copy2", side_effect=OSError("copy failed")),
            pytest.raises(OSError, match="copy failed"),
        ):
            move_file(src, target)

        assert src.read_text(encoding="utf-8") == "new"
        assert target.read_text(encoding="utf-8") == "old"
        assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


class TestCopyFile:
    """copy_file のテスト。"""

    def test_copies_into_existing_folder(self, tmp_path):
        """dst が既存フォルダなら、その中に同名でコピーする（元は残る）。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")
        folder = tmp_path / "output"
        folder.mkdir()

        result = copy_file(src, folder)

        assert result == folder / "report.xlsx"
        assert src.exists()  # 元ファイルは残る

    def test_copies_to_file_path_with_auto_mkdir(self, tmp_path):
        """ファイルパス指定なら親フォルダを自動作成してコピーする。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")
        target = tmp_path / "out" / "backup.xlsx"

        result = copy_file(src, target)

        assert result == target
        assert target.read_text(encoding="utf-8") == "data"

    def test_same_file_is_left_unchanged(self, tmp_path):
        """コピー元とコピー先が同じファイルなら、何もせずそのパスを返す。"""
        src = tmp_path / "report.xlsx"
        src.write_text("data", encoding="utf-8")

        result = copy_file(src, tmp_path)

        assert result == src
        assert src.read_text(encoding="utf-8") == "data"


class TestDateNameBuilder:
    """DateNameBuilder のテスト。

    今日の日付をファイル名に付与するクラス。
    prefix / suffix / 拡張子 / 日付フォーマットの組み合わせを確認する。
    """

    def test_plain(self):
        """plain() は日付なしのファイル名を返す。"""
        assert DateNameBuilder("レポート").plain() == "レポート.xlsx"

    def test_prefix(self):
        """prefix() は YYYYMMDD を前に付ける。"""
        today_text = today().strftime("%Y%m%d")
        assert DateNameBuilder("レポート").prefix() == f"{today_text}_レポート.xlsx"

    def test_suffix(self):
        """suffix() は YYYYMMDD を後ろに付ける。"""
        today_text = today().strftime("%Y%m%d")
        assert DateNameBuilder("レポート").suffix() == f"レポート_{today_text}.xlsx"

    def test_custom_ext(self):
        """ext 引数で拡張子を変更できる。"""
        today_text = today().strftime("%Y%m%d")
        assert DateNameBuilder("ログ", ext=".csv").prefix() == f"{today_text}_ログ.csv"

    def test_ext_without_dot_is_normalized(self):
        """ext をドットなしで渡しても補完されることを確認する。"""
        assert DateNameBuilder("ログ", ext="csv").plain() == "ログ.csv"

    def test_yyyymm_format(self):
        """date_format="%Y%m" にすると年月のみになる。月次ファイルに使う。"""
        ym = today().strftime("%Y%m")
        assert DateNameBuilder("月次").prefix(date_format="%Y%m") == f"{ym}_月次.xlsx"

    def test_custom_date_format(self):
        """任意の strftime フォーマットを指定できる。"""
        formatted = today().strftime("%Y-%m-%d")
        assert (
            DateNameBuilder("レポート").prefix(date_format="%Y-%m-%d")
            == f"{formatted}_レポート.xlsx"
        )


class TestFileFinderToday:
    """FileFinder.today() のテスト。

    フォルダ内から今日の日付を含むファイルを取得する。
    tmp_path は pytest が提供するテスト用の一時フォルダで、テスト後に自動削除される。
    """

    def test_finds_today_file(self, tmp_path):
        """今日の日付を含むファイルが見つかる。"""
        today_text = today().strftime("%Y%m%d")
        target = tmp_path / f"{today_text}_売上.xlsx"
        target.touch()

        assert FileFinder(tmp_path).today() == target

    def test_raises_when_not_found(self, tmp_path):
        """今日の日付を含むファイルが存在しない場合は FileNotFoundError になる。"""
        (tmp_path / "20200101_古いファイル.xlsx").touch()

        with pytest.raises(FileNotFoundError):
            FileFinder(tmp_path).today()

    def test_returns_none_when_not_required(self, tmp_path):
        """required=False なら見つからなくても None を返す。"""
        assert FileFinder(tmp_path).today(required=False) is None

    def test_yyyymm_format(self, tmp_path):
        """date_format="%Y%m" で年月のみのファイル名を検索できる。"""
        ym = today().strftime("%Y%m")
        target = tmp_path / f"{ym}_月次.xlsx"
        target.touch()

        assert FileFinder(tmp_path).today(date_format="%Y%m") == target

    def test_csv_pattern(self, tmp_path):
        """pattern="*.csv" にすると CSV ファイルのみ検索対象になる。"""
        today_text = today().strftime("%Y%m%d")
        target = tmp_path / f"{today_text}_ログ.csv"
        target.touch()

        assert FileFinder(tmp_path).today(pattern="*.csv") == target

    def test_returns_latest_when_multiple(self, tmp_path):
        """今日のファイルが複数ある場合、更新日時が最も新しいものを返す。"""
        today_text = today().strftime("%Y%m%d")
        old = tmp_path / f"{today_text}_v1.xlsx"
        new = tmp_path / f"{today_text}_v2.xlsx"
        old.touch()
        new.touch()
        os.utime(old, (0, 0))  # old の更新日時を過去（Unix エポック）に設定

        assert FileFinder(tmp_path).today() == new

    def test_ignores_matching_folder(self, tmp_path):
        """名前が一致してもフォルダは検索結果に含めない。"""
        today_text = today().strftime("%Y%m%d")
        (tmp_path / f"{today_text}_売上.xlsx").mkdir()

        assert FileFinder(tmp_path).today(required=False) is None


class TestFileFinderLatest:
    """FileFinder.latest() のテスト。

    デフォルトはファイル名の辞書順で最後のファイルを取得する。
    """

    def test_finds_latest_by_name(self, tmp_path):
        """ファイル名の辞書順で最後のファイルを返す（更新日時は影響しない）。"""
        name_new = tmp_path / "20260711_売上.xlsx"
        name_old = tmp_path / "20260101_売上.xlsx"
        name_new.touch()
        name_old.touch()
        os.utime(name_new, (0, 0))  # 名前上の最新の方を、更新日時では最古にする

        assert FileFinder(tmp_path).latest() == name_new

    def test_finds_latest_by_updated(self, tmp_path):
        """by="updated" なら更新日時が最も新しいファイルを返す。"""
        name_new = tmp_path / "20260711_売上.xlsx"
        name_old = tmp_path / "20260101_売上.xlsx"
        name_new.touch()
        name_old.touch()
        os.utime(name_new, (0, 0))  # 名前上の最新の方を、更新日時では最古にする

        assert FileFinder(tmp_path).latest(by=SortBy.UPDATED) == name_old

    def test_invalid_by_raises(self, tmp_path):
        """by に不正な値を指定すると ValueError になる。"""
        with pytest.raises(ValueError):
            FileFinder(tmp_path).latest(by="date")

    def test_raises_when_empty(self, tmp_path):
        """対象ファイルが存在しない場合は FileNotFoundError になる。"""
        with pytest.raises(FileNotFoundError):
            FileFinder(tmp_path).latest()

    def test_returns_none_when_not_required(self, tmp_path):
        """required=False なら見つからなくても None を返す。"""
        assert FileFinder(tmp_path).latest(required=False) is None

    def test_csv_pattern(self, tmp_path):
        """pattern="*.csv" で CSV のみ対象にできる。xlsx は無視される。"""
        (tmp_path / "data.xlsx").touch()
        target = tmp_path / "data.csv"
        target.touch()

        assert FileFinder(tmp_path).latest(pattern="*.csv") == target

    def test_ignores_matching_folder(self, tmp_path):
        """パターンに一致してもフォルダは検索結果に含めない。"""
        (tmp_path / "売上.xlsx").mkdir()

        assert FileFinder(tmp_path).latest(required=False) is None


class TestFileFinderDated:
    """FileFinder.dated() のテスト。"""

    def test_returns_files_in_date_descending_order(self, tmp_path):
        """ファイル名の日付が新しい順で返る。"""
        old = tmp_path / "売上_20260101.xlsx"
        new = tmp_path / "売上_20260729.xlsx"
        old.touch()
        new.touch()

        assert FileFinder(tmp_path).dated() == [new, old]

    @pytest.mark.parametrize(
        "date_text",
        ["20260729", "2026-07-29", "2026_07_29", "2026.07.29"],
    )
    def test_recognizes_supported_date_formats(self, tmp_path, date_text):
        """対応する4種類の日付表記を認識する。"""
        target = tmp_path / f"日本語レポート_{date_text}.xlsx"
        target.touch()

        assert FileFinder(tmp_path).dated() == [target]

    @pytest.mark.parametrize(
        "name",
        [
            "日付なし.xlsx",
            "不正日付_20261345.xlsx",
            "伝票120260729001.xlsx",
            "区切り不一致_2026-07_29.xlsx",
            "全角数字_２０２６０７２９.xlsx",
        ],
    )
    def test_ignores_names_without_valid_supported_date(self, tmp_path, name):
        """日付でない数字や未対応の表記を検索結果に含めない。"""
        (tmp_path / name).touch()

        assert FileFinder(tmp_path).dated(required=False) == []

    def test_ignores_matching_folder(self, tmp_path):
        """日付表記を含む名前でもフォルダは検索結果に含めない。"""
        (tmp_path / "売上_20260729.xlsx").mkdir()

        assert FileFinder(tmp_path).dated(required=False) == []

    def test_same_date_is_ordered_by_updated_time(self, tmp_path):
        """同じ日付なら更新日時が新しい順で返る。"""
        old = tmp_path / "売上_20260729_v1.xlsx"
        new = tmp_path / "売上_20260729_v2.xlsx"
        old.touch()
        new.touch()
        os.utime(old, (0, 0))

        assert FileFinder(tmp_path).dated() == [new, old]

    def test_returns_empty_list_when_not_required(self, tmp_path):
        """required=False なら該当ファイルがなくても空リストを返す。"""
        assert FileFinder(tmp_path).dated(required=False) == []

    def test_raises_when_required_file_is_not_found(self, tmp_path):
        """required=True なら該当ファイルがないと FileNotFoundError になる。"""
        with pytest.raises(FileNotFoundError, match="ファイル名に 20260729"):
            FileFinder(tmp_path).dated()

    def test_uses_first_date_when_name_contains_multiple_dates(self, tmp_path):
        """名前に日付が複数ある場合は先に現れる日付で並べる。"""
        first_is_old = tmp_path / "20260101_比較_20261231.xlsx"
        middle = tmp_path / "20260729_売上.xlsx"
        first_is_old.touch()
        middle.touch()

        assert FileFinder(tmp_path).dated() == [middle, first_is_old]


class TestDownloadDir:
    """DownloadDir のテスト。

    ブラウザダウンロード用の一時フォルダの作成・完了待ち・削除を確認する。
    """

    def test_creates_temp_dir(self):
        """インスタンス化すると一時フォルダが作成される。"""
        dl = DownloadDir()
        try:
            assert dl.path.is_dir()
        finally:
            dl.remove()

    def test_fspath_allows_path_conversion(self):
        """os.PathLike として Path() にそのまま渡せる。"""
        from pathlib import Path

        dl = DownloadDir()
        try:
            assert Path(dl) == dl.path
        finally:
            dl.remove()

    def test_wait_returns_completed_files(self):
        """ダウンロード中ファイルがなければ、完了ファイルの一覧を返す。"""
        dl = DownloadDir()
        try:
            target = dl.path / "report.xlsx"
            target.touch()

            assert dl.wait(timeout=3) == [target]
        finally:
            dl.remove()

    def test_wait_times_out_when_in_progress(self):
        """.crdownload が残っている間は完了とみなさず、タイムアウトする。"""
        dl = DownloadDir()
        try:
            (dl.path / "report.xlsx.crdownload").touch()

            with pytest.raises(DownloadTimeoutError):
                dl.wait(timeout=1)
        finally:
            dl.remove()

    def test_wait_ignores_old_temp_file(self, tmp_path):
        """作成前からある一時ファイルは新しいダウンロードを妨げない。"""
        target = tmp_path / "downloads"
        target.mkdir()
        (target / "old.tmp").touch()
        dl = DownloadDir(path=target)
        completed = target / "report.xlsx"
        completed.touch()

        assert dl.wait(timeout=1) == [completed]

    def test_remove_deletes_dir(self):
        """remove() でフォルダごと削除される。"""
        dl = DownloadDir()
        dl.remove()

        assert not dl.path.exists()

    def test_with_block_auto_removes_temp_dir(self):
        """with を抜けると一時フォルダは自動削除される（消し忘れ防止）。"""
        with DownloadDir() as dl:
            assert dl.path.is_dir()

        assert not dl.path.exists()

    def test_with_block_keeps_specified_path(self, tmp_path):
        """path 指定した固定フォルダは with を抜けても削除されない。"""
        target = tmp_path / "downloads"
        with DownloadDir(path=target) as dl:
            (dl.path / "report.xlsx").touch()

        assert target.exists()
        assert (target / "report.xlsx").exists()


class TestDownloadDirFixedPath:
    """path で固定フォルダを指定した場合の DownloadDir のテスト。

    セッションごとの割り当て（どのフォルダを使うか）は test_browser.py で確認する。
    """

    def test_uses_specified_path(self, tmp_path):
        """path 指定で既存フォルダをそのまま使えることを確認する。"""
        target = tmp_path / "downloads"

        dl = DownloadDir(path=target)

        assert dl.path == target
        assert target.is_dir()  # なければ作成される

    def test_wait_ignores_preexisting_files(self, tmp_path):
        """path 指定時、作成前からあったファイルは完了対象にならないことを確認する。"""
        old_file = tmp_path / "前回のダウンロード.xlsx"
        old_file.touch()

        dl = DownloadDir(path=tmp_path)
        new_file = tmp_path / "今回のダウンロード.xlsx"
        new_file.touch()

        assert dl.wait(timeout=3) == [new_file]

    def test_wait_times_out_when_only_old_files(self, tmp_path):
        """path 指定時、前回のファイルしかなければタイムアウトすることを確認する。"""
        (tmp_path / "前回のダウンロード.xlsx").touch()

        dl = DownloadDir(path=tmp_path)

        with pytest.raises(DownloadTimeoutError):
            dl.wait(timeout=1)

    def test_remove_skips_specified_path_with_warning(self, tmp_path, caplog):
        """path 指定した固定フォルダは remove() で削除されず、警告が出ることを確認する。"""
        target = tmp_path / "downloads"
        dl = DownloadDir(path=target)

        dl.remove()

        assert target.exists()
        assert "削除しません" in caplog.text

    def test_remove_force_deletes_specified_path(self, tmp_path):
        """force=True なら path 指定した固定フォルダも削除されることを確認する。"""
        target = tmp_path / "downloads"
        dl = DownloadDir(path=target)

        dl.remove(force=True)

        assert not target.exists()


class TestDiffRow:
    """diff_row（1行同士の差分）のテスト。"""

    def test_returns_changed_columns(self):
        """値が異なる列だけが {列名: (変更前, 変更後)} で返ることを確認する。"""
        before = {"注文番号": "A001", "金額": "1000", "担当者": "山田"}
        after = {"注文番号": "A001", "金額": "2000", "担当者": "山田"}

        assert diff_row(before, after) == {"金額": ("1000", "2000")}

    def test_returns_empty_when_same(self):
        """差分がなければ空の辞書が返ることを確認する（if で判定できる）。"""
        row = {"注文番号": "A001", "金額": "1000"}
        assert diff_row(row, dict(row)) == {}

    def test_csv_string_equals_excel_number(self):
        """CSV の "1000" と Excel の 1000 / 1000.0 は差分にならないことを確認する。"""
        before = {"金額": "1000", "数量": "5"}
        after = {"金額": 1000.0, "数量": 5}

        assert diff_row(before, after) == {}

    def test_none_equals_empty_string(self):
        """Excel の空セル（None）と CSV の空文字（""）は差分にならないことを確認する。"""
        before = {"備考": ""}
        after = {"備考": None}

        assert diff_row(before, after) == {}

    def test_column_only_in_one_side(self):
        """片方にしかない列は、もう片方を None として差分になることを確認する。"""
        before = {"注文番号": "A001"}
        after = {"注文番号": "A001", "金額": "1000"}

        assert diff_row(before, after) == {"金額": (None, "1000")}


class TestDiffRows:
    """diff_rows（データセット同士の差分）のテスト。"""

    def test_detects_added_removed_changed(self):
        """追加・削除・変更をそれぞれ検出することを確認する。"""
        before = [
            {"社員番号": "001", "氏名": "山田"},
            {"社員番号": "002", "氏名": "佐藤"},
        ]
        after = [
            {"社員番号": "001", "氏名": "山田太郎"},  # 変更
            {"社員番号": "003", "氏名": "鈴木"},  # 追加（002 は削除）
        ]

        result = diff_rows(before, after, key="社員番号")

        assert result.added == [{"社員番号": "003", "氏名": "鈴木"}]
        assert result.removed == [{"社員番号": "002", "氏名": "佐藤"}]
        assert len(result.changed) == 1
        assert result.changed[0].key == "001"
        assert result.changed[0].columns == {"氏名": ("山田", "山田太郎")}

    def test_no_diff_returns_empty_result(self):
        """同じデータなら added / removed / changed すべて空になることを確認する。"""
        rows = [{"社員番号": "001", "氏名": "山田"}]

        result = diff_rows(rows, [dict(r) for r in rows], key="社員番号")

        assert result.added == []
        assert result.removed == []
        assert result.changed == []

    def test_key_matches_across_csv_and_excel(self):
        """CSV の "1001" と Excel の 1001.0 がキーとして突合できることを確認する。"""
        before = [{"注文番号": "1001", "金額": "1000"}]  # CSV（全部 str）
        after = [{"注文番号": 1001.0, "金額": 2000}]  # Excel（数値）

        result = diff_rows(before, after, key="注文番号")

        assert result.added == []
        assert result.removed == []
        assert result.changed[0].columns == {"金額": ("1000", 2000)}

    def test_missing_key_column_raises(self):
        """key で指定した列が存在しないと ColumnNotFoundError になることを確認する。"""
        rows = [{"注文番号": "A001"}]

        with pytest.raises(ColumnNotFoundError, match="キー列"):
            diff_rows(rows, rows, key="社員番号")


class TestNormalize:
    """normalize（NFKC テキスト正規化）のテスト。"""

    def test_zenkaku_alphanumeric_to_hankaku(self):
        """全角英数字が半角に変換されることを確認する。"""
        assert normalize("ＡＢＣ１２３") == "ABC123"

    def test_zenkaku_symbol_to_hankaku(self):
        """全角括弧・句点が半角に変換されることを確認する。"""
        assert normalize("（株）") == "(株)"
        assert normalize("１．２") == "1.2"

    def test_hankaku_kana_to_zenkaku(self):
        """半角カタカナが全角カタカナに変換されることを確認する。"""
        assert normalize("ｱｲｳｴｵ") == "アイウエオ"

    def test_hankaku_dakuten_merged(self):
        """半角の濁点付き文字（ｶﾞ）が全角（ガ）に変換されることを確認する。"""
        assert normalize("ｶﾞｷﾞ") == "ガギ"

    def test_already_normalized_unchanged(self):
        """すでに正規化済みの文字列はそのまま返ることを確認する。"""
        assert normalize("ABC山田太郎") == "ABC山田太郎"


class TestStripSpaces:
    """strip_spaces（前後スペース除去）のテスト。"""

    def test_strips_zenkaku_spaces(self):
        """前後の全角スペースが除去されることを確認する。"""
        assert strip_spaces("　山田　太郎　") == "山田　太郎"

    def test_strips_hankaku_spaces(self):
        """前後の半角スペースが除去されることを確認する。"""
        assert strip_spaces("  山田  ") == "山田"

    def test_empty_string(self):
        """空文字列はそのまま空文字列になることを確認する。"""
        assert strip_spaces("") == ""


class TestRemoveSpaces:
    """remove_spaces（全スペース除去）のテスト。"""

    def test_removes_all_spaces(self):
        """半角・全角スペースがすべて除去されることを確認する。"""
        assert remove_spaces("０３－１２３４　５６７８") == "０３－１２３４５６７８"

    def test_removes_tabs(self):
        """タブも除去されることを確認する。"""
        assert remove_spaces("A\tB") == "AB"


class TestWait:
    """wait（待機ユーティリティ）のテスト。"""

    def test_seconds_waits(self):
        """seconds() が指定した秒数だけ待つことを確認する（短い値で）。"""
        import time

        start = time.monotonic()
        wait.seconds(0.05)
        assert time.monotonic() - start >= 0.04

    def test_until_returns_true_when_condition_met(self):
        """until() は条件が満たされると True を返すことを確認する。"""
        counter = [0]

        def condition():
            counter[0] += 1
            return counter[0] >= 3

        assert wait.until(condition, timeout=5, interval=0.01) is True

    def test_until_returns_false_on_timeout(self):
        """until() はタイムアウトすると False を返すことを確認する（エラーではない）。"""
        result = wait.until(lambda: False, timeout=0.05, interval=0.01)
        assert result is False

    def test_until_checks_at_least_once(self):
        """timeout=0 でも条件は最低1回確認されることを確認する。"""
        assert wait.until(lambda: True, timeout=0) is True


class TestPaths:
    """Paths（パス定数）のテスト。"""

    def test_downloads_is_absolute_and_exists(self):
        """downloads() が実在する絶対パスを返すことを確認する（レジストリから解決）。"""
        result = Paths.downloads()
        assert result.is_absolute()
        assert result.is_dir()

    def test_desktop_is_absolute_and_exists(self):
        """desktop() が実在する絶対パスを返すことを確認する（OneDrive リダイレクト対応）。"""
        result = Paths.desktop()
        assert result.is_absolute()
        assert result.is_dir()

    def test_shell_folder_falls_back_on_missing_value(self, tmp_path):
        """レジストリに値がない場合はデフォルトにフォールバックすることを確認する。"""
        from comken.utils.files.paths import _shell_folder

        assert _shell_folder("存在しない値名", tmp_path) == tmp_path

    def test_temp_dir_is_path(self):
        """temp_dir() が Path オブジェクトを返すことを確認する。"""
        from pathlib import Path

        assert isinstance(Paths.temp_dir(), Path)

    def test_temp_dir_exists(self):
        """temp_dir() が実在するディレクトリを返すことを確認する。"""
        assert Paths.temp_dir().is_dir()
