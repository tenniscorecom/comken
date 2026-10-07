"""comken/core/encoding.py のテスト。

文字コードの名前・別名・Windows コードページ番号をここで集中的に確かめる。
新しい文字コード・コードページを足したら、このファイルにも必ずケースを足す。
"""

import codecs

import pytest

from comken.core.encoding import CP932, UTF8, UTF8_SIG, code_page, normalize_encoding


class TestNormalizeEncoding:
    """normalize_encoding（文字コード名の正規化）のテスト。"""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("UTF-8", "utf-8"),
            ("utf_8", "utf-8"),
            ("  utf-8-sig  ", "utf-8-sig"),
            ("utf8", "utf-8"),
            ("utf8-sig", "utf-8-sig"),
            ("utf-8-bom", "utf-8-sig"),
            ("sjis", "cp932"),
            ("Shift_JIS", "cp932"),
            ("shift-jis", "cp932"),
            ("shiftjis", "cp932"),
            ("windows-31j", "cp932"),
            ("MS932", "cp932"),
            ("mskanji", "cp932"),
            ("ms-kanji", "cp932"),
            ("CP932", "cp932"),
            ("utf-8-sig", "utf-8-sig"),
        ],
    )
    def test_normalizes_known_aliases(self, raw: str, expected: str) -> None:
        """表記ゆれを正規の codec 名へそろえることを確認する。"""
        assert normalize_encoding(raw) == expected

    def test_returns_known_codec_as_lowercase_dash_form(self) -> None:
        """別名対応に無い既知の codec は正規化してそのまま返す。"""
        assert normalize_encoding("EUC-JP") == "euc-jp"

    def test_rejects_unknown_name_with_helpful_message(self) -> None:
        """未知の名前は ``ValueError``、対処法の文言を含む。"""
        with pytest.raises(ValueError, match="省略すると自動判定"):
            normalize_encoding("foo")

    def test_rejects_auto_string_as_unknown(self) -> None:
        """``"auto"`` は特別扱いせず未知の名前として ``ValueError``。"""
        with pytest.raises(ValueError, match="省略すると自動判定"):
            normalize_encoding("auto")


class TestNormalizeEncodingExtended:
    """``codecs.lookup`` 経由で吸収する別名まわりのテスト。"""

    def test_windows_code_page_number_maps_to_cp932(self) -> None:
        """Windows コードページ番号 ``932`` は ``cp932`` へ正規化される。

        Python 3.14 以降の ``codecs.lookup`` が ``"932"`` を ``cp932`` として
        受け付けるため、``normalize_encoding`` は ``codecs.lookup`` 経由でこの
        表記を吸収する。
        """
        # Python が ``932`` を codec として受け付けない環境では、このテストは
        # 想定外なので ``pytest.skip`` で逃げる。
        try:
            codecs.lookup("932")
        except LookupError:
            pytest.skip("この Python は codecs.lookup('932') を受け付けない")
        assert normalize_encoding("932") == "cp932"

    def test_utf_8_sig_with_underscore_maps_to_utf_8_sig(self) -> None:
        """``UTF_8_SIG`` は ``_`` → ``-`` の正規化で ``utf-8-sig`` へそろう。"""
        assert normalize_encoding("UTF_8_SIG") == "utf-8-sig"

    def test_utf_8_bom_maps_to_utf_8_sig(self) -> None:
        """``utf-8-bom`` は Python の codec に存在しないため ``utf-8-sig`` に寄せる。"""
        assert normalize_encoding("utf-8-bom") == "utf-8-sig"

    def test_latin1_returns_lowercase_dash_form(self) -> None:
        """``latin-1`` は正規化（小文字・``-`` 区切り）のまま返す（cp932 等に寄せない）。"""
        assert normalize_encoding("latin-1") == "latin-1"


class TestConstants:
    """``comken.core.encoding`` の公開定数が Python の codec として有効であること。"""

    @pytest.mark.parametrize("name", [CP932, UTF8, UTF8_SIG])
    def test_constants_are_valid_codecs(self, name: str) -> None:
        """公開定数が ``codecs.lookup`` で解決でき、名前が一致する。"""
        assert codecs.lookup(name).name == name


class TestCodePage:
    """``code_page`` のテスト（Windows コードページ番号を返す）。"""

    def test_cp932_returns_932(self) -> None:
        """``cp932`` は Windows の 932。"""
        assert code_page("cp932") == 932

    def test_sjis_returns_932(self) -> None:
        """``sjis`` は別名吸収のうえで Windows の 932。"""
        assert code_page("sjis") == 932

    def test_utf_8_sig_returns_65001(self) -> None:
        """``utf-8-sig`` は Windows の 65001。"""
        assert code_page("utf-8-sig") == 65001

    def test_utf8_sig_returns_65001(self) -> None:
        """``utf8-sig`` は別名吸収のうえで Windows の 65001。"""
        assert code_page("utf8-sig") == 65001

    def test_utf_8_without_bom_raises_value_error(self) -> None:
        """Access は BOM なし UTF-8 を直接扱えないため ``ValueError``。"""
        with pytest.raises(ValueError, match="次から指定してください"):
            code_page("utf-8")

    def test_unknown_encoding_raises_value_error(self) -> None:
        """``euc-jp`` は ``code_page`` の表に無く ``ValueError``。"""
        with pytest.raises(ValueError, match="次から指定してください"):
            code_page("euc-jp")
