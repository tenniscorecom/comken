"""``comken.core.text.normalize``（比較のための正規化）のテスト。"""

import pytest

from comken.core.table import Table
from comken.core.text import normalize


class TestNormalize:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, ""),
            ("ＡＢＣ１２３", "ABC123"),  # 全角英数 → 半角
            ("ｶﾞ", "ガ"),  # 半角カナ → 全角カナ
            ("カナ", "カナ"),  # 全角カナはそのまま（Excel の ASC とは違う）
            ("㈱山田①", "(株)山田1"),  # 合字・丸数字は展開
            ("　山田 ", "山田"),  # 全角空白・前後の空白
            (1000.0, "1000"),  # 整数値の小数は整数に
            (1000, "1000"),
            (0.5, "0.5"),
            ("1000", "1000"),
            ("0001", "0001"),  # 先頭ゼロの文字列は数値にしない
            (0, "0"),
            (False, "False"),
        ],
    )
    def test_known_values(self, value: object, expected: str) -> None:
        assert normalize(value) == expected

    def test_csv_string_and_excel_number_become_equal(self) -> None:
        assert normalize("1001") == normalize(1001) == normalize(1001.0)

    def test_nan_and_inf_are_not_treated_as_integers(self) -> None:
        assert normalize(float("nan")) == "nan"
        assert normalize(float("inf")) == "inf"


class TestDiffUsesNormalize:
    def test_full_width_and_half_width_values_are_not_a_difference(self) -> None:
        before = Table(["id", "name"], [{"id": "1", "name": "ＡＢＣ"}])
        after = Table(["id", "name"], [{"id": "1", "name": "ABC"}])

        assert before.diff(after, key="id").changed.to_rows() == []

    def test_keys_are_matched_after_normalize(self) -> None:
        before = Table(["id", "name"], [{"id": "Ａ１", "name": "x"}])
        after = Table(["id", "name"], [{"id": "A1", "name": "y"}])

        changed = before.diff(after, key="id").changed.to_rows()

        assert changed == [{"id": "A1", "列": "name", "変更前": "x", "変更後": "y"}]
