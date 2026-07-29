"""examples/ のオフラインサンプルが実際に動くことを確認するテスト。

外部システム（Excel COM・ブラウザ）を必要としない3本を、
出力先を tmp_path に差し替えて main() まで通し、成果物ができることを検証する。
README・ドキュメントが「そのまま動く」と案内している主張をテストで担保する。
"""

import pytest
from openpyxl import load_workbook


class TestCsvToExcelReport:
    def test_creates_report(self, tmp_path, monkeypatch):
        """CSV を読んで Excel レポートを作る例が xlsx を出力する。"""
        from examples.csv_to_excel_report import run

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
        from examples.excel_key_transfer import run

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
        assert transferred["Z999"][1] in (None, "")

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
        from examples.csv_diff_report import run

        monkeypatch.setattr(run, "OUTPUT_FOLDER", tmp_path)
        monkeypatch.setattr(run, "YESTERDAY_CSV", tmp_path / "yesterday.csv")
        monkeypatch.setattr(run, "TODAY_CSV", tmp_path / "today.csv")
        run.main()

        outputs = list(tmp_path.glob("*.xlsx"))
        assert len(outputs) == 1
        statuses = {
            row[0]
            for row in load_workbook(outputs[0]).active.iter_rows(min_row=2, values_only=True)
        }
        # 追加(004)・削除(003)・変更(002) がそれぞれ検出されている
        assert {"追加", "削除", "変更"} <= statuses


class TestCsvDateMove:
    def test_moves_only_file_with_matching_date(self, tmp_path):
        """指定列とファイル名の日付が一致する CSV だけを移動する。"""
        from examples.csv_date_move.run import move_matching_files

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
