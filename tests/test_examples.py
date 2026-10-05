"""examples/ のオフラインサンプルが実際に動くことを確認するテスト。

外部システム（Excel COM・ブラウザ）を必要としないサンプルを、
出力先を tmp_path に差し替えて main() まで通し、成果物ができることを検証する。
README・ドキュメントが「そのまま動く」と案内している主張をテストで担保する。
"""

import pytest
from openpyxl import load_workbook


class TestBasicExamples:
    def test_csv_read(self, tmp_path, monkeypatch):
        from examples import csv_read

        csv_path = tmp_path / "受注明細.csv"
        monkeypatch.setattr(csv_read, "CSV_PATH", csv_path)
        csv_read.main()

        assert csv_path.exists()
        assert "株式会社アルファ" in csv_path.read_text(encoding="utf-8")

    def test_csv_write(self, tmp_path, monkeypatch):
        from examples import csv_write

        output_path = tmp_path / "作業記録.csv"
        monkeypatch.setattr(csv_write, "OUTPUT_PATH", output_path)
        csv_write.main()

        assert output_path.exists()
        assert len(output_path.read_text(encoding="utf-8-sig").splitlines()) == 5

    def test_excel_read(self, tmp_path, monkeypatch):
        from examples import excel_read

        excel_path = tmp_path / "在庫一覧.xlsx"
        monkeypatch.setattr(excel_read, "EXCEL_PATH", excel_path)
        excel_read.main()

        assert load_workbook(excel_path, read_only=True)["PY_在庫"].max_row == 3

    def test_excel_write(self, tmp_path, monkeypatch):
        from examples import excel_write

        output_path = tmp_path / "売上帳票.xlsx"
        monkeypatch.setattr(excel_write, "OUTPUT_PATH", output_path)
        excel_write.main()

        worksheet = load_workbook(output_path)[excel_write.SHEET_NAME]
        assert worksheet.freeze_panes == "A2"
        assert worksheet["D4"].value == 4300

    def test_column_mapping(self, tmp_path, monkeypatch):
        from examples import column_mapping

        monkeypatch.setattr(column_mapping, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(column_mapping, "CONFIG_PATH", tmp_path / "config.ini")
        monkeypatch.setattr(column_mapping, "SOURCE_CSV", tmp_path / "受注.csv")
        monkeypatch.setattr(column_mapping, "OUTPUT_PATH", tmp_path / "請求一覧.xlsx")
        column_mapping.main()

        worksheet = load_workbook(column_mapping.OUTPUT_PATH)["PY_請求一覧"]
        assert worksheet["B2"].value == "株式会社アルファ"
        assert worksheet["C2"].value == 12000

    def test_state(self, tmp_path, monkeypatch):
        from examples import state

        state_path = tmp_path / "state.ini"
        monkeypatch.setattr(state, "STATE_PATH", state_path)
        state.main()
        state.main()

        assert "1002" in state_path.read_text(encoding="utf-8")

    def test_logger(self, tmp_path, monkeypatch):
        from examples import logger

        monkeypatch.setattr(logger, "LOG_FOLDER", tmp_path / "logs")
        logger.main()

    def test_runtime(self, tmp_path, monkeypatch):
        from examples import runtime

        monkeypatch.setattr(runtime, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(runtime, "SOURCE_PATH", tmp_path / "source.txt")
        monkeypatch.setattr(runtime, "DRY_RUN_PATH", tmp_path / "dry-run.txt")
        monkeypatch.setattr(runtime, "ACTUAL_PATH", tmp_path / "actual.txt")
        runtime.main()

        assert not runtime.DRY_RUN_PATH.exists()
        assert runtime.ACTUAL_PATH.exists()

    def test_files(self, tmp_path, monkeypatch):
        from examples import files

        monkeypatch.setattr(files, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(files, "ARCHIVE_PATH", tmp_path / "日次資料.zip")
        files.main()

        assert files.ARCHIVE_PATH.exists()
        assert len(list((tmp_path / "展開").glob("*.csv"))) == 2

    def test_utils(self):
        from examples import utils

        utils.main()

    def test_constants(self, tmp_path, monkeypatch):
        from examples import constants

        monkeypatch.setattr(constants, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(constants, "CSV_PATH", tmp_path / "名簿.csv")
        constants.main()

        assert constants.CSV_PATH.exists()

    def test_exceptions(self, tmp_path, monkeypatch):
        from examples import exceptions

        monkeypatch.setattr(exceptions, "CSV_PATH", tmp_path / "例外確認.csv")
        exceptions.main()


class TestCsvToExcelReport:
    def test_creates_report(self, tmp_path, monkeypatch):
        """CSV を読んで Excel レポートを作る例が xlsx を出力する。"""
        from examples.advanced.csv_to_excel_report import run

        monkeypatch.setattr(run, "OUTPUT_FOLDER", tmp_path)
        run.main()

        outputs = list(tmp_path.glob("*.xlsx"))
        assert len(outputs) == 1
        # 合計行まで書けている（ヘッダー + データ3件 + 合計 = 5行以上）
        ws = load_workbook(outputs[0]).active
        assert ws.max_row >= 5
        assert ws.cell(row=ws.max_row, column=1).value == "合計"


class TestExcelKeyTransfer:
    @pytest.fixture
    def transferred(self, tmp_path, monkeypatch):
        """サンプルを実行し、転記後のシートを {注文番号: 行} で返す。"""
        from examples.advanced.excel_key_transfer import run

        monkeypatch.setattr(run, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(run, "MASTER_CSV", tmp_path / "master.csv")
        monkeypatch.setattr(run, "DETAIL_CSV", tmp_path / "detail.csv")
        monkeypatch.setattr(run, "INVOICE_XLSX", tmp_path / "invoice.xlsx")
        run.main()

        ws = load_workbook(tmp_path / "invoice.xlsx").active
        return {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}

    def test_transfers_matched_rows(self, transferred):
        """マスタにあるキーだけ転記される。"""
        assert transferred["A001"][1] == "株式会社アルファ"
        assert "Z999" not in transferred

    def test_sums_multiple_detail_rows(self, transferred):
        """1対多の明細は合計して転記される（後の行で上書きしない）。"""
        # A001 は 48000 + 12000 + 1500。index() で引くと最後の 1500 になってしまう
        assert transferred["A001"][2] == 61500
        assert transferred["A002"][2] == 18000

    def test_amount_is_number_not_text(self, transferred):
        """金額が文字列でなく数値で入る（Excel 側で集計できる）。"""
        assert isinstance(transferred["A001"][2], int)


class TestCsvDiffReport:
    def test_detects_added_removed_changed(self, tmp_path, monkeypatch):
        """差分レポートの例が追加・削除・変更を検出して xlsx を出す。"""
        from examples.advanced.csv_diff_report import run

        monkeypatch.setattr(run, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(run, "YESTERDAY_CSV", tmp_path / "yesterday.csv")
        monkeypatch.setattr(run, "TODAY_CSV", tmp_path / "today.csv")
        run.main()

        outputs = list(tmp_path.glob("*.xlsx"))
        assert len(outputs) == 1
        # openpyxl の ``Cell.value`` は ``_CellGetValue`` で hashable ではない。
        # ``values_only=True`` でも要素は ``Cell`` 由来として扱われるため ``str()`` で
        # 文字列に揃えて ``set`` に入れる（比較対象も ``str``）。
        statuses = {
            str(row[0])
            for row in load_workbook(outputs[0]).active.iter_rows(min_row=2, values_only=True)
        }
        # 追加(004)・削除(003)・変更(002) がそれぞれ検出されている
        assert {"追加", "削除", "変更"} <= statuses


class TestCsvDateMove:
    def test_moves_only_file_with_matching_date(self, tmp_path):
        """指定列とファイル名の日付が一致する CSV だけを移動する。"""
        from examples.advanced.csv_date_move.run import move_matching_files

        input_folder = tmp_path / "input"
        output_folder = tmp_path / "output"
        input_folder.mkdir()
        matching = input_folder / "売上_20260729.csv"
        mismatching = input_folder / "売上_20260730.csv"
        matching.write_text("日付\n2026/07/29\n", encoding="utf-8")
        mismatching.write_text("日付\n2026/07/29\n", encoding="utf-8")

        result = move_matching_files(input_folder, output_folder, "日付", "%Y/%m/%d", "*.csv")

        assert result == (1, 1)
        assert (output_folder / matching.name).exists()
        assert not matching.exists()
        assert mismatching.exists()
        assert not (output_folder / mismatching.name).exists()


class TestDailyBatchTemplate:
    @pytest.fixture
    def run_module(self, monkeypatch):
        """``run`` を ``config.ini`` 無しの状態で import して返す。

        ``examples.advanced.daily_batch_template.config`` はモジュール読込時に
        ``Config(...)`` で ``config.ini`` を読む。CI では
        ``config.ini`` が .gitignore 対象で存在しないため、素直に import した
        だけで ``ConfigError`` が出てしまう（さらに副作用で example から
        ``config.ini`` を生成してしまう）。
        ``run`` を import する前にダミーの ``config`` モジュールを ``sys.modules``
        に差し込んで ``from .config import config`` が ``config.ini`` を読まない
        ようにする。
        """
        import importlib
        import sys
        from types import ModuleType

        dummy_config = ModuleType("examples.advanced.daily_batch_template.config")
        dummy_config.config = None
        monkeypatch.setitem(
            sys.modules,
            "examples.advanced.daily_batch_template.config",
            dummy_config,
        )
        # 既に import 済みだと本物の config を読んだ run が残っている可能性が
        # あるので、毎回ダミーで取り直せるよう run も外しておく。
        # ``from パッケージ import run`` はパッケージの属性に run が残っていると
        # import し直さないので、import_module で読み直す
        monkeypatch.delitem(
            sys.modules,
            "examples.advanced.daily_batch_template.run",
            raising=False,
        )

        return importlib.import_module("examples.advanced.daily_batch_template.run")

    def test_reads_todays_csv_and_writes_report(self, tmp_path, monkeypatch, run_module):
        """雛形の main() が、今日の日付つき CSV を探して Excel レポートを作る。"""
        from types import SimpleNamespace

        from comken.core import today

        input_folder = tmp_path / "input"
        output_folder = tmp_path / "output"
        input_folder.mkdir()
        output_folder.mkdir()
        today = today().strftime("%Y%m%d")
        (input_folder / f"{today}_売上.csv").write_text(
            "商品,金額\nA,100\nB,200\n", encoding="utf-8"
        )
        files = SimpleNamespace(INPUT_FOLDER=input_folder, OUTPUT_FOLDER=output_folder)
        monkeypatch.setattr(run_module, "config", SimpleNamespace(FILES=files))

        run_module.main()

        outputs = list(output_folder.glob("*日次売上レポート.xlsx"))
        assert len(outputs) == 1
        ws = load_workbook(outputs[0])["PY_売上"]
        assert list(ws.iter_rows(min_row=2, values_only=True)) == [("A", "100"), ("B", "200")]

    def test_skips_when_no_input_today(self, tmp_path, monkeypatch, run_module):
        """今日の入力が無ければ、エラーにせず何も出力しない。"""
        from types import SimpleNamespace

        (tmp_path / "input").mkdir()
        (tmp_path / "output").mkdir()
        files = SimpleNamespace(INPUT_FOLDER=tmp_path / "input", OUTPUT_FOLDER=tmp_path / "output")
        monkeypatch.setattr(run_module, "config", SimpleNamespace(FILES=files))

        run_module.main()

        assert list((tmp_path / "output").iterdir()) == []


class TestTableTransferDesign:
    def test_writes_invoice_with_skip_and_unmatched(self, tmp_path, monkeypatch):
        """Transfer.matched_rows / unmatched / apply_mapping を使ったサンプルが
        Excel 出力を作る。matched_rows で continue した行は除かれ、
        read にしか無い行は新規追加、write にしか無い行は「転記元に無し」と
        印が付けられる。
        """
        from examples.advanced.table_transfer_design import run

        monkeypatch.setattr(run, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(run, "SOURCE_CSV", tmp_path / "受注.csv")
        monkeypatch.setattr(run, "OUTPUT_PATH", tmp_path / "請求一覧.xlsx")
        run.main()

        assert (tmp_path / "請求一覧.xlsx").exists()
        ws = load_workbook(tmp_path / "請求一覧.xlsx")["PY_請求一覧"]
        # A001: 通常転記 / A003: 新規追加 / A099: 転記元に無し
        # A002 は continue でスキップされ備考が空欄、filter で落ちる
        rows = {r[0]: r for r in ws.iter_rows(min_row=2, values_only=True)}
        assert set(rows) == {"A001", "A003", "A099"}
        assert rows["A001"][1] == "株式会社アルファ"
        assert rows["A001"][2] == 12000
        assert rows["A001"][3] == "消費税: 1200"
        assert rows["A003"][3] == "新規追加"
        assert rows["A099"][3] == "転記元に無し"


class TestSalesforceQuery:
    """``examples.advanced.salesforce_query`` のサンプルを疑似組織で通す。

    Salesforce 組織・認証情報が無くても ``_fake_org.FakeOpportunityOrg``
    が ``_send`` だけを差し替えるため、``bulk_query()`` / ``query()`` 本体の
    ロジックはそのまま動き、CSV 出力と集計が本物と同じコードで検証できる。
    """

    def test_main_writes_csv_and_aggregates(self, tmp_path, monkeypatch):
        """``main()`` が CSV を作って won_total と count_by_stage を回すこと。"""
        from examples.advanced.salesforce_query import run

        monkeypatch.setattr(run, "OUTPUT_DIR", tmp_path)
        run.main()

        # 1. CSV ができる・5件・ヘッダーがそのまま・文字列のまま・参照項目 Account.Name を含む
        csv_path = tmp_path / "opportunities.csv"
        assert csv_path.exists()
        # comken の CSV は既定で BOM 付き (utf-8-sig) で書く
        rows = list(csv_path.read_text(encoding="utf-8-sig").splitlines())
        # ヘッダー + データ5件 = 6行
        assert len(rows) == 6
        assert rows[0] == "Id,Name,Account.Name,Amount,IsWon,CloseDate"
        # bulk の値は全て文字列のまま: Amount=100000 (前ゼロなし)、IsWon="true" (bool ではない)
        assert "100000" in rows[1]
        assert ",true," in rows[1]
        assert "250000" in rows[2]
        assert ",false," in rows[2]
        # null のセルは空文字のまま (案件C の Amount・案件D の Account.Name)
        assert ",,false," in rows[3]
        assert ",,50000," in rows[4]

    def test_won_total_is_decimal_sum_of_true_rows(self):
        """``won_total`` は IsWon="true" だけ Decimal 合計する。

        "false" も空文字も真と判定されないこと (``row["IsWon"] != "true"``
        で判定するコメントの動作）を担保する。
        """
        from decimal import Decimal

        from comken.core.table import Table
        from comken.toolbox.csv.file import parse_text
        from examples.advanced.salesforce_query._fake_org import (
            OPPORTUNITIES_BULK_PAGE_1,
            OPPORTUNITIES_BULK_PAGE_2,
        )
        from examples.advanced.salesforce_query.run import won_total

        # bulk の結果をパースして Table に詰める
        raw_rows = parse_text(OPPORTUNITIES_BULK_PAGE_1 + OPPORTUNITIES_BULK_PAGE_2)
        columns = list(raw_rows[0])
        data_rows = [dict(zip(columns, row, strict=True)) for row in raw_rows[1:]]
        table = Table(columns, data_rows)

        total = won_total(table)
        # 案件A(100000) + 案件D(50000) + 案件E(75000) = 225000
        # 案件B/C は IsWon=false、案件C は Amount 空欄で Decimal 変換不可のため除外
        assert total == Decimal("225000")

    def test_count_by_stage_returns_int_dict(self):
        """``count_by_stage`` は集計結果を ``{str: int}`` で返す。

        bulk_query() は GROUP BY を 400 で弾くため query() 側に振り分ける
        必要があり、``cnt`` が int で返ることを担保する。件数は bulk CSV の
        5件と合う: Closed Won=3 (IsWon=true) / Prospecting=1 / Negotiation/Review=1。
        """
        from examples.advanced.salesforce_query._fake_org import FakeOpportunityOrg
        from examples.advanced.salesforce_query.run import count_by_stage

        sf = FakeOpportunityOrg()
        try:
            counts = count_by_stage(sf)
        finally:
            sf.close()

        assert counts == {
            "Prospecting": 1,
            "Negotiation/Review": 1,
            "Closed Won": 3,
        }
        # 値が int 型で返ること (bulk のように "5" ではない)
        assert all(isinstance(value, int) for value in counts.values())

    def test_find_account_returns_first_row_dict_without_attributes(self):
        """``find_account`` は 1件の dict を返す (``attributes`` は取り除かれている)。"""
        from examples.advanced.salesforce_query._fake_org import FakeOpportunityOrg
        from examples.advanced.salesforce_query.run import find_account

        sf = FakeOpportunityOrg()
        try:
            account = find_account(sf, "株式会社アルファ")
        finally:
            sf.close()

        assert account == {"Id": "001000000000001XXX", "Name": "株式会社アルファ"}
        # 見つからないときは None (例外にならないこと)
        sf = FakeOpportunityOrg()
        try:
            assert find_account(sf, "存在しない") is None
        finally:
            sf.close()

    def test_find_account_escapes_single_quote(self):
        """``find_account`` は ``'`` を含む名前でも例外を出さず ``None`` を返す。

        利用者入力を SOQL に埋める前に ``\\`` / ``'`` をエスケープしている
        ことを担保する (``O'Brien`` のような名前で ``WHERE Name = 'O'Brien'``
        のように壊れたクエリにならないこと)。
        """
        from examples.advanced.salesforce_query._fake_org import FakeOpportunityOrg
        from examples.advanced.salesforce_query.run import find_account

        sf = FakeOpportunityOrg()
        try:
            # 該当アカウントは疑似組織に登録していないので None。例外が出ないことだけが確認点
            assert find_account(sf, "O'Brien & Sons") is None
        finally:
            sf.close()
