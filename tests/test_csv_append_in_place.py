"""CSV の追記が、既存ファイルの末尾へ書き足すだけで済む経路の契約を確かめる。

見出しの文字コードが決まるファイル（BOM 付き UTF-8、見出しに日本語がある UTF-8 / CP932）
への ``append`` は、ファイルの中身を全件読まず・全件書き直さず、確定のときに末尾へ足す。
それ以外（``columns=`` / ``types=`` の指定、見出しが ASCII だけで BOM も無いファイル、
``encoding=`` の明示が違う、空のファイル）は、従来どおり全件を読んで書き直す。
"""

import csv
import io
from unittest.mock import patch

import pytest

from comken.exceptions import CSVError, InvalidTableInputError, TableError
from comken.toolbox.csv import CSV
from comken.toolbox.csv import file as csv_file_module

TRICKY = [
    {"id": "1", "name": "山田, 太郎", "memo": '引用"あり'},
    {"id": "2", "name": "鈴木", "memo": "改行\nあり"},
    {"id": "3", "name": "", "memo": "すこし 長い 値"},
]


def _write(path, rows, *, encoding, header=("id", "name", "memo"), newline="\r\n") -> None:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerow(header)
    writer.writerows(rows)
    path.write_bytes(buffer.getvalue().encode(encoding))


def _append(path, rows, **kwargs) -> None:
    with CSV(path, **kwargs) as csv_file:
        csv_file.append(rows)


def _parsed(path, encoding) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_bytes().decode(encoding), newline="")))


@pytest.fixture
def slow_path():
    """足すだけの経路を使わせない（従来の全件書き直しの結果と比べるため）。"""
    with patch.object(CSV, "_plan_in_place_append", return_value=None):
        yield


class TestAppendInPlace:
    @pytest.mark.parametrize(
        ("encoding", "label"),
        [("utf-8-sig", "BOM 付き UTF-8"), ("utf-8", "BOM なし UTF-8"), ("cp932", "CP932")],
    )
    def test_bytes_are_identical_to_full_rewrite(self, tmp_path, encoding, label) -> None:
        """見出しの文字コードが決まるファイルでは、足すだけの結果が全件書き直しと同じバイト列になる。"""
        fast = tmp_path / "fast.csv"
        slow = tmp_path / "slow.csv"
        for path in (fast, slow):
            _write(path, [["10", "既存", "x"]], encoding=encoding, header=("id", "名前", "memo"))
        additions = [
            {"id": "1", "名前": "山田, 太郎", "memo": '引用"あり'},
            {"id": "2", "名前": "鈴木", "memo": "改行\nあり"},
        ]
        _append(fast, additions)
        with patch.object(CSV, "_plan_in_place_append", return_value=None):
            _append(slow, additions)

        assert fast.read_bytes() == slow.read_bytes(), label

    def test_does_not_read_or_rewrite_whole_file(self, tmp_path) -> None:
        """全件を読まず、一時ファイルへの全件書き直し（atomic_write）もしない。"""
        path = tmp_path / "log.csv"
        _write(path, [[str(i), "n", "m"] for i in range(2000)], encoding="utf-8-sig")
        with (
            patch.object(CSV, "read", side_effect=AssertionError("全件を読んではいけない")),
            patch.object(csv_file_module, "atomic_write", side_effect=AssertionError("書き直し")),
        ):
            _append(path, {"id": "x", "name": "新規", "memo": "m"})

        rows = _parsed(path, "utf-8-sig")
        assert len(rows) == 2002
        assert rows[-1] == ["x", "新規", "m"]

    def test_existing_bytes_are_left_untouched(self, tmp_path) -> None:
        """既存の行は 1 バイトも書き換えない（末尾に足すだけ）。"""
        path = tmp_path / "log.csv"
        # 全件を書き直すと変わってしまう書き方（不要な引用符・LF 改行）を、わざと入れておく
        original = '"id","name","memo"\n1,"山田",x\n'.encode("utf-8-sig")
        path.write_bytes(original)
        _append(path, {"id": "2", "name": "鈴木", "memo": "y"})

        assert path.read_bytes().startswith(original)
        # 既存の改行（LF）に合わせて足す
        assert path.read_bytes() == original + "2,鈴木,y\n".encode()

    def test_adds_terminator_when_last_line_is_unterminated(self, tmp_path) -> None:
        """前回の書き込みが途中で切れて末尾が改行で終わっていないときは、改行を足してから書く。"""
        path = tmp_path / "log.csv"
        path.write_bytes("id,name,memo\r\n1,山田,x".encode("utf-8-sig"))
        _append(path, {"id": "2", "name": "鈴木", "memo": "y"})

        assert _parsed(path, "utf-8-sig") == [
            ["id", "name", "memo"],
            ["1", "山田", "x"],
            ["2", "鈴木", "y"],
        ]

    def test_several_appends_are_written_once(self, tmp_path) -> None:
        """with の中で何度 append しても、確定は 1 回で、順序も保たれる。"""
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        with patch.object(
            csv_file_module.CSV, "_flush_appended", autospec=True, side_effect=CSV._flush_appended
        ) as flush:
            with CSV(path) as csv_file:
                csv_file.append({"id": "1", "name": "a", "memo": ""})
                csv_file.append([{"id": "2", "name": "b", "memo": ""}])
                csv_file.append({"id": "3", "name": "c", "memo": ""})
            assert flush.call_count == 1

        assert [row[0] for row in _parsed(path, "utf-8-sig")] == ["id", "0", "1", "2", "3"]

    def test_save_in_the_middle_then_more_appends(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        with CSV(path) as csv_file:
            csv_file.append({"id": "1", "name": "a", "memo": ""})
            csv_file.save()
            assert [row[0] for row in _parsed(path, "utf-8-sig")] == ["id", "0", "1"]
            csv_file.append({"id": "2", "name": "b", "memo": ""})

        assert [row[0] for row in _parsed(path, "utf-8-sig")] == ["id", "0", "1", "2"]

    def test_nothing_is_written_when_the_with_block_raises(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        before = path.read_bytes()
        with pytest.raises(RuntimeError), CSV(path) as csv_file:
            csv_file.append({"id": "1", "name": "a", "memo": ""})
            raise RuntimeError("途中で失敗")

        assert path.read_bytes() == before

    def test_dry_run_writes_nothing(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        before = path.read_bytes()
        _append(path, {"id": "1", "name": "a", "memo": ""}, dry_run=True)

        assert path.read_bytes() == before

    def test_read_after_append_returns_existing_and_added_rows(self, tmp_path) -> None:
        """追記のあとの read() は「ファイルの中身 + 足した行」を返す（そこで初めて全件を読む）。"""
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        with CSV(path) as csv_file:
            csv_file.append({"id": "1", "name": "a", "memo": ""})
            table = csv_file.read()
            assert [row["id"] for row in table.to_rows()] == ["0", "1"]
            assert csv_file.count() == 2
            assert [row["id"] for row in csv_file.iter_rows()] == ["0", "1"]
        assert [row[0] for row in _parsed(path, "utf-8-sig")] == ["id", "0", "1"]

    def test_replace_after_append_replaces_everything(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        with CSV(path) as csv_file:
            csv_file.append({"id": "1", "name": "a", "memo": ""})
            csv_file.replace([{"id": "9", "name": "z", "memo": ""}])

        assert _parsed(path, "utf-8-sig") == [["id", "name", "memo"], ["9", "z", ""]]

    def test_unencodable_character_raises_and_keeps_file(self, tmp_path) -> None:
        """CP932 のファイルに、CP932 で表せない文字を足そうとすると止まり、ファイルは無傷。"""
        path = tmp_path / "log.csv"
        _write(path, [["0", "既存", "m"]], encoding="cp932", header=("id", "名前", "memo"))
        before = path.read_bytes()
        with pytest.raises(InvalidTableInputError), CSV(path) as csv_file:
            csv_file.append({"id": "1", "名前": "絵文字😀", "memo": ""})

        assert path.read_bytes() == before

    def test_unknown_column_is_rejected_at_append(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        _write(path, [["0", "n", "m"]], encoding="utf-8-sig")
        with CSV(path) as csv_file, pytest.raises(TableError):
            csv_file.append({"id": "1", "name": "a", "memo": "", "typo": "x"})


class TestFallsBackToFullRewrite:
    """足すだけの経路を使えない場合は、従来どおり全件を読んで書き直す。"""

    def test_ascii_only_header_without_bom_is_normalised_to_utf8_bom(self, tmp_path) -> None:
        path = tmp_path / "log.csv"
        path.write_bytes(b"id,name\r\n1,a\r\n")
        _append(path, {"id": "2", "name": "b"})

        assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    def test_types_are_applied_to_existing_rows(self, tmp_path) -> None:
        """``types=`` を指定したときは、既存の行にも変換がかかる（従来の挙動）。"""
        path = tmp_path / "log.csv"
        _write(path, [["01", "n", "m"]], encoding="utf-8-sig")
        with CSV(path, types={"id": int}) as csv_file:
            csv_file.append({"id": "2", "name": "b", "memo": ""})

        assert [row[0] for row in _parsed(path, "utf-8-sig")] == ["id", "1", "2"]

    def test_explicit_encoding_that_differs_stops_instead_of_appending(self, tmp_path) -> None:
        """ファイルと違う ``encoding=`` を明示したら、従来どおり読み込みで止まる。

        別の文字コードの行を足して、1 つのファイルに 2 つの文字コードが混ざることはない。
        """
        path = tmp_path / "log.csv"
        _write(path, [["0", "既存", "m"]], encoding="utf-8-sig", header=("id", "名前", "memo"))
        before = path.read_bytes()
        with pytest.raises(CSVError), CSV(path, encoding="cp932") as csv_file:
            csv_file.append({"id": "1", "名前": "新規", "memo": ""})

        assert path.read_bytes() == before

    def test_columns_argument_uses_the_old_path(self, tmp_path) -> None:
        """``columns=`` は「見出しの無いファイル」の指定なので、足すだけの経路には入らない。"""
        path = tmp_path / "log.csv"
        path.write_bytes("1,a\r\n".encode("utf-8-sig"))
        with CSV(path, columns=["id", "name"]) as csv_file:
            csv_file.append({"id": "2", "name": "b"})

        assert _parsed(path, "utf-8-sig") == [["id", "name"], ["1", "a"], ["2", "b"]]
