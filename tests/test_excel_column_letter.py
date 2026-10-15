"""comken.toolbox.excel.column_letter のテスト。

``col_to_num()`` の逆関数が正しく働くか確認する。Excel の列は A 始まりの
26進数で、``Z`` の次は ``AA``。1始まりで ``703`` は ``AAA``。
境界（``1`` / ``26`` / ``27`` / ``702`` / ``703``）と1桁／2桁／3桁の切り替わりを
押さえる。
"""

import pytest

from comken.toolbox.excel import column_letter


class TestKnownValues:
    def test_first_column(self) -> None:
        """1 は "A"。"""
        assert column_letter(1) == "A"

    def test_last_single_letter_column(self) -> None:
        """26 は "Z"。"""
        assert column_letter(26) == "Z"

    def test_first_two_letter_column(self) -> None:
        """27 は "AA"。Z の次が AA になることを確認する。"""
        assert column_letter(27) == "AA"

    def test_az_is_52(self) -> None:
        """52 は "AZ"。2桁の境目。"""
        assert column_letter(52) == "AZ"

    def test_last_two_letter_column(self) -> None:
        """702 は "ZZ"。"""
        assert column_letter(702) == "ZZ"

    def test_first_three_letter_column(self) -> None:
        """703 は "AAA"。ZZ の次が AAA になることを確認する。"""
        assert column_letter(703) == "AAA"


class TestTwoLetterRange:
    """2桁の範囲の代表値を ``A=1`` 起点で確認する。"""

    @pytest.mark.parametrize(
        ("index", "expected"),
        [
            (1, "A"),
            (2, "B"),
            (3, "C"),
            (4, "D"),
            (10, "J"),
            (26, "Z"),
            (27, "AA"),
            (28, "AB"),
            (52, "AZ"),
            (53, "BA"),
            (54, "BB"),
            (701, "ZY"),
            (702, "ZZ"),
        ],
    )
    def test_known_letters(self, index: int, expected: str) -> None:
        assert column_letter(index) == expected


class TestThreeLetterRange:
    """3桁の範囲で ``703`` が ``AAA``、それから先も順調に伸びることを確認する。"""

    @pytest.mark.parametrize(
        ("index", "expected"),
        [
            (703, "AAA"),
            (704, "AAB"),
            (728, "AAZ"),
            (729, "ABA"),
            (18278, "ZZZ"),  # 26^3
        ],
    )
    def test_known_letters(self, index: int, expected: str) -> None:
        assert column_letter(index) == expected


class TestInvalidValues:
    """0 以下は ValueError。"""

    def test_zero_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1以上"):
            column_letter(0)

    def test_negative_raises(self) -> None:
        with pytest.raises(ValueError, match=r"1以上"):
            column_letter(-1)

    def test_large_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            column_letter(-100)


class TestRoundTripWithColToNum:
    """``col_to_num()`` と組み合わせて往復しても整合するか確認する。

    片方向だけだと境界条件で桁上がりを見落とすので、
    ``col_to_num(column_letter(n)) == n`` を広い範囲で回して確認する。
    """

    @pytest.mark.parametrize(
        "index",
        [1, 9, 10, 26, 27, 52, 100, 500, 702, 703, 1000, 18278],
    )
    def test_round_trip(self, index: int) -> None:
        from comken.core.columns import col_to_num

        assert col_to_num(column_letter(index)) == index
