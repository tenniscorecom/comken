"""CSV API の読み書き・保留・失敗時保護の契約を確認する。"""

from unittest.mock import patch

import pytest

from comken.core import Table
from comken.exceptions import (
    ComkenFileNotFoundError,
    CSVError,
    InvalidTableInputError,
    TableError,
    UnsupportedFileSuffixError,
)
from comken.toolbox import csv as csv_package
from comken.toolbox.csv import CSV


class TestCSV:
    def test_public_api_contains_only_csv(self) -> None:
        assert csv_package.__all__ == ["CSV", "read_text"]
        for removed in ("Csv" + "Reader", "Csv" + "Writer", "Csv" + "Base", "index" + "_files"):
            assert not hasattr(csv_package, removed)

    def test_reads_strings_by_default_and_only_converts_requested_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")
        with CSV(path) as csv_file:
            assert csv_file.read() == [{"id": "1", "name": "山田"}]
        with CSV(path, types={"id": int}) as csv_file:
            assert csv_file.read() == [{"id": 1, "name": "山田"}]

    def test_iter_rows_streams_dicts_one_at_a_time(self, tmp_path) -> None:
        """``iter_rows()`` は 1 行ずつ dict で流す（全件メモリに載せない）。"""
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n2,鈴木\n3,佐藤\n", encoding="utf-8-sig")
        with CSV(path) as csv_file:
            iterator = csv_file.iter_rows()
            assert next(iterator) == {"id": "1", "name": "山田"}
            assert next(iterator) == {"id": "2", "name": "鈴木"}
            assert next(iterator) == {"id": "3", "name": "佐藤"}
            with pytest.raises(StopIteration):
                next(iterator)

    def test_iter_rows_uses_columns_when_header_is_absent(self, tmp_path) -> None:
        """``columns`` を指定したときはヘッダー行を読まずにデータだけ流す。"""
        path = tmp_path / "no-header.csv"
        path.write_text("A001,1000\nA002,2000\n", encoding="utf-8-sig")
        with CSV(path, columns=["id", "amount"]) as csv_file:
            assert list(csv_file.iter_rows()) == [
                {"id": "A001", "amount": "1000"},
                {"id": "A002", "amount": "2000"},
            ]

    def test_iter_rows_with_explicit_encoding_streams_file_directly(self, tmp_path) -> None:
        """明示 encoding 指定時は ``_read_text`` を経由せずファイルから直接ストリーミングする。"""
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n2,鈴木\n", encoding="utf-8")
        with (
            CSV(path, encoding="utf-8") as csv_file,
            patch.object(
                CSV,
                "_read_text",
                side_effect=AssertionError("明示 encoding 指定時は _read_text を呼ばないはず"),
            ),
        ):
            # 明示 encoding のときは文字コード判定のためにファイル全体を読む必要がないため、
            # ``_read_text`` を呼ばずに ``Path.open`` から直接 ``DictReader`` に流す。
            # 呼ばれたら失敗する ``AssertionError`` で検証する。
            assert list(csv_file.iter_rows()) == [
                {"id": "1", "name": "山田"},
                {"id": "2", "name": "鈴木"},
            ]

    def test_iter_rows_with_explicit_encoding_uses_columns(self, tmp_path) -> None:
        """明示 encoding 指定でも ``columns`` 指定はストリーミング経路で動く。"""
        path = tmp_path / "no-header.csv"
        path.write_text("A001,1000\nA002,2000\n", encoding="cp932")
        with (
            CSV(path, encoding="cp932", columns=["id", "amount"]) as csv_file,
            patch.object(
                CSV,
                "_read_text",
                side_effect=AssertionError("明示 encoding 指定時は _read_text を呼ばないはず"),
            ),
        ):
            assert list(csv_file.iter_rows()) == [
                {"id": "A001", "amount": "1000"},
                {"id": "A002", "amount": "2000"},
            ]

    def test_auto_iter_rows_does_not_read_full_file_into_memory(self, tmp_path) -> None:
        """``encoding=None`` の ``iter_rows()`` はファイル全体を読まない。

        ファイル全体を読む ``Path.read_bytes`` / ``_read_text`` を ``AssertionError`` で
        塞いでも ``iter_rows`` が通れば、先頭からのストリームで動いている証拠。
        """
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n2,鈴木\n", encoding="utf-8-sig")
        with (
            CSV(path) as csv_file,
            patch.object(
                type(path),
                "read_bytes",
                side_effect=AssertionError("iter_rows は read_bytes を呼ばないはず"),
            ),
            patch.object(
                CSV,
                "_read_text",
                side_effect=AssertionError("iter_rows は _read_text を呼ばないはず"),
            ),
        ):
            assert list(csv_file.iter_rows()) == [
                {"id": "1", "name": "山田"},
                {"id": "2", "name": "鈴木"},
            ]

    def test_auto_iter_rows_handles_utf8_char_straddling_one_mib(self, tmp_path) -> None:
        """1 MiB 境界に UTF-8 の 3 バイト文字が分断されても誤判定しない。

        先頭に UTF-8 としての「あ」列を繰り返し詰め、1 MiB の境界が必ず
        3 バイト文字の途中で切れるように調整する。切り詰めが効けば、
        残った部分は UTF-8 として復号でき、ファイル全体も UTF-8 として
        読める（途中で切れた文字の続きも正しく結合する）。
        """
        path = tmp_path / "utf8.csv"
        # 「あ,い」= 7 bytes (E3 81 82 2C E3 81 84) + LF = 8 bytes だが、
        # 1048576 が 8 で割り切れるので境界が行末に来てしまう。
        # そこで 7 バイトの行（CSV っぽくないが、ヘッダー＋改行として読ませる）
        # ではなく、5 バイトの「あ\n」を繰り返しにして境界を確実に途中で切らせる。
        # ただし CSV として読めるよう、行末に「,val\n」をつけて CSV 形式にする。
        # 行のバイト長は「a,あ\n」= 1 + 1 + 3 + 1 = 6 バイトで 1048576 % 6 = 4。
        # これで境界が「あ」の途中で切れることが保証される。
        line_utf8 = "a,あ\n"  # 1 + 1 + 3 + 1 = 6 bytes (a, comma, "あ", LF)
        encoded = line_utf8.encode("utf-8")
        target = 1024 * 1024
        repeats = target // len(encoded) + 2  # 確実に 1 MiB を超える
        content = encoded * repeats
        # 1 MiB の境界が「あ」(E3 81 82) の途中（E3 や 81）に来ていることを確認
        assert content[target - 1] >= 0x80, (
            f"expected multi-byte boundary at {target - 1}, got {content[target - 1]:#x}"
        )
        path.write_bytes(content)
        assert path.stat().st_size > 1024 * 1024

        with CSV(path) as csv_file:
            # ヘッダー行（先頭の非空行）も「あ」が境界にかかる可能性が高い。
            # csv.DictReader は先頭行を見出しとして読み、データ行を順に返す。
            # 途中で切れたヘッダーは途中で切れたままセルに入るが、UTF-8 の
            # 文字境界で切れているため decode は成功する。
            rows = list(csv_file.iter_rows())
        # 1 行以上の「あ」行が読める（境界で切れた行は不完全かもしれないが
        # UnicodeDecodeError は起きない）。末尾の手前までは完全に読めるはず。
        assert len(rows) >= 1
        # 少なくとも最初の数行は完全に読めるはず
        for row in rows[: min(len(rows), 100)]:
            # 値は str に変換されている
            for value in row.values():
                assert isinstance(value, str)

    def test_auto_iter_rows_handles_cp932_char_straddling_one_mib(self, tmp_path) -> None:
        """1 MiB 境界に CP932 の 2 バイト文字が分断されても誤判定しない。

        UTF-8 として読めないバイト（CP932 の「あ」= 0x82 0xA0）を 1 MiB 弱
        繰り返して書き、境界が「0x82」の途中で切れるように調整する。
        切り詰めても残りは cp932 と判定でき、CP932 として全行を読める。
        """
        path = tmp_path / "cp932.csv"
        line_cp932 = b"\x82\xa0,\x82\xa2\n"  # あ,い + LF (5 bytes)
        target = 1024 * 1024
        repeats = target // len(line_cp932) + 1
        content = line_cp932 * repeats
        # 1 MiB の境界が「あ」(82 A0) の途中（0x82 の単独）に来ていることを確認
        assert content[target - 1] == 0x82  # CP932 lead without trail
        path.write_bytes(content)
        assert path.stat().st_size > 1024 * 1024

        with CSV(path) as csv_file:
            rows = list(csv_file.iter_rows())
        # 切り詰め + cp932 判定で、全行が CP932 として読める。
        assert len(rows) >= 1
        for row in rows[:-1]:
            assert row["あ"] == "あ"
            assert row["い"] == "い"

    def test_auto_iter_rows_raises_when_only_head_is_ascii_but_tail_is_cp932(
        self, tmp_path
    ) -> None:
        """先頭 1 MiB が ASCII だけ、末尾に CP932 の行があると ``CSVError``。"""
        path = tmp_path / "mixed.csv"
        # 1 MiB + 100 byte まで ASCII の繰り返し
        padding = b"a" * (1024 * 1024 + 100)
        # 末尾に CP932 の「あ,い」行
        tail = b"\x82\xa0,\x82\xa2\n"  # あ,い
        path.write_bytes(padding + tail)
        assert path.stat().st_size > 1024 * 1024
        with (
            CSV(path) as csv_file,
            pytest.raises(CSVError) as exc_info,
        ):
            list(csv_file.iter_rows())
        # 「encoding= を指定」「encoding を明示」など、利用者への対処が示されている
        assert "encoding" in str(exc_info.value)
        # UnicodeDecodeError がそのまま漏れていないこと
        assert not isinstance(exc_info.value, UnicodeDecodeError)

    def test_auto_reads_cp932(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("名前\n山田\n", encoding="cp932")
        with CSV(path) as csv_file:
            assert csv_file.read().column("名前") == ["山田"]

    def test_columns_treats_first_row_as_data(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("A001,1000\n", encoding="utf-8-sig")
        with CSV(path, columns=["注文番号", "金額"]) as csv_file:
            table = csv_file.read()
        assert table.to_rows() == [{"注文番号": "A001", "金額": "1000"}]

    def test_append_is_saved_only_on_normal_with_exit(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="utf-8-sig")
        with pytest.raises(RuntimeError), CSV(path) as csv_file:
            csv_file.append({"id": "2"})
            raise RuntimeError
        with CSV(path) as csv_file:
            assert csv_file.read().column("id") == ["1"]
        with CSV(path) as csv_file:
            csv_file.append({"id": "2"})
        with CSV(path) as csv_file:
            assert csv_file.read().column("id") == ["1", "2"]

    def test_replace_accepts_table(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace(Table(["id"], [{"id": "1"}]))
        with CSV(path) as csv_file:
            assert csv_file.read() == [{"id": "1"}]

    def test_rejects_non_csv_suffix(self, tmp_path) -> None:
        with pytest.raises(UnsupportedFileSuffixError):
            CSV(tmp_path / "data.txt")

    def test_auto_reads_utf8_bom_without_bom_in_header(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")
        with CSV(path) as csv_file:
            assert csv_file.read() == [{"id": "1", "name": "山田"}]

    def test_auto_rejects_unknown_encoding_with_csv_exception(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_bytes(b"\x81\x20\x81\x20")
        with pytest.raises(CSVError), CSV(path) as csv_file:
            csv_file.read()

    def test_headerless_rejects_rows_with_too_many_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("A001,1000,山田\n", encoding="utf-8-sig")
        with (
            pytest.raises(CSVError, match="1行目"),
            CSV(path, columns=["id", "amount"]) as csv_file,
        ):
            csv_file.read()

    def test_read_only_rejects_replace_and_does_not_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\nold\n", encoding="utf-8-sig")
        with pytest.raises(TableError), CSV(path, read_only=True) as csv_file:
            csv_file.replace([{"id": "new"}])
        with CSV(path) as csv_file:
            assert csv_file.read().column("id") == ["old"]

    def test_dry_run_does_not_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\nold\n", encoding="utf-8-sig")
        with CSV(path, dry_run=True) as csv_file:
            csv_file.replace([{"id": "new"}])
            assert csv_file.read().column("id") == ["new"]
            csv_file.save()
        with CSV(path) as csv_file:
            assert csv_file.read().column("id") == ["old"]

    def test_pending_read_is_visible_before_save(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace([{"id": "1"}])
            assert csv_file.read() == [{"id": "1"}]
            assert not path.exists()

    def test_append_requires_matching_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,A\n", encoding="utf-8-sig")
        with pytest.raises(TableError), CSV(path) as csv_file:
            csv_file.append({"id": "2"})

    def test_append_table_requires_matching_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="utf-8-sig")
        with pytest.raises(TableError), CSV(path) as csv_file:
            csv_file.append(Table(["name"], [{"name": "A"}]))

    def test_save_writes_header_and_creates_parent(self, tmp_path) -> None:
        path = tmp_path / "nested" / "data.csv"
        with CSV(path) as csv_file:
            csv_file.replace([{"id": "1"}])
            csv_file.save()
        assert path.read_text(encoding="utf-8-sig") == "id\n1\n"

    def test_types_only_convert_declared_columns(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,amount\n001,2\n", encoding="utf-8-sig")
        with CSV(path, types={"amount": int}) as csv_file:
            table = csv_file.read()
        assert table.to_rows() == [{"id": "001", "amount": 2}]

    def test_type_conversion_error_reports_row_and_column(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id,amount\n1,invalid\n", encoding="utf-8-sig")
        with (
            pytest.raises(TableError, match="1件目、列「amount」"),
            CSV(path, types={"amount": int}) as csv_file,
        ):
            csv_file.read()

    def test_write_failure_preserves_existing_file(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        original = "id\nold\n"
        path.write_text(original, encoding="utf-8-sig")
        with (
            patch("csv.DictWriter.writerows", side_effect=OSError("write failed")),
            pytest.raises(OSError, match="write failed"),
            CSV(path) as csv_file,
        ):
            csv_file.replace([{"id": "new"}])
            csv_file.save()
        assert path.read_text(encoding="utf-8-sig") == original

    @pytest.mark.parametrize("text", ["id,\n1,A\n", "id,id\n1,2\n"])
    def test_rejects_invalid_headers(self, tmp_path, text) -> None:
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8-sig")
        with pytest.raises(CSVError), CSV(path) as csv_file:
            csv_file.read()

    @pytest.mark.parametrize("text", ["id,name\n1\n", "id,name\n1,A,extra\n"])
    def test_rejects_wrong_data_width(self, tmp_path, text) -> None:
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8-sig")
        with pytest.raises(CSVError, match="2行目"), CSV(path) as csv_file:
            csv_file.read()

    @pytest.mark.parametrize("text", ["id,name\n1\n", "id,name\n1,A,extra\n"])
    def test_iter_rows_rejects_wrong_data_width(self, tmp_path, text) -> None:
        """``iter_rows()`` も ``read()`` と同じく列数不一致を検出する。

        ``csv.DictReader`` は列数が合わない行を検証せず、余分な値を ``None``
        キー配下へ、不足した列を ``None`` 値で埋めて黙って返す。以前は
        ``iter_rows()`` だけこの検証が抜けていた。
        """
        path = tmp_path / "data.csv"
        path.write_text(text, encoding="utf-8-sig")
        with pytest.raises(CSVError, match="2行目"), CSV(path) as csv_file:
            list(csv_file.iter_rows())

    def test_iter_rows_with_explicit_encoding_rejects_wrong_data_width(self, tmp_path) -> None:
        """明示 encoding のストリーミング経路（``DictReader`` 直結）でも検出する。"""
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n2\n", encoding="utf-8")
        with (
            pytest.raises(CSVError, match="3行目"),
            CSV(path, encoding="utf-8") as csv_file,
        ):
            list(csv_file.iter_rows())

    def test_iter_rows_headerless_rejects_wrong_data_width(self, tmp_path) -> None:
        """``columns`` 指定（ヘッダー行なし）でも1行目から検出する。"""
        path = tmp_path / "data.csv"
        path.write_text("A001,1000,山田\n", encoding="utf-8-sig")
        with (
            pytest.raises(CSVError, match="1行目"),
            CSV(path, columns=["id", "amount"]) as csv_file,
        ):
            list(csv_file.iter_rows())

    def test_missing_and_zero_byte_have_dedicated_errors(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        with pytest.raises(ComkenFileNotFoundError), CSV(path) as csv_file:
            csv_file.read()
        path.touch()
        with pytest.raises(CSVError), CSV(path) as csv_file:
            csv_file.read()
        with CSV(path, columns=["id"]) as csv_file:
            assert csv_file.read() == []

    def test_utf8_bom_only_has_missing_header_error(self, tmp_path) -> None:
        path = tmp_path / "bom_only.csv"
        path.write_bytes(b"\xef\xbb\xbf")
        with pytest.raises(CSVError), CSV(path) as csv_file:
            csv_file.read()

    def test_replace_empty_preserves_columns_or_requires_them(self, tmp_path) -> None:
        existing = tmp_path / "existing.csv"
        existing.write_text("id\n1\n", encoding="utf-8-sig")
        with CSV(existing) as csv_file:
            csv_file.replace([])
        assert existing.read_text(encoding="utf-8-sig") == "id\n"
        with pytest.raises(CSVError), CSV(tmp_path / "new.csv") as csv_file:
            csv_file.replace([])

    def test_read_outside_with_block_raises_table_not_open_error(self, tmp_path) -> None:
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="utf-8-sig")
        with pytest.raises(TableError, match="CSV"):
            CSV(path).read()
        with pytest.raises(TableError, match="CSV"):
            CSV(path).replace([{"id": "1"}])
        with pytest.raises(TableError, match="CSV"):
            CSV(path).save()
        with pytest.raises(TableError, match="CSV"):
            CSV(path).count()
        with pytest.raises(TableError, match="CSV"):
            CSV(path).iter_rows()

    def test_append_preserves_cp932_encoding(self, tmp_path) -> None:
        """CP932 の既存ファイルに追記しても CP932 のまま（BOM を付けない）。"""
        path = tmp_path / "history.csv"
        path.write_text("日付,備考\n2024-01-01,初期データ\n", encoding="cp932")
        with CSV(path) as csv_file:
            csv_file.append({"日付": "2024-01-02", "備考": "追記"})
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        # 全体を CP932 として復号でき、追記した行が含まれること。
        decoded = raw.decode("cp932")
        assert "初期データ" in decoded
        assert "追記" in decoded

    def test_append_preserves_utf8_bom(self, tmp_path) -> None:
        """UTF-8 BOM 付きの既存ファイルは BOM 付きのままで書き戻される。"""
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8-sig")
        with CSV(path) as csv_file:
            csv_file.append({"id": "2", "name": "鈴木"})
        raw = path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        assert raw.decode("utf-8-sig").splitlines()[0] == "id,name"
        assert "鈴木" in raw.decode("utf-8-sig")

    def test_append_preserves_utf8_without_bom(self, tmp_path) -> None:
        """BOM なし UTF-8 の既存ファイルは BOM を付けずに書き戻される。"""
        path = tmp_path / "data.csv"
        path.write_text("id,name\n1,山田\n", encoding="utf-8")
        with CSV(path) as csv_file:
            csv_file.append({"id": "2", "name": "鈴木"})
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert "鈴木" in raw.decode("utf-8")

    def test_replace_preserves_cp932_encoding(self, tmp_path) -> None:
        """``replace()`` も CP932 を保つ。"""
        path = tmp_path / "history.csv"
        path.write_text("日付,備考\n2024-01-01,初期データ\n", encoding="cp932")
        with CSV(path) as csv_file:
            csv_file.replace([{"日付": "2024-02-01", "備考": "置き換え"}])
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        decoded = raw.decode("cp932")
        assert "初期データ" not in decoded
        assert "置き換え" in decoded

    def test_new_file_written_with_utf8_bom(self, tmp_path) -> None:
        """新規ファイルは既定通り UTF-8 BOM 付きで書き出される。"""
        path = tmp_path / "new.csv"
        with CSV(path) as csv_file:
            csv_file.replace([{"id": "1", "name": "山田"}])
        raw = path.read_bytes()
        assert raw.startswith(b"\xef\xbb\xbf")
        assert path.read_text(encoding="utf-8-sig").splitlines()[0] == "id,name"

    def test_ascii_only_existing_file_falls_back_to_utf8_sig(self, tmp_path) -> None:
        """ASCII だけの既存ファイルに日本語を足すと、判定不能として ``utf-8-sig`` で書く。"""
        path = tmp_path / "ascii.csv"
        # ``id,value`` の ASCII だけの既存ファイル。判定不能なので既定の utf-8-sig に
        # フォールバックすることを確かめるため、日本語のセルを足して BOM が付くか確認する。
        path.write_text("id,value\n1,A\n", encoding="utf-8")
        with CSV(path) as csv_file:
            csv_file.append({"id": "2", "value": "B"})
            csv_file.append({"id": "3", "value": "山田"})
        raw = path.read_bytes()
        # ASCII だけだと判定不能なので、新規ファイルと同じ utf-8-sig (BOM 付き) で書く。
        assert raw.startswith(b"\xef\xbb\xbf")
        assert "山田" in raw.decode("utf-8-sig")

    def test_cp932_file_unrepresentable_char_raises_and_preserves_file(self, tmp_path) -> None:
        """CP932 既存ファイルに表せない文字（絵文字）を書くと例外、ファイルは無傷。"""
        path = tmp_path / "history.csv"
        original_bytes = "日付,備考\n2024-01-01,初期データ\n".encode("cp932")
        path.write_bytes(original_bytes)
        before = path.read_bytes()
        with (
            pytest.raises(InvalidTableInputError, match="cp932"),
            CSV(path) as csv_file,
        ):
            csv_file.append({"日付": "2024-01-02", "備考": "絵文字😀"})
        # 例外後はファイルが完全に元通り（``atomic_write`` が temp を片付けた）。
        assert path.read_bytes() == before

    def test_explicit_encoding_overrides_preservation(self, tmp_path) -> None:
        """``encoding=`` 明示時はその指定が最優先（既存ファイルの文字コードと無関係）。

        CP932（既定の ``AUTO`` 判定なら保持される）ASCII だけの既存ファイルに
        対して ``encoding="utf-8-sig`` を明示すると、保持せず BOM 付きで書く。
        """
        path = tmp_path / "data.csv"
        path.write_text("id\n1\n", encoding="cp932")
        with CSV(path, encoding="utf-8-sig") as csv_file:
            csv_file.append({"id": "2"})
        raw = path.read_bytes()
        # 明示 ``encoding="utf-8-sig"`` は既定判定を上書きして BOM を付ける。
        assert raw.startswith(b"\xef\xbb\xbf")

    def test_explicit_encoding_on_new_file(self, tmp_path) -> None:
        """新規ファイルでも ``encoding=`` 明示はそのまま使われる。"""
        path = tmp_path / "new.csv"
        with CSV(path, encoding="cp932") as csv_file:
            csv_file.replace([{"id": "1", "name": "山田"}])
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert "山田" in raw.decode("cp932")
