"""comken/services/salesforce_downloader/contract のテスト。

soql-collector（書き手）とダウンローダー（読み手）の共有契約が
``contract.py`` 1 か所で定義されていることを担保する。

- 未完成 SOQL の印（``INCOMPLETE_MARKER_PREFIX`` / ``INCOMPLETE_MARKER``）が
  検知側と書き手の両方の視点で矛盾していないこと
- 列名の対応.csv の列がここ 1 か所で定義され、 ``COLUMN_NAMES_CSV_COLUMNS`` の
  ``,`` 連結と CSV の 1 行目が一致すること
- バイト単位の見本が BOM 付き UTF-8 + CRLF で読み出せ、1 行目が ``INCOMPLETE_MARKER_PREFIX``
  で始まること（実物の見本は手書きの ``【未完成】ここから下を補ってください`` のように、
  PREFIX だけで全文 ``INCOMPLETE_MARKER`` を含まない）
- 存在しない名前を渡すと ``ComkenFileNotFoundError`` 相当の例外で止まり、
  メッセージに使える名前の一覧が含まれること
"""

import pytest

from comken.exceptions import ComkenError, ComkenFileNotFoundError
from comken.services.salesforce_downloader.contract import (
    COLUMN_NAMES_CSV_COLUMNS,
    INCOMPLETE_MARKER,
    INCOMPLETE_MARKER_PREFIX,
    load_sample,
)


class TestIncompleteMarker:
    """未完成 SOQL の印は検知側（先頭一致）と書き手（全文）が矛盾しない。"""

    def test_marker_starts_with_prefix(self) -> None:
        """``INCOMPLETE_MARKER`` は ``INCOMPLETE_MARKER_PREFIX`` で始まる（検知側の前提）。"""
        assert INCOMPLETE_MARKER.startswith(INCOMPLETE_MARKER_PREFIX)

    def test_marker_is_prefix_plus_suffix(self) -> None:
        """``INCOMPLETE_MARKER`` は接頭辞＋本文で、 ``INCOMPLETE_MARKER`` の全文は固定値。"""
        # 全文が変わると見本ファイルとの一致も壊れるので、文字列そのものを固定する。
        assert INCOMPLETE_MARKER == (
            INCOMPLETE_MARKER_PREFIX + "作れなかった部分があります。このままでは実行できません。"
        )

    def test_marker_prefix_is_distinct_from_marker(self) -> None:
        """接頭辞と全文が同じだと先頭一致の意味が無い。 接頭辞は本文より短い。"""
        assert len(INCOMPLETE_MARKER_PREFIX) < len(INCOMPLETE_MARKER)


class TestColumnNamesCsvColumns:
    """列名の対応.csv の列は ``contract.py`` 1 か所で定義される。"""

    def test_columns_are_tuple(self) -> None:
        """並びと要素数は出力ファイルそのもの。 tuple で固定する。"""
        assert COLUMN_NAMES_CSV_COLUMNS == (
            "主オブジェクト",
            "SOQL列名",
            "表示名",
            "備考",
            "更新日",
        )

    def test_columns_have_five_entries(self) -> None:
        """列数は 5 で固定（``列名の対応.csv`` の仕様）。"""
        assert len(COLUMN_NAMES_CSV_COLUMNS) == 5


class TestLoadSample:
    """``load_sample()`` はバイト単位の見本を取り出す。"""

    def test_incomplete_soql_sample_first_line_starts_with_prefix(self) -> None:
        """見本 TXT の 1 行目は ``INCOMPLETE_MARKER_PREFIX`` で始まる。

        実物の見本ファイルは手書きの ``【未完成】ここから下を補ってください`` のように
        PREFIX だけで ``INCOMPLETE_MARKER`` の全文（接頭辞＋本文）を含まないため、
        全文一致ではなく先頭一致で検証する。
        改行コード ``\\r\\n`` が混ざるので、 ``splitlines()`` ではなく
        ``split(b"\\r\\n")`` で先頭を取り出す。
        """
        raw = load_sample("未完成のSOQL.contract.txt")
        first_line = raw.split(b"\r\n", 1)[0]

        # ``INCOMPLETE_MARKER_PREFIX`` は str なので encode してバイト列と直接比較する
        assert first_line.startswith(INCOMPLETE_MARKER_PREFIX.encode("utf-8"))

    def test_column_names_sample_starts_with_bom_and_crfl(self) -> None:
        """見本 CSV は BOM 付き UTF-8・CRLF で、 1 行目が ``COLUMN_NAMES_CSV_COLUMNS`` の
        ``,`` 連結と一致する。
        """
        raw = load_sample("列名の対応.contract.csv")
        first_line = raw.split(b"\r\n", 1)[0]

        assert raw.startswith(b"\xef\xbb\xbf"), "BOM 付き UTF-8 ではない"
        assert b"\r\n" in raw, "CRLF 改行ではない"
        expected_first_line = b"\xef\xbb\xbf" + b",".join(
            col.encode("utf-8") for col in COLUMN_NAMES_CSV_COLUMNS
        )
        assert first_line == expected_first_line

    def test_column_names_sample_first_line_without_bom_equals_columns_csv(self) -> None:
        """BOM を除いた 1 行目が ``COLUMN_NAMES_CSV_COLUMNS`` の CSV 文字列と一致する
        （業務側の CSV パーサが BOM を読む前提でも、列検証は BOM 抜きで行えることを保証）。
        """
        raw = load_sample("列名の対応.contract.csv")
        # BOM を除いた 1 行目を文字列として取り出す
        without_bom = raw.removeprefix(b"\xef\xbb\xbf")
        first_line = without_bom.split(b"\r\n", 1)[0].decode("utf-8")

        expected = ",".join(COLUMN_NAMES_CSV_COLUMNS)
        assert first_line == expected

    def test_raises_for_unknown_name_with_available_list(self) -> None:
        """存在しない名前で ``ComkenFileNotFoundError`` 相当の例外。

        メッセージに使える名前の一覧を入れて、 業務担当者が直感で次に打てる名前へ
        たどれるようにする。
        """
        with pytest.raises(ComkenFileNotFoundError) as excinfo:
            load_sample("存在しない.contract.txt")

        message = str(excinfo.value)
        # 例外は comken の例外階層（ComkenError）にも入っているので、
        # 既存の try/except ComkenError でも受け取れる。
        assert isinstance(excinfo.value, ComkenError)
        # メッセージに「存在しない.contract.txt」と、 どちらかの既存ファイル名が
        # 含まれていること（業務担当者がファイル名を見て直せること）。
        assert "存在しない.contract.txt" in message
        assert "未完成のSOQL.contract.txt" in message or "列名の対応.contract.csv" in message
