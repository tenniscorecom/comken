"""Salesforce レポートの集約取得（読み取る側）を検証する。

`cached_report()` / `cached_report_path()` / `output_path()` は設計上ネットワークを
使わない。取得を実行する側（`download_scheduled()`）は 2026-09 に comken の外
（Salesforceレポートダウンローダー）へ切り出したため、ここでは「取得を実行する側が
置くファイル」を `_simulate_download()` で直接シミュレートし、`cached_report()`
がそれを正しく受け取れるかを確かめる（実際の取得実行側のテストは、そちらの
リポジトリの `tests/` にある）。

`MASTER_PATH` / `HISTORY_PATH` は `monkeypatch.setattr` で tmp_path のパスへ
差し替える。
"""

import datetime as dt
from pathlib import Path

import pytest

from comken.core.table import Table
from comken.exceptions import (
    CachedReportNotFoundError,
    GroupNotRegisteredError,
    ReportDisabledError,
    ReportNotRegisteredError,
)
from comken.services.salesforce_downloader import (
    cached_report,
    cached_report_path,
    load_master,
    output_path,
)
from comken.services.salesforce_downloader import provider as provider_module
from comken.services.salesforce_downloader.sheets.group_settings import load_group_settings
from comken.services.salesforce_downloader.sheets.master import ReportEntry
from comken.toolbox.csv import CSV
from comken.toolbox.excel import Excel

URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"
URL_B = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000FGHIJ/view"
ROWS = [{"名前": "山田", "金額": "100"}, {"名前": "鈴木", "金額": "200"}]

HEADERS = [
    "ID",
    "グループ",
    "担当者",
    "概要",
    "Salesforce URL",
    "有効",
    "備考",
]

GROUP_SETTINGS_HEADERS = ["グループ", "ベースURL"]


@pytest.fixture(autouse=True)
def _reset_master_cache():
    """管理表・グループ設定のプロセス内キャッシュをテストごとに破棄する。

    `_find()` は ``Path.resolve()`` 後の絶対パスをキーに管理表をキャッシュする
    ため、 ``tmp_path`` が違うテスト同士はキーが違っていて**普通はリークしない**。
    ただしモンキーパッチで `paths.MASTER_PATH` を差し替えた直後に古いキャッシュ
    を引きずらないよう、念のため明示的に破棄する。
    """
    provider_module._reset_cached_master()
    try:
        yield
    finally:
        provider_module._reset_cached_master()


def make_master(path: Path, rows: list[list], settings_rows: list[list] | None = None) -> Path:
    """管理表（Excel）を作る。設定シートも一緒に作るかは ``settings_rows`` で切り替える。"""
    table_rows = [dict(zip(HEADERS, row, strict=True)) for row in rows]
    with Excel(path) as book:
        book.create_data_sheet("管理表").create_table("管理表", Table(HEADERS, table_rows))
        if settings_rows is not None:
            settings_table_rows = [
                dict(zip(GROUP_SETTINGS_HEADERS, row, strict=True)) for row in settings_rows
            ]
            book.create_data_sheet("設定").create_table(
                "設定", Table(GROUP_SETTINGS_HEADERS, settings_table_rows)
            )
    return path


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """管理表・履歴・保存先をまとめて用意し、共有定数へ注入する。

    `paths.MASTER_PATH` / `paths.HISTORY_PATH` を tmp_path 配下の値へ差し替える。
    `provider.py` は import 時に独自のローカル束縛を作るので、その属性も同期する。

    ベースパス（設定シート）だけを作り、その配下に「担当者」「概要」の
    サブフォルダは作らない（新仕様のフォルダ階層はベースパスのみ）。
    """
    base_path = tmp_path / "ベース"
    base_path.mkdir()
    master = make_master(
        tmp_path / "レポート管理表.xlsx",
        [
            [
                "1001",
                "営業本部",
                "山田",
                "顧客一覧",
                URL_A,
                "○",
                "",
            ],
            [
                "1002",
                "営業本部",
                "佐藤",
                "売上実績",
                URL_B,
                "○",
                "",
            ],
            [
                "1003",
                "営業本部",
                "山田",
                "停止中",
                URL_B,
                "×",
                "",
            ],
        ],
        settings_rows=[
            ["営業本部", str(base_path)],
        ],
    )
    history_path = tmp_path / "ダウンロード履歴.csv"
    monkeypatch.setattr("comken.services.salesforce_downloader.paths.MASTER_PATH", master)
    monkeypatch.setattr("comken.services.salesforce_downloader.paths.HISTORY_PATH", history_path)
    # `provider` もローカル束縛しているので同期する
    monkeypatch.setattr(provider_module, "MASTER_PATH", master)
    return {
        "master_path": master,
        "history_path": history_path,
        "base_path": base_path,
    }


def _simulate_download(
    entry: ReportEntry,
    rows: list[dict] | None = None,
    *,
    schedule_run_time: dt.time | None = None,
    fixed_now: dt.datetime | None = None,
) -> Path:
    """取得を実行する側（Salesforceレポートダウンローダー）が置くファイルをシミュレートする。

    実物の `download_scheduled()` はもう comken に無いので、ここでは
    「``output_path()`` で組み立てた単一のパスへ ``Table`` を書く」という、
    書き込み側との契約だけを直接再現する。
    """
    values = ROWS if rows is None else rows
    columns = list(values[0].keys()) if values else ["名前", "金額"]
    kwargs: dict = {}
    if fixed_now is not None:
        kwargs["now"] = fixed_now
    archive_path = output_path(entry, schedule_run_time, **kwargs)
    with CSV(archive_path) as csv_file:
        csv_file.replace(Table(columns, values))
    return archive_path


class TestOutputPath:
    """``output_path()`` は唯一の出力パスを組み立てる。"""

    def test_uses_schedule_run_time_when_provided(self, paths):
        """``schedule_run_time`` を渡したら stem に ``%Y%m%d_%H%M`` で埋め込む。"""
        entry = load_master(paths["master_path"])["1001"]
        run_time = dt.time(9, 0)
        fixed_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        path = output_path(entry, run_time, now=fixed_now)
        assert path == paths["base_path"] / "1001_20260918_0900.csv"

    def test_falls_back_to_now_when_schedule_run_time_is_none(self, paths):
        """スケジュール行が無いレポート（後方互換）は ``now`` をそのまま使う。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 1, 7, 13, 30)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        path = output_path(entry, None, now=fixed_now)
        assert path == paths["base_path"] / "1001_20260107_1330.csv"

    def test_uses_clock_now_when_now_argument_is_omitted(self, paths, monkeypatch):
        """``now`` 引数も省略した場合は ``clock_now()`` の現在時刻を使う。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 5, 4, 7, 0)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        path = output_path(entry)
        assert path == paths["base_path"] / "1001_20260504_0700.csv"

    def test_folder_is_base_path_only(self, paths):
        """フォルダは「ベースパス」のみ。「担当者」「概要」の階層は無い。"""
        entry = load_master(paths["master_path"])["1001"]
        path = output_path(entry, schedule_run_time=dt.time(9, 0))
        assert path.parent == paths["base_path"]
        # 担当者・概要がパスに現れない
        assert "山田" not in path.parts
        assert "顧客一覧" not in path.parts

    def test_unknown_group_raises_group_not_registered(self, tmp_path, monkeypatch):
        """``report_folder()`` 経由の ``GroupNotRegisteredError`` がそのまま上がる。"""
        base_path = tmp_path / "ベース"
        base_path.mkdir()
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "未知グループ",
                    "山田",
                    "顧客一覧",
                    URL_A,
                    "○",
                    "",
                ]
            ],
            settings_rows=[["営業本部", str(base_path)]],
        )
        monkeypatch.setattr(provider_module, "MASTER_PATH", master)
        entry = load_master(master)["1001"]
        with pytest.raises(GroupNotRegisteredError) as caught:
            output_path(entry, schedule_run_time=dt.time(9, 0))
        assert "未知グループ" in str(caught.value)
        assert "営業本部" in str(caught.value)


class TestLatestTodayPath:
    """``_latest_today_path()`` はフォルダ内で本日分の最新ファイルを返す。"""

    def test_returns_none_when_no_files(self, paths):
        """当日分のファイルが1つも無いフォルダでは ``None``。"""
        entry = load_master(paths["master_path"])["1001"]
        assert provider_module._latest_today_path(entry) is None

    def test_returns_the_only_today_file(self, paths, monkeypatch):
        """当日分のファイルが1件だけなら、それを返す。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        path = _simulate_download(entry, schedule_run_time=dt.time(9, 0), fixed_now=fixed_now)
        assert provider_module._latest_today_path(entry) == path

    def test_returns_the_latest_when_multiple_today_files_exist(self, paths, monkeypatch):
        """当日分のファイルが複数あれば、ファイル名ソートで一番新しいもの。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 9, 18, 13, 0)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        earlier = _simulate_download(
            entry, rows=[{"名前": "朝", "金額": "1"}], schedule_run_time=dt.time(9, 0)
        )
        _simulate_download(entry, rows=[{"名前": "昼", "金額": "2"}])  # now=13:00 で最新になる
        latest = provider_module._latest_today_path(entry)
        assert latest is not None
        assert latest != earlier
        assert latest.name.endswith("_1300.csv")

    def test_ignores_files_from_other_days(self, paths, monkeypatch):
        """日付が違うファイルは候補に含めない（昨日の同名ファイルは無視）。"""
        entry = load_master(paths["master_path"])["1001"]
        # フォルダに昨日のファイルを直接置く
        yesterday_file = paths["base_path"] / "1001_20260101_0900.csv"
        yesterday_file.write_text("古い", encoding="utf-8")
        # 当日（2026-09-18）のファイルを _simulate_download で置く
        fixed_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        today_file = _simulate_download(
            entry, schedule_run_time=dt.time(9, 0), fixed_now=fixed_now
        )
        latest = provider_module._latest_today_path(entry)
        assert latest == today_file

    def test_ignores_files_from_other_reports(self, paths, monkeypatch):
        """管理番号が違うファイルは候補に含めない（同じフォルダに他レポートのファイル）。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        # 別レポートのファイルを直接置く
        other_file = paths["base_path"] / "1002_20260918_0900.csv"
        other_file.write_text("別レポート", encoding="utf-8")
        target = _simulate_download(
            entry, schedule_run_time=dt.time(9, 0), fixed_now=fixed_now
        )
        assert provider_module._latest_today_path(entry) == target


class TestCachedReport:
    """``cached_report()`` は本日の最新キャッシュを ``Table`` で返す。"""

    def test_returns_the_file_downloaded_by_the_scheduled_run(self, paths):
        entry = load_master(paths["master_path"])["1001"]
        _simulate_download(entry, schedule_run_time=dt.time(9, 0))
        table = cached_report("1001")
        assert cached_report_path("1001").is_file()
        assert table.to_rows() == ROWS

    def test_returns_the_latest_when_run_multiple_times_in_a_day(self, paths, monkeypatch):
        """本日中に複数回取得したら、``cached_report()`` は一番新しいファイルを返す。"""
        entry = load_master(paths["master_path"])["1001"]
        # 1回目: 09:00 取得
        first_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: first_now)
        _simulate_download(
            entry,
            rows=[{"名前": "朝", "金額": "1"}],
            schedule_run_time=dt.time(9, 0),
            fixed_now=first_now,
        )
        # 2回目: 13:00 取得（中身が新しい）
        second_now = dt.datetime(2026, 9, 18, 13, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: second_now)
        _simulate_download(
            entry,
            rows=[{"名前": "昼", "金額": "2"}],
            schedule_run_time=dt.time(13, 0),
            fixed_now=second_now,
        )
        # cached_report() は 2 回目（最新）の中身を返す
        assert cached_report("1001").to_rows() == [{"名前": "昼", "金額": "2"}]
        # フォルダにはファイルが2件残っている（時刻が違うので両方残る）
        saved = sorted(paths["base_path"].glob("1001_*.csv"))
        assert len(saved) == 2

    def test_not_downloaded_yet_raises(self, paths):
        """当日分のキャッシュが無いなら ``CachedReportNotFoundError``。"""
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(CachedReportNotFoundError) as caught:
            cached_report("1001")
        # 例外メッセージに保存先（=ベースパス）が案内される
        assert str(paths["base_path"]) in str(caught.value)
        assert "1001" in str(caught.value)

    def test_manual_file_at_the_expected_path_is_used_on_rerun(self, paths, monkeypatch):
        """``output_path()`` が指すファイル名で配置すれば、``cached_report()`` が読む。"""
        entry = load_master(paths["master_path"])["1001"]
        fixed_now = dt.datetime(2026, 9, 18, 9, 5)  # noqa: DTZ001 — テスト用に意図的に固定した tz-naive な datetime
        monkeypatch.setattr(provider_module, "clock_now", lambda: fixed_now)
        # 例外メッセージに書かれたパスへ手動配置
        manual_path = output_path(entry, schedule_run_time=dt.time(9, 0), now=fixed_now)
        manual_path.write_text("名前,金額\n手動配置,999\n", encoding="utf-8")

        assert cached_report("1001").to_rows() == [{"名前": "手動配置", "金額": "999"}]

    def test_unregistered_key_raises(self, paths):
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(ReportNotRegisteredError):
            cached_report("9999")

    def test_disabled_report_raises(self, paths):
        """無効なレポートは「定期」指定でも例外（取る前段で止める）。"""
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(ReportDisabledError):
            cached_report("1003")


class TestGroupSettingsLoading:
    """設定シート経由で出力先が決まる経路の確認。"""

    def test_load_group_settings_reads_pairs(self, paths):
        """設定シートの「グループ」「ベースURL」を辞書にできる。"""
        settings = load_group_settings(paths["master_path"])
        assert settings == {"営業本部": paths["base_path"]}

    def test_output_path_uses_report_folder(self, paths):
        """``output_path()`` が ``report_folder()`` を経由してベースパス配下に作る。"""
        entry = load_master(paths["master_path"])["1001"]
        path = output_path(entry, schedule_run_time=dt.time(9, 0))
        assert path.parent == paths["base_path"]
        assert path.name.startswith("1001_")
        assert path.name.endswith(".csv")


class TestReportFolder:
    """``report_folder()`` は設定シートのベースパスをそのまま返す。"""

    def test_returns_base_path_only(self, paths):
        """「ベースパス」のみ返す。「担当者」「概要」の階層は作らない。"""
        entry = load_master(paths["master_path"])["1001"]
        settings = load_group_settings(paths["master_path"])
        folder = provider_module.report_folder(entry, settings)
        assert folder == paths["base_path"]

    def test_unknown_group_raises_group_not_registered(self, paths):
        """設定シートに無い登録グループを書くと ``GroupNotRegisteredError``。"""
        entry = load_master(paths["master_path"])["1001"]
        with pytest.raises(GroupNotRegisteredError) as caught:
            provider_module.report_folder(entry, {"別グループ": paths["base_path"]})
        assert "営業本部" in str(caught.value)
