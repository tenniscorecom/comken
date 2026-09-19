"""ダウンロード履歴の読み取り関数を検証する。

履歴の書き込み（旧 `record()`、同時追記の排他制御を含む）は 2026-09 に comken の外
（Salesforceレポートダウンローダー）へ切り出した。書き込み側のテスト（同時追記・
書き込み時のヘッダー検証）はそちらの `tests/` にある。ここでは読み取り関数
（`successful_files_today` / `schedule_succeeded_today` / `truncated_today` /
`read_history`）だけを検証し、テストデータは `_write_row()` で直接 CSV へ書く
（`record()` が内部でやっていたことの最小限の再現）。
"""

import csv
from collections.abc import Sequence
from pathlib import Path

import pytest

from comken.core.clock import now
from comken.exceptions import EncodingDetectionError, HistoryHeaderMismatchError
from comken.services.salesforce_downloader.sheets.history import (
    COLUMNS,
    FAILURE,
    SUCCESS,
    HistoryRow,
    read_history,
    schedule_succeeded_today,
    successful_files_today,
    truncated_today,
)
from comken.services.salesforce_downloader.sheets.master import ReportEntry

# マイグレーションテスト用の固定 URL。``test_service.py`` と同じ値を使う（管理表の URL
# からレポート ID を取り出すテストは ``report_id`` 列が実 URL を要求するため）
URL_A = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report/00O5g00000ABCDE/view"


def _write_row(path: Path, *, entry: ReportEntry, project: str, row: HistoryRow) -> None:
    """テスト用: 旧 `record()` 相当の1行をCSVへ直接書く（書き込み側は別リポジトリへ移動）。"""

    def _stage(value: bool | None) -> str:
        if value is None:
            return ""
        return SUCCESS if value else FAILURE

    values = [
        now().strftime("%Y-%m-%d %H:%M:%S"),
        entry.key,
        row.schedule_key,
        entry.summary,
        entry.report_id,
        entry.url,
        project,
        SUCCESS if row.succeeded else FAILURE,
        _stage(row.fetched_from_salesforce),
        _stage(row.saved_to_file),
        # 保存先の組み立て（group_settings 経由）は他の場所で扱うので、ここでは概要だけ書く
        entry.summary,
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(values)


def test_successful_file_requires_both_overall_and_save_success(tmp_path) -> None:
    """成否だけが成功でも、保存成功が無い履歴を取得済みにしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="異常な履歴",
        row=HistoryRow(True, True, False, file_name="not-saved.csv"),
    )

    assert successful_files_today(history_path, entry.key) == []


def test_read_history_returns_every_row_in_order(tmp_path) -> None:
    """絞り込みはせず、書かれた順のまま全行を Table で返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P1",
        row=HistoryRow(True, True, True, file_name="a.csv"),
    )
    _write_row(
        history_path,
        entry=entry,
        project="P2",
        row=HistoryRow(True, True, True, file_name="b.csv"),
    )

    rows = read_history(history_path).to_rows()
    assert [row["プロジェクト"] for row in rows] == ["P1", "P2"]
    assert rows[0]["ファイル名"] == "a.csv"
    assert rows[1]["ファイル名"] == "b.csv"


def test_read_history_returns_empty_table_when_history_missing(tmp_path) -> None:
    """履歴が無いときは例外を出さず、列だけ持つ空の Table を返す。"""
    result = read_history(tmp_path / "無い.csv")
    assert len(result) == 0
    assert result.columns == list(COLUMNS)


def test_read_history_rejects_header_mismatch(tmp_path) -> None:
    """見出しが壊れている（空の見出しがある／列名が重複している）場合は
    ``HistoryHeaderMismatchError`` で止める。

    列数が違う／列名が一部欠落している／順序が違う程度の変更は
    ``migrate_row()`` で吸収するため、ここでは**致命的に壊れたケース**
    （=どの列値をどの列に読んだか曖昧になるケース）だけを弾く。
    """
    history_path = tmp_path / "履歴.csv"
    # 2列目に空文字の見出し = ``DictReader`` が列値の対応を取れない壊れ方
    history_path.write_text("管理番号,,成否\n1000,x,成功\n", encoding="utf-8-sig")

    with pytest.raises(HistoryHeaderMismatchError):
        read_history(history_path)


def test_schedule_succeeded_today_returns_true_after_same_key_success(tmp_path) -> None:
    """同じスケジュールキーで当日成功した履歴があれば True を返す。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is True


def test_schedule_succeeded_today_returns_false_when_no_record(tmp_path) -> None:
    """履歴が無いとき False を返す。"""
    assert schedule_succeeded_today(tmp_path / "無い.csv", "S001") is False


def test_schedule_succeeded_today_ignores_other_keys(tmp_path) -> None:
    """別スケジュールキーの成功履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S002",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_ignores_other_dates(tmp_path) -> None:
    """昨日の成功履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        (
            "実行日時,管理番号,スケジュールキー,概要,レポートID,URL,プロジェクト,"
            "成否,Salesforce取得結果,保存結果,保存先,ファイル名,取得件数,処理秒数,"
            "原因区分,エラーコード,エラー内容\n"
            "2024-01-01 09:00:00,1001,S001,顧客一覧,,,,成功,成功,成功,,a.csv,1,0.10,,,,"
        ),
        encoding="utf-8-sig",
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_requires_save_success(tmp_path) -> None:
    """成否=成功でも保存結果=失敗なら True にしない（保存できていないので再試行可）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            False,
            file_name="not-saved.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "S001") is False


def test_schedule_succeeded_today_rejects_empty_key(tmp_path) -> None:
    """空文字のスケジュールキーは何を引いても False を返す。

    呼び出し側で空文字を弾くのが本来の形だが、誤って渡された場合の防御として
    False を返す（誤マッチで別行と一致させないため）。
    """
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            True,
            True,
            True,
            file_name="a.csv",
            schedule_key="S001",
        ),
    )
    assert schedule_succeeded_today(history_path, "") is False


def test_truncated_today_returns_true_when_today_failed_with_truncated_error(tmp_path) -> None:
    """今日 ``SalesforceReportTruncatedError`` で失敗した履歴があれば True。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=None,
            cause="Salesforce",
            error_code="SalesforceReportTruncatedError",
            error="2000 行で打ち止め",
        ),
    )
    assert truncated_today(history_path, entry.key) is True


def test_truncated_today_returns_false_when_history_missing(tmp_path) -> None:
    """履歴ファイルが無い場合は例外を出さず False。"""
    assert truncated_today(tmp_path / "無い.csv", "1001") is False


def test_truncated_today_returns_false_for_other_error_codes(tmp_path) -> None:
    """今日の失敗でも、エラーコードが ``SalesforceReportTruncatedError``
    以外（例: 通信エラー、``OSError``）なら False。2000件超以外の失敗は
    毎回リトライしてよい、という既存挙動を壊さない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=False,
            cause="ファイル",
            error_code="OSError",
            error="共有サーバー断",
        ),
    )
    assert truncated_today(history_path, entry.key) is False


def test_truncated_today_ignores_other_report_keys(tmp_path) -> None:
    """別の管理番号の 2000件超 失敗履歴は True にしない。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=False,
            fetched_from_salesforce=True,
            saved_to_file=None,
            cause="Salesforce",
            error_code="SalesforceReportTruncatedError",
            error="2000 行で打ち止め",
        ),
    )
    assert truncated_today(history_path, "別の管理番号") is False


def test_truncated_today_ignores_other_dates(tmp_path) -> None:
    """昨日の ``SalesforceReportTruncatedError`` 失敗は True にしない
    （翌日に改めて1回だけ試すため、日付をまたいだらリセットする）。"""
    history_path = tmp_path / "履歴.csv"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        (
            "実行日時,管理番号,スケジュールキー,概要,レポートID,URL,プロジェクト,"
            "成否,Salesforce取得結果,保存結果,保存先,ファイル名,取得件数,処理秒数,"
            "原因区分,エラーコード,エラー内容\n"
            "2024-01-01 09:00:00,1001,,,,,,失敗,成功,,,"
            ",,1.00,Salesforce,SalesforceReportTruncatedError,2000 行で打ち止め"
        ),
        encoding="utf-8-sig",
    )
    assert truncated_today(history_path, "1001") is False


def test_truncated_today_ignores_successful_rows_with_same_code(tmp_path) -> None:
    """同じエラーコードの文字列が成否=成功の行に書かれていても False
    （あり得ない組合せだが、列値の照合順の防御として明示的に区別する）。"""
    history_path = tmp_path / "履歴.csv"
    entry = _entry(tmp_path)
    _write_row(
        history_path,
        entry=entry,
        project="P",
        row=HistoryRow(
            succeeded=True,
            fetched_from_salesforce=True,
            saved_to_file=True,
            file_name="a.csv",
            error_code="SalesforceReportTruncatedError",
        ),
    )
    assert truncated_today(history_path, entry.key) is False


def _entry(tmp_path: Path) -> ReportEntry:
    """各テストで同じ管理表1行を使う。"""
    _ = tmp_path  # フォルダは組み立てないので受け取るだけ
    return ReportEntry(
        key="1001",
        summary="顧客一覧",
        url="https://example.com/Report/00O5g00000ABCDE/view",
        group="営業本部",
        assignee="山田太郎",
        enabled=True,
        allow_empty=False,
    )


def _write_row_cp932(path: Path, *, entry: ReportEntry, project: str, row: HistoryRow) -> None:
    """テスト用: ``CP932`` で1行書く（Excel で開いて保存し直した履歴を再現）。

    人が Excel で開いて上書き保存すると CP932 化するため、``read_text()`` 側が
    それを吸収できることを確認する。日本語列名が CP932 のバイト列にしか
    乗らないため、UTF-8 試行が失敗して CP932 経路を通る。
    """

    def _stage(value: bool | None) -> str:
        if value is None:
            return ""
        return SUCCESS if value else FAILURE

    values = [
        now().strftime("%Y-%m-%d %H:%M:%S"),
        entry.key,
        row.schedule_key,
        entry.summary,
        entry.report_id,
        entry.url,
        project,
        SUCCESS if row.succeeded else FAILURE,
        _stage(row.fetched_from_salesforce),
        _stage(row.saved_to_file),
        # 保存先の組み立て（group_settings 経由）は他の場所で扱うので、ここでは概要だけ書く
        entry.summary,
        row.file_name,
        "" if row.row_count is None else row.row_count,
        f"{row.seconds:.2f}",
        row.cause,
        row.error_code,
        row.error.replace("\n", " "),
    ]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists() or path.stat().st_size == 0
    with path.open("a", encoding="cp932", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(COLUMNS)
        writer.writerow(values)


# ── 文字コード自動判定（人が Excel で開いて保存し直した履歴の吸収） ──
class TestEncodingAutoDetection:
    """``read_text()`` が UTF-8 (BOM 付き) と CP932 の自動判定で両方読めること。"""

    def test_read_history_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 で保存された履歴も読み取れる（Excel 経由で再保存した履歴）。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry(tmp_path)
        _write_row_cp932(
            history_path,
            entry=entry,
            project="案件集計",
            row=HistoryRow(True, True, True, file_name="a.csv"),
        )
        # 列名・値ともに日本語が含まれるため UTF-8 経由は失敗し、CP932 で復号される
        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["プロジェクト"] == "案件集計"
        assert rows[0]["ファイル名"] == "a.csv"

    def test_successful_files_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から当日の成功ファイル名を取れる。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry(tmp_path)
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="a.csv"),
        )
        matches = successful_files_today(history_path, entry.key)
        # 保存先は ``_write_row_cp932`` 内で ``entry.summary`` を入れる（テスト簡略化のため）
        assert matches == [Path(entry.summary) / "a.csv"]

    def test_schedule_succeeded_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から当日同キーの成功を判定できる。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry(tmp_path)
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(True, True, True, file_name="a.csv", schedule_key="S001"),
        )
        assert schedule_succeeded_today(history_path, "S001") is True

    def test_truncated_today_handles_cp932_encoded_file(self, tmp_path) -> None:
        """CP932 の履歴から ``SalesforceReportTruncatedError`` の当日失敗を拾える。"""
        history_path = tmp_path / "履歴.csv"
        entry = _entry(tmp_path)
        _write_row_cp932(
            history_path,
            entry=entry,
            project="P",
            row=HistoryRow(
                succeeded=False,
                fetched_from_salesforce=True,
                saved_to_file=None,
                cause="Salesforce",
                error_code="SalesforceReportTruncatedError",
                error="2000 行で打ち止め",
            ),
        )
        assert truncated_today(history_path, entry.key) is True

    def test_read_history_rejects_undecodable_file(self, tmp_path) -> None:
        """UTF-8 / CP932 のどちらでも読めないバイト列は明示的にエラーにする。

        エンコーディングを握りつぶすと「読めたように見えて壊れた値」の事故に
        つながるため、``EncodingDetectionError`` で停止する。
        """
        history_path = tmp_path / "履歴.csv"
        history_path.write_bytes(b"\x80\x81\x82\x83")  # UTF-8 / CP932 どちらでも読めないバイト列

        with pytest.raises(EncodingDetectionError):
            read_history(history_path)


# ── 列構成マイグレーション（COLUMNS 追加・削除・並び替え） ─────────────────────
def _write_csv_raw(path: Path, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """テスト用: 任意の列構成で履歴CSVを書く（COLUMNS 以外も書ける）。

    ``_write_row()`` は ``COLUMNS`` 固定のヘルパーなので、COLUMNS と違う列構成を
    試したいテストでは直接このヘルパーで書く。出力は ``_append()`` と同じく
    UTF-8 BOM 付きにする（``read_text()`` の UTF-8 経路で読める）。
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for row in rows:
            writer.writerow(row)


def _today_row_values(
    *, schedule_key: str = "", error_code: str = "", result: str = SUCCESS
) -> list[str]:
    """COLUMNS 順の今日日付1行を組み立てる（テストで使う基本データ）。"""
    today_str = now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        today_str,  # 実行日時
        "1001",  # 管理番号
        schedule_key,  # スケジュールキー
        "顧客一覧",  # 概要
        "00O5g00000ABCDE",  # レポートID
        URL_A,  # URL
        "定期実行",  # プロジェクト
        result,  # 成否
        SUCCESS,  # Salesforce取得結果
        SUCCESS,  # 保存結果
        "顧客一覧",  # 保存先（テスト簡略化のため概要で代用）
        "a.csv",  # ファイル名
        "1",  # 取得件数
        "0.10",  # 処理秒数
        "",  # 原因区分
        error_code,  # エラーコード
        "",  # エラー内容
    ]


class TestHeaderMigration:
    """``COLUMNS`` の列追加・削除・並び替えがあっても、読み込み側が動くこと。

    管理表マイグレーション（``create_template()``）と同じ「増えた列は空文字、
    減った列は捨て、並び順は新しい定義順」のルールを履歴CSV側にも適用する。
    """

    def test_extra_column_at_end_is_absorbed(self, tmp_path) -> None:
        """COLUMNS に無い列が末尾にあるCSVでも、既存データは保持して読み込める。

        増えた列（COLUMNS に無い列）は ``migrate_row()`` が捨てて、新しい
        ``COLUMNS`` 順の Table を返す。値が捨てられた事自体はログや例外で
        騒がず、黙って吸収する。
        """
        history_path = tmp_path / "履歴.csv"
        # 末尾に「新しい列」を足した17列の見出し
        extra_header = [*COLUMNS, "新列"]
        _write_csv_raw(
            history_path,
            header=[*extra_header],
            rows=[[*_today_row_values(), "追加された値"]],
        )

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # 返り値の Table は ``COLUMNS`` の列だけを持つ（追加された列は捨てた）
        assert list(rows[0].keys()) == list(COLUMNS)
        # 既存列の値は保持される
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["ファイル名"] == "a.csv"

    def test_missing_last_column_is_filled_with_empty(self, tmp_path) -> None:
        """COLUMNS の末尾列が無い古いCSVでも、最後の列を空文字として読み込める。"""
        history_path = tmp_path / "履歴.csv"
        # 「エラー内容」を抜いた15列の見出し（古いバージョン想定）
        old_header = list(COLUMNS[:-1])
        _write_csv_raw(
            history_path,
            header=old_header,
            rows=[_today_row_values()[: len(old_header)]],
        )

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # 抜けた列は空文字で埋められる
        assert rows[0]["エラー内容"] == ""
        assert rows[0]["管理番号"] == "1001"

    def test_reordered_columns_are_normalized_to_current_order(self, tmp_path) -> None:
        """COLUMNS の順序が違う古いCSVでも、各値は現在の ``COLUMNS`` 順で読める。"""
        history_path = tmp_path / "履歴.csv"
        # 「管理番号」「実行日時」「プロジェクト」「成否」を先頭に並べ替えた
        # 古い構成。値の並びもそれに揃える
        reordered_header = [
            "管理番号",
            "実行日時",
            "プロジェクト",
            "成否",
            *[
                column
                for column in COLUMNS
                if column not in {"管理番号", "実行日時", "プロジェクト", "成否"}
            ],
        ]
        # 値はヘッダーと同じ並びで書く。5 列目以降は元の COLUMNS 順のうち
        # 先頭4列を除いた残り
        reordered_values = [
            "1001",  # 管理番号
            now().strftime("%Y-%m-%d %H:%M:%S"),  # 実行日時
            "定期実行",  # プロジェクト
            SUCCESS,  # 成否
            "",  # スケジュールキー
            "顧客一覧",  # 概要
            "00O5g00000ABCDE",  # レポートID
            URL_A,  # URL
            SUCCESS,  # Salesforce取得結果
            SUCCESS,  # 保存結果
            "顧客一覧",  # 保存先
            "a.csv",  # ファイル名
            "1",  # 取得件数
            "0.10",  # 処理秒数
            "",  # 原因区分
            "",  # エラーコード
            "",  # エラー内容
        ]
        _write_csv_raw(history_path, header=reordered_header, rows=[reordered_values])

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # ``migrate_row()`` が ``COLUMNS`` 順へ並べ直すため、列名で値を取れる
        assert rows[0]["管理番号"] == "1001"
        assert rows[0]["実行日時"].startswith(now().strftime("%Y-%m-%d"))
        assert rows[0]["成否"] == SUCCESS
        assert rows[0]["ファイル名"] == "a.csv"

    def test_extra_column_does_not_break_successful_files_today(self, tmp_path) -> None:
        """列追加があっても ``successful_files_today()`` が当日成功を拾える。"""
        history_path = tmp_path / "履歴.csv"
        extra_header = [*COLUMNS, "新列"]
        _write_csv_raw(
            history_path,
            header=extra_header,
            rows=[[*_today_row_values(), "追加された値"]],
        )

        matches = successful_files_today(history_path, "1001")
        assert matches == [Path("顧客一覧") / "a.csv"]

    def test_missing_column_does_not_break_schedule_succeeded_today(self, tmp_path) -> None:
        """列欠落があっても ``schedule_succeeded_today()`` が例外を出さない。

        「スケジュールキー」列が無い古いCSVでも、読み込み側で ``migrate_row()``
        が吸収して ``COLUMNS`` 順の行へ揃え直すため、判定ロジックは通常通り動く。
        古い構成ではスケジュールキーが無いので ``schedule_key == ""`` となり、
        渡した ``S001`` とは一致しない（防御的に False を返す）。
        """
        history_path = tmp_path / "履歴.csv"
        # 「スケジュールキー」と「エラー内容」を両方抜いた古い構成
        old_header = [c for c in COLUMNS if c not in {"スケジュールキー", "エラー内容"}]
        old_values_full = _today_row_values(schedule_key="S001")
        # 抜けた列ぶんを除いた値で書く（古い見出し 15 列に合わせる）
        old_values = [
            value
            for header, value in zip(COLUMNS, old_values_full, strict=True)
            if header in set(old_header)
        ]
        _write_csv_raw(history_path, header=old_header, rows=[old_values])

        # 旧バージョンのヘッダーでも例外を出さず、防御的に False を返す
        assert schedule_succeeded_today(history_path, "S001") is False

    def test_reordered_columns_do_not_break_truncated_today(self, tmp_path) -> None:
        """列並び替えがあっても ``truncated_today()`` が truncated エラーを拾える。"""
        history_path = tmp_path / "履歴.csv"
        # 失敗行（``SalesforceReportTruncatedError``）を「管理番号/実行日時/成否/
        # エラーコード」が先頭に並ぶ古い順で書く
        reordered_header = [
            "管理番号",
            "実行日時",
            "成否",
            "エラーコード",
            *[
                column
                for column in COLUMNS
                if column not in {"管理番号", "実行日時", "成否", "エラーコード"}
            ],
        ]
        truncated_values = [
            "1001",
            now().strftime("%Y-%m-%d %H:%M:%S"),
            FAILURE,
            "SalesforceReportTruncatedError",
            "",  # スケジュールキー
            "顧客一覧",  # 概要
            "00O5g00000ABCDE",  # レポートID
            URL_A,  # URL
            "定期実行",  # プロジェクト
            SUCCESS,  # Salesforce取得結果
            "",  # 保存結果
            "",  # 保存先
            "",  # ファイル名
            "",  # 取得件数
            "1.00",  # 処理秒数
            "Salesforce",  # 原因区分
            "",  # エラー内容
        ]
        _write_csv_raw(history_path, header=reordered_header, rows=[truncated_values])

        assert truncated_today(history_path, "1001") is True

    def test_renamed_known_column_is_treated_as_new_column(self, tmp_path) -> None:
        """既存列を**リネーム**した古いCSVでは、旧名の値は捨てられ、新名は空文字。

        ファイル全体マイグレーション（``history_writer._migrate_if_needed()``）
        側で吸収される挙動なので、読み込み側のテストとしては「例外を出さず、
        新 ``COLUMNS`` 順で読める（リネーム前の列は空文字）」ことを確認する。
        """
        history_path = tmp_path / "履歴.csv"
        # 「ファイル名」を「FILE_NAME」にリネームした古いバージョン
        renamed_header = ["FILE_NAME" if c == "ファイル名" else c for c in COLUMNS]
        old_values = _today_row_values()
        renamed_values = [
            "a.csv" if header == "ファイル名" else value
            for header, value in zip(COLUMNS, old_values, strict=True)
        ]
        _write_csv_raw(history_path, header=renamed_header, rows=[renamed_values])

        rows = read_history(history_path).to_rows()
        assert len(rows) == 1
        # リネーム後の列名は ``COLUMNS`` に無いため捨てる
        assert rows[0]["ファイル名"] == ""
        # 他の列は保持
        assert rows[0]["管理番号"] == "1001"
