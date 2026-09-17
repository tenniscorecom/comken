"""Salesforce レポートの集約取得（読み取る側）を検証する。

`cached_report()` / `file_path_of()` は設計上ネットワークを使わない。取得を
実行する側（`download_scheduled()`）は 2026-09 に comken の外（Salesforceレポート
ダウンローダー）へ切り出したため、ここでは「取得を実行する側が置くファイル」を
`_simulate_download()` で直接シミュレートし、`cached_report()` がそれを正しく
受け取れるかを確かめる（実際の取得実行側のテストは、そちらのリポジトリの
`tests/` にある）。

`MASTER_PATH` / `HISTORY_PATH` は `monkeypatch.setattr` で tmp_path のパスへ
差し替える。
"""

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
    file_path_of,
    load_master,
)
from comken.services.salesforce_downloader import provider as provider_module
from comken.services.salesforce_downloader.provider import daily_cache_path_of
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

    「ベースパス」配下に `山田` / `佐藤` の担当者用フォルダを作り、各レポートの
    概要ごとのフォルダも pre-create しておく（``provider.py` はフォルダを作らない
    設計なので、``_simulate_download`` 側で揃える）。
    """
    base_path = tmp_path / "ベース"
    base_path.mkdir()
    # 担当者 / 概要のフォルダを作っておく（組み立て結果と一致するように）
    for assignee in ("山田", "佐藤"):
        for summary in ("顧客一覧", "売上実績", "停止中"):
            (base_path / assignee / summary).mkdir(parents=True, exist_ok=True)

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


def _simulate_download(entry: ReportEntry, rows: list[dict] | None = None) -> Path:
    """取得を実行する側（Salesforceレポートダウンローダー）が置くファイルをシミュレートする。

    実物の `download_scheduled()` はもう comken に無いので、ここでは
    「保管ファイル（`file_path_of`）を書き、当日キャッシュ（`daily_cache_path_of`）を
    その内容で更新する」という、書き込み側との契約だけを直接再現する。
    """
    values = ROWS if rows is None else rows
    columns = list(values[0].keys()) if values else ["名前", "金額"]
    archive_path = file_path_of(entry)
    with CSV(archive_path) as csv_file:
        csv_file.replace(Table(columns, values))
    daily_cache_path_of(entry).write_bytes(archive_path.read_bytes())
    return archive_path


class TestFilePathOf:
    """file_path_of() は「管理番号_概要_日付.{csv|xlsx}」を組み立てるだけの純関数。"""

    def test_csv_file_name_has_key_and_summary_and_date(self, tmp_path, monkeypatch):
        base_path = tmp_path / "ベース"
        base_path.mkdir()
        (base_path / "山田" / "顧客一覧").mkdir(parents=True)
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業本部",
                    "山田",
                    "顧客一覧",
                    URL_A,
                    "○",
                    "",
                ]
            ],
            settings_rows=[["営業本部", str(base_path)]],
        )
        # `file_path_of` は内部で `MASTER_PATH` をキーに設定シートを読むため、
        # テストでも差し替える
        monkeypatch.setattr(provider_module, "MASTER_PATH", master)
        entry = load_master(master)["1001"]
        name = file_path_of(entry).name
        assert name.startswith("1001_顧客一覧_")
        assert name.endswith(".csv")
        assert len(name.removesuffix(".csv").rsplit("_", 3)[-1]) == 6

    def test_forbidden_characters_in_summary_are_stripped(self, tmp_path, monkeypatch):
        """ファイル名に使えない文字（\\/:*?\"<>|）は落とす。"""
        base_path = tmp_path / "ベース"
        base_path.mkdir()
        # 禁則文字を含むフォルダ名は Windows で作れないため、
        # ファイルパス組み立て結果に禁則文字が「残らない」ことだけ確認する
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業本部",
                    "山田",
                    "禁則: A/B?C*D",
                    URL_A,
                    "○",
                    "",
                ]
            ],
            settings_rows=[["営業本部", str(base_path)]],
        )
        monkeypatch.setattr(provider_module, "MASTER_PATH", master)
        entry = load_master(master)["1001"]
        name = file_path_of(entry).name
        # 禁則文字が含まれないこと（_ に置換されず、除去される）
        for forbidden in '\\/:*?"<>|':
            assert forbidden not in name

    def test_summary_limit_caps_long_names(self, tmp_path, monkeypatch):
        """概要が長い場合は 30 文字で切る。"""
        base_path = tmp_path / "ベース"
        base_path.mkdir()
        long_summary = "あ" * 50
        long_summary_dir = long_summary[:30]
        (base_path / "山田" / long_summary_dir).mkdir(parents=True)
        master = make_master(
            tmp_path / "管理表.xlsx",
            [
                [
                    "1001",
                    "営業本部",
                    "山田",
                    long_summary,
                    URL_A,
                    "○",
                    "",
                ]
            ],
            settings_rows=[["営業本部", str(base_path)]],
        )
        monkeypatch.setattr(provider_module, "MASTER_PATH", master)
        entry = load_master(master)["1001"]
        name = file_path_of(entry).name
        # 管理番号とサフィックスを除いた概要部分が 30 文字以下
        summary_in_name = name.split("_", 1)[1].rsplit("_", 3)[0]
        assert len(summary_in_name) <= 30


class TestCachedReport:
    """cached_report() は固定パスだけを確認し、Salesforceへ取りに行かない。"""

    def test_returns_the_file_downloaded_by_the_scheduled_run(self, paths):
        entry = load_master(paths["master_path"])["1001"]
        _simulate_download(entry)
        table = cached_report("1001")
        assert cached_report_path("1001").is_file()
        assert table.to_rows() == ROWS

    def test_archive_files_accumulate_while_cache_reflects_latest(self, paths):
        """保管ファイル（`file_path_of`）は書くたびに増えるが、当日キャッシュは最新のみ持つ。

        いつ・何回書くか（1日1回までに制限する等）はスケジュール判定の話で、
        取得を実行する側（Salesforceレポートダウンローダー）の責務。ここでは
        「書き込みが2回あったら」読み取り側がどう見えるかだけを確かめる。
        """
        entry = load_master(paths["master_path"])["1001"]
        updated_rows = [{"名前": "最新", "金額": "300"}]
        _simulate_download(entry)
        _simulate_download(entry, updated_rows)
        # 当日キャッシュは最新の書き込みを反映する
        assert cached_report("1001").to_rows() == updated_rows
        # 保管ファイルは書くたびに増える（2件）+ 当日キャッシュ1件 = 3件
        report_dir = paths["base_path"] / "山田" / "顧客一覧"
        assert len(list(report_dir.glob("1001_*.csv"))) == 3

    def test_second_report_raises_when_cache_is_missing(self, paths):
        """まだ取得していないレポートも、キャッシュが無いなら `CachedReportNotFoundError`"""
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(CachedReportNotFoundError):
            cached_report("1002")

    def test_not_downloaded_yet_raises(self, paths):
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(CachedReportNotFoundError) as caught:
            cached_report("1001")
        assert "1001_顧客一覧_" in str(caught.value)
        assert "python main.py" in str(caught.value)

    def test_manual_file_at_the_displayed_path_is_used_on_rerun(self, paths):
        """例外が示した場所へCSVを置けば、登録操作なしで同じ処理を再実行できる。"""
        _ = paths  # autouse fixture が `MASTER_PATH` を差し替えるのに使う
        with pytest.raises(CachedReportNotFoundError) as caught:
            cached_report("1001")

        # エラー文の最後から2行目が、利用者へ案内する正確な配置先。
        # 実際の復旧手順と同じように、そのパスへ手動取得したCSVを置く。
        cache_path = Path(str(caught.value).splitlines()[-2])
        cache_path.write_text("名前,金額\n手動配置,999\n", encoding="utf-8")

        assert cached_report("1001").to_rows() == [{"名前": "手動配置", "金額": "999"}]

    def test_missing_cache_raises_even_if_archive_exists(self, paths):
        entry = load_master(paths["master_path"])["1001"]
        _simulate_download(entry)
        # 時刻付き保管ファイルは残し、時刻を含まない当日キャッシュだけを消す。
        cache_path = provider_module.daily_cache_path_of(entry)
        cache_path.unlink()
        with pytest.raises(CachedReportNotFoundError):
            cached_report("1001")

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
    """設定シート経由で出力先が決まる経路（`report_folder` / キャッシュ）の確認。"""

    def test_load_group_settings_reads_pairs(self, paths):
        """設定シートの「グループ」「ベースURL」を辞書にできる。"""
        settings = load_group_settings(paths["master_path"])
        assert settings == {"営業本部": paths["base_path"]}

    def test_file_path_of_uses_report_folder(self, paths):
        """`file_path_of` が `report_folder` を経由してベースパス配下に作る。"""
        entry = load_master(paths["master_path"])["1001"]
        archive = file_path_of(entry)
        # ベースパス / 担当者 / 概要 配下にファイルが作られる
        assert archive.parent == paths["base_path"] / "山田" / "顧客一覧"
        assert archive.name.startswith("1001_顧客一覧_")

    def test_daily_cache_path_of_uses_report_folder(self, paths):
        """`daily_cache_path_of` もベースパス配下を返す。"""
        entry = load_master(paths["master_path"])["1001"]
        cache = daily_cache_path_of(entry)
        assert cache.parent == paths["base_path"] / "山田" / "顧客一覧"
        assert cache.name.startswith("1001_顧客一覧_")

    def test_unknown_group_raises_group_not_registered(self, paths, monkeypatch):
        """設定シートに無い登録グループを書くと `GroupNotRegisteredError`。"""
        master = make_master(
            paths["master_path"].parent / "未知グループ.xlsx",
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
            settings_rows=[["営業本部", str(paths["base_path"])]],
        )
        # `file_path_of` は内部で `MASTER_PATH` をキーに設定シートを読むため、
        # この新しい管理表を対象に判定させるには差し替えが必要
        # （差し替えないと、paths フィクスチャが設定した元の管理表の設定シートを
        # 読んでしまい、「未知グループ.xlsx」を検証したことにならない）
        monkeypatch.setattr(provider_module, "MASTER_PATH", master)
        entry = load_master(master)["1001"]
        with pytest.raises(GroupNotRegisteredError) as caught:
            provider_module.file_path_of(entry)
        assert "未知グループ" in str(caught.value)
        assert "営業本部" in str(caught.value)
