"""
CsvReader クラスのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

from pathlib import Path

import pytest

from comken.constants import Encoding
from comken.csv import CsvReader, CsvWriter
from comken.exceptions import ColumnNotFoundError, CsvError, UnsupportedFileSuffixError


@pytest.fixture
def sample_csv(tmp_path):
    """テスト用 CSV ファイルを作成して返す。"""
    content = "注文番号,金額,担当者\nA001,1000,山田\nA002,2000,山田\nA003,3000,佐藤\n"
    path = tmp_path / "data.csv"
    path.write_text(content, encoding="utf-8-sig")
    return path


class TestCsvReaderRows:
    """rows() のテスト。"""

    def test_path_is_path(self, tmp_path: Path) -> None:
        reader = CsvReader(str(tmp_path / "data.csv"))
        assert reader.path == tmp_path / "data.csv"
        assert isinstance(reader.path, Path)

    def test_rejects_non_csv_suffix(self, tmp_path: Path) -> None:
        with pytest.raises(UnsupportedFileSuffixError):
            CsvReader(tmp_path / "data.txt")

    def test_returns_all_rows(self, sample_csv):
        """全行を辞書のリストで返すことを確認する。"""
        rows = CsvReader(sample_csv).rows()
        assert len(rows) == 3
        assert rows[0] == {"注文番号": "A001", "金額": "1000", "担当者": "山田"}

    def test_columns_filter(self, sample_csv):
        """columns 指定時は指定列のみ返すことを確認する。"""
        rows = CsvReader(sample_csv).rows(columns=["注文番号", "金額"])
        assert rows[0] == {"注文番号": "A001", "金額": "1000"}
        assert "担当者" not in rows[0]


class TestCsvReaderFind:
    """find() のテスト。"""

    def test_finds_existing_row(self, sample_csv):
        """キーに一致する行を返すことを確認する。"""
        row = CsvReader(sample_csv).find("注文番号", "A001")
        assert row is not None
        assert row["金額"] == "1000"

    def test_returns_none_when_not_found(self, sample_csv):
        """見つからない場合は None を返すことを確認する。"""
        row = CsvReader(sample_csv).find("注文番号", "Z999")
        assert row is None

    def test_returns_first_match(self, sample_csv):
        """複数一致する場合は最初の行を返すことを確認する。"""
        row = CsvReader(sample_csv).find("担当者", "山田")
        assert row["注文番号"] == "A001"


class TestCsvReaderFilter:
    """filter() のテスト。"""

    def test_returns_matching_rows(self, sample_csv):
        """条件に一致する全行を返すことを確認する。"""
        rows = CsvReader(sample_csv).filter("担当者", "山田")
        assert len(rows) == 2
        assert all(r["担当者"] == "山田" for r in rows)

    def test_returns_empty_list_when_not_found(self, sample_csv):
        """一致しない場合は空リストを返すことを確認する。"""
        rows = CsvReader(sample_csv).filter("担当者", "存在しない人")
        assert rows == []


class TestCsvReaderColumn:
    """column() のテスト。"""

    def test_returns_column_values(self, sample_csv):
        """指定列の値一覧を返すことを確認する。"""
        values = CsvReader(sample_csv).column("金額")
        assert values == ["1000", "2000", "3000"]


class TestCsvReaderIndex:
    """index() のテスト。"""

    def test_returns_dict_keyed_by_column(self, sample_csv):
        """キー列で辞書化されることを確認する。"""
        lookup = CsvReader(sample_csv).index("注文番号")
        assert "A001" in lookup
        assert lookup["A001"]["金額"] == "1000"

    def test_all_rows_indexed(self, sample_csv):
        """全行がインデックスに含まれることを確認する。"""
        lookup = CsvReader(sample_csv).index("注文番号")
        assert len(lookup) == 3


class TestCsvReaderHeaders:
    """ヘッダーなし CSV（headers 引数）のテスト。"""

    def test_reads_headerless_csv(self, tmp_path):
        """headers で列名を付けると、1行目からデータとして読めることを確認する。"""
        path = tmp_path / "no_header.csv"
        path.write_text("A001,1000\nA002,2000\n", encoding="utf-8")

        rows = CsvReader(path, headers=["注文番号", "金額"]).rows()

        assert len(rows) == 2
        assert rows[0]["注文番号"] == "A001"
        assert rows[1]["金額"] == "2000"

    def test_index_works_with_headers(self, tmp_path):
        """headers 指定でも index() で突合用辞書を作れることを確認する。"""
        path = tmp_path / "no_header.csv"
        path.write_text("A001,1000\nA002,2000\n", encoding="utf-8")

        lookup = CsvReader(path, headers=["注文番号", "金額"]).index("注文番号")

        assert lookup["A002"]["金額"] == "2000"

    def test_headers_too_few_raises(self, tmp_path):
        """headers の列数が CSV の列数より少ないと CsvError になることを確認する。

        （DictReader が余った列を None キーに押し込み、黙ってデータが迷子になるため）
        """
        path = tmp_path / "no_header.csv"
        path.write_text("A001,1000,山田\n", encoding="utf-8")  # 実際は3列

        with pytest.raises(CsvError, match="列数"):
            CsvReader(path, headers=["注文番号", "金額"]).rows()


class TestCsvReaderColumnValidation:
    """存在しない列名の検証テスト。

    列名が間違っていると「黙って0件」ではなく ColumnNotFoundError になる
    （非エンジニアがヘッダーを変更したときに気づけるようにする）。
    """

    def test_find_raises_on_missing_column(self, sample_csv):
        """find で存在しない列名を指定するとエラーになる。"""
        with pytest.raises(ColumnNotFoundError, match="存在する列"):
            CsvReader(sample_csv).find("存在しない列", "A001")

    def test_index_raises_on_missing_column(self, sample_csv):
        """index で存在しない列名を指定するとエラーになる。"""
        with pytest.raises(ColumnNotFoundError):
            CsvReader(sample_csv).index("受注番号")  # 正しくは「注文番号」

    def test_column_raises_on_missing_column(self, sample_csv):
        """column で存在しない列名を指定するとエラーになる。"""
        with pytest.raises(ColumnNotFoundError):
            CsvReader(sample_csv).column("価格")

    def test_rows_columns_raises_on_missing_column(self, sample_csv):
        """rows(columns=...) に存在しない列名が含まれるとエラーになる。"""
        with pytest.raises(ColumnNotFoundError):
            CsvReader(sample_csv).rows(columns=["注文番号", "存在しない列"])


class TestCsvReaderEncoding:
    """文字コードのテスト。"""

    def test_reads_cp932(self, tmp_path):
        """Shift-JIS（cp932）のファイルを明示指定で読み込めることを確認する。"""
        path = tmp_path / "sjis.csv"
        path.write_bytes("番号,名前\n1,山田\n".encode("cp932"))
        rows = CsvReader(path, encoding="cp932").rows()
        assert rows[0]["名前"] == "山田"

    def test_auto_detects_utf8_sig(self, tmp_path):
        """自動判定（デフォルト）で BOM 付き UTF-8 を読めることを確認する。"""
        path = tmp_path / "utf8.csv"
        path.write_text("番号,名前\n1,山田\n", encoding="utf-8-sig")

        rows = CsvReader(path).rows()
        assert rows[0]["名前"] == "山田"
        assert "番号" in rows[0]  # BOM がキーに混入していない

    def test_auto_detects_cp932(self, tmp_path):
        """自動判定（デフォルト）で Shift-JIS を読めることを確認する。"""
        path = tmp_path / "sjis.csv"
        path.write_bytes("番号,名前\n1,鈴木\n".encode("cp932"))

        rows = CsvReader(path).rows()
        assert rows[0]["名前"] == "鈴木"

    def test_auto_raises_when_unknown_encoding(self, tmp_path):
        """UTF-8 でも CP932 でも読めないファイルは CsvError になることを確認する。"""
        path = tmp_path / "unknown.csv"
        path.write_bytes(b"\x81\x20\x81\x20")  # どちらの文字コードでも不正なバイト列

        with pytest.raises(CsvError):
            CsvReader(path).rows()


class TestCsvWriter:
    """CsvWriter のテスト。"""

    def test_write_rows_creates_file_with_header(self, tmp_path):
        """write_rows でヘッダー付きの CSV が作られることを確認する。"""
        path = tmp_path / "output.csv"
        rows = [{"注文番号": "A001", "金額": "1000"}, {"注文番号": "A002", "金額": "2000"}]

        CsvWriter(path, fieldnames=["注文番号", "金額"]).write_rows(rows)

        result = CsvReader(path).rows()
        assert len(result) == 2
        assert result[0] == {"注文番号": "A001", "金額": "1000"}

    def test_append_row_adds_to_existing_file(self, tmp_path):
        """append_row で既存ファイルの末尾に追記されることを確認する。"""
        path = tmp_path / "output.csv"
        writer = CsvWriter(path, fieldnames=["注文番号", "金額"])
        writer.write_rows([{"注文番号": "A001", "金額": "1000"}])

        writer.append_row({"注文番号": "A002", "金額": "2000"})

        result = CsvReader(path).rows()
        assert len(result) == 2
        assert result[1]["注文番号"] == "A002"

    def test_append_row_creates_file_with_header_when_missing(self, tmp_path):
        """ファイルがない状態の append_row はヘッダー付きで新規作成されることを確認する。"""
        path = tmp_path / "new.csv"

        CsvWriter(path, fieldnames=["注文番号"]).append_row({"注文番号": "A001"})

        result = CsvReader(path).rows()
        assert result == [{"注文番号": "A001"}]

    def test_creates_parent_folder(self, tmp_path):
        """親フォルダがなくても自動作成して書き込めることを確認する。

        （ExcelWriter.save と同じ挙動）
        """
        path = tmp_path / "reports" / "2026" / "output.csv"

        CsvWriter(path, fieldnames=["注文番号"]).write_rows([{"注文番号": "A001"}])

        assert path.exists()

    def test_auto_encoding_falls_back_to_utf8_sig(self, tmp_path):
        """Encoding.AUTO を渡すと UTF8_SIG として書き込まれることを確認する。

        （素通しすると open() の "unknown encoding: auto" という不親切なエラーになる。
        CsvReader と同じ定数を渡し回しても落ちないようにフォールバックする）
        """
        path = tmp_path / "output.csv"

        CsvWriter(path, fieldnames=["名前"], encoding=Encoding.AUTO).write_rows([{"名前": "山田"}])

        assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # UTF-8 BOM
        assert CsvReader(path).rows() == [{"名前": "山田"}]
