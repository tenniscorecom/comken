"""comken/toolbox/salesforce/soql.py のテスト。

組み立てた文字列だけを確かめる（通信はしない）。値の取り違えと識別子の検査が
「止まる」ことを確かめられるよう、期待する文字列を必ず全文で書いて照合する。
"""

import math
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from comken.exceptions import ComkenError, SalesforceError, SoqlBuildError
from comken.toolbox.salesforce.soql import (
    LAST_MONTH,
    LAST_WEEK,
    LAST_YEAR,
    NEXT_MONTH,
    NEXT_WEEK,
    NEXT_YEAR,
    THIS_MONTH,
    THIS_QUARTER,
    THIS_WEEK,
    THIS_YEAR,
    TODAY,
    TOMORROW,
    YESTERDAY,
    DateLiteral,
    Soql,
    last_n_days,
    last_n_months,
    last_n_weeks,
    last_n_years,
    next_n_days,
    next_n_months,
    next_n_weeks,
    next_n_years,
)

JST = timezone(timedelta(hours=9))
ALL_DATE_CONSTANTS = [
    TODAY,
    YESTERDAY,
    TOMORROW,
    THIS_WEEK,
    LAST_WEEK,
    NEXT_WEEK,
    THIS_MONTH,
    LAST_MONTH,
    NEXT_MONTH,
    THIS_QUARTER,
    LAST_YEAR,
    NEXT_YEAR,
    THIS_YEAR,
]


class TestBasicShape:
    """基本形。ドキュメントに書いた例がそのまま出ることを確かめる。"""

    def test_example_builds_expected_string(self) -> None:
        soql = (
            Soql("Opportunity")
            .where("CloseDate", ">=", last_n_days(30))
            .where("StageName", "=", "Closed Won")
            .select("Id", "Name", "Amount")
            .order_by("Amount", desc=True)
            .limit(100)
            .build()
        )
        assert soql == (
            "SELECT Id, Name, Amount FROM Opportunity WHERE CloseDate >= LAST_N_DAYS:30 "
            "AND StageName = 'Closed Won' ORDER BY Amount DESC LIMIT 100"
        )

    def test_order_of_calls_does_not_matter(self) -> None:
        written = (
            Soql("Opportunity")
            .where("CloseDate", ">=", last_n_days(30))
            .where("StageName", "=", "Closed Won")
            .select("Id", "Name", "Amount")
            .order_by("Amount", desc=True)
            .limit(100)
            .build()
        )
        # 句（WHERE の中の条件どうしの順番は保つ）の並べ替えだけを変えたもの
        shuffled = (
            Soql("Opportunity")
            .limit(100)
            .order_by("Amount", desc=True)
            .select("Id", "Name", "Amount")
            .where("CloseDate", ">=", last_n_days(30))
            .where("StageName", "=", "Closed Won")
            .build()
        )
        assert shuffled == written

    def test_str_is_the_same_as_build(self) -> None:
        query = Soql("Account").select("Id").where("Name", "=", "x")
        assert str(query) == query.build()

    def test_select_is_required(self) -> None:
        with pytest.raises(SoqlBuildError, match="SELECT"):
            Soql("Opportunity").where("Name", "=", "x").build()


class TestImmutability:
    """``Soql`` は不変。途中のオブジェクトを使い回して別の枝を作れる。"""

    def test_methods_do_not_change_the_original(self) -> None:
        base = Soql("Opportunity").select("Id")
        base.select("Name")
        base.where("StageName", "=", "Closed Won")
        base.limit(10)
        assert base.build() == "SELECT Id FROM Opportunity"

    def test_branching_from_a_shared_base(self) -> None:
        base = Soql("Opportunity").select("Id", "Name")
        won = base.where("StageName", "=", "Closed Won").limit(10).build()
        lost = base.where("StageName", "=", "Closed Lost").build()

        assert won == "SELECT Id, Name FROM Opportunity WHERE StageName = 'Closed Won' LIMIT 10"
        assert lost == "SELECT Id, Name FROM Opportunity WHERE StageName = 'Closed Lost'"
        assert base.build() == "SELECT Id, Name FROM Opportunity"

    def test_repeated_calls_return_equal_but_separate_objects(self) -> None:
        query = Soql("Account").select("Id")
        again = query.select("Name")
        assert again == query.select("Name")
        assert again is not query


class TestClauses:
    """各句の追加のされ方。"""

    def test_select_appends_in_called_order_and_deduplicates(self) -> None:
        query = Soql("Account").select("Id", "Name").select("Name", "Amount").select("Id").build()
        assert query == "SELECT Id, Name, Amount FROM Account"

    def test_limit_takes_the_last_value(self) -> None:
        assert Soql("Account").select("Id").limit(50).limit(10).build().endswith("LIMIT 10")

    def test_limit_zero_is_allowed(self) -> None:
        assert Soql("Account").select("Id").limit(0).build().endswith("LIMIT 0")

    @pytest.mark.parametrize("count", [-1, 1.0, True, "10"])
    def test_limit_rejects_non_counts(self, count: object) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").limit(count)  # type: ignore[arg-type]

    def test_multiple_where_are_joined_with_and(self) -> None:
        query = Soql("Account").select("Id").where("Name", "=", "a").where("Type", "=", "b").build()
        assert query == "SELECT Id FROM Account WHERE Name = 'a' AND Type = 'b'"

    def test_multiple_order_by_keep_called_order(self) -> None:
        query = (
            Soql("Account").select("Id").order_by("Name").order_by("CreatedDate", desc=True).build()
        )
        assert query.endswith("ORDER BY Name, CreatedDate DESC")

    def test_group_by(self) -> None:
        query = Soql("Opportunity").select("StageName", "COUNT(Id)").group_by("StageName").build()
        assert query == "SELECT StageName, COUNT(Id) FROM Opportunity GROUP BY StageName"


class TestIdentifierChecks:
    """識別子（オブジェクト名・項目名）と SELECT の式の検査。"""

    def test_related_field_and_custom_field_pass(self) -> None:
        query = (
            Soql("Account").select("Id", "Account.Name", "Owner.Profile.Name", "Custom__c").build()
        )
        assert query == "SELECT Id, Account.Name, Owner.Profile.Name, Custom__c FROM Account"

    @pytest.mark.parametrize(
        "name",
        ["Id; DELETE", "Name--", "Name/*x*/", "Name)", "  ", "1abc", "Name Name", ""],
    )
    def test_bad_select_field_is_rejected(self, name: str) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select(name)

    @pytest.mark.parametrize("name", ["Id; DELETE", "Name--", "Name)", "1Name", ""])
    def test_bad_object_name_is_rejected(self, name: str) -> None:
        with pytest.raises(SoqlBuildError):
            Soql(name).select("Id")

    def test_bad_where_field_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name)", "=", "x")

    def test_bad_group_by_field_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").group_by("Name)")

    def test_bad_order_by_field_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").order_by("Name)")


class TestAggregation:
    """集計関数と別名。"""

    @pytest.mark.parametrize(
        "expression",
        [
            "COUNT()",
            "COUNT(Id)",
            "COUNT_DISTINCT(Id)",
            "SUM(Amount)",
            "AVG(Amount)",
            "MIN(Amount)",
            "MAX(Amount)",
        ],
    )
    def test_aggregation_expressions_pass(self, expression: str) -> None:
        assert Soql("Opportunity").select(expression).build() == (
            f"SELECT {expression} FROM Opportunity"
        )

    def test_alias_after_space_passes(self) -> None:
        query = Soql("Opportunity").select("SUM(Amount) total").build()
        assert query == "SELECT SUM(Amount) total FROM Opportunity"

    @pytest.mark.parametrize(
        "expression",
        [
            "SUM(Amount) total, x",
            "SUM(1)",
            "SUM()",
            "COUNT(Id) --x",
            "COUNT(Id); DELETE",
            "(SELECT Id FROM Account)",
            "Id --",
        ],
    )
    def test_non_aggregation_expressions_are_rejected(self, expression: str) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Opportunity").select(expression)


def _unescaped_quotes(text: str) -> int:
    """バックスラッシュでエスケープされていない `'` の個数。

    SOQL の文字列リテラルは 1 つにつき「開き + 閉じ」の 2 個なので、これが 2 なら
    リテラルは途中で閉じておらず、値の中の `'` がクエリに混ざっていないことを示す。
    """
    return len(re.findall(r"(?<!\\)'", text))


class TestStringEscaping:
    """文字列値のエスケープ。出力の SOQL が壊れないことを文字列として確かめる。"""

    def _where(self, value: object, operator: str = "=") -> str:
        return Soql("Account").select("Id").where("Name", operator, value).build()

    # 期待値は `\\'` が入れ子になるので raw 文字列で書く（r"..." の中の \ はそのまま 1 個の文字）。
    def test_quote_is_escaped_and_literal_stays_closed(self) -> None:
        built = self._where("O'Brien")
        assert built == r"SELECT Id FROM Account WHERE Name = 'O\'Brien'"
        # バックスラッシュ以外の引用符は 2 個だけ = 文字列リテラルは 1 つで閉じている
        assert _unescaped_quotes(built) == 2

    def test_injection_attempt_cannot_add_a_second_condition(self) -> None:
        built = self._where("' OR Name != '")
        assert built == r"SELECT Id FROM Account WHERE Name = '\' OR Name != \''"
        # 値の中の ' はどちらもエスケープ済み。リテラルは 1 つだけで閉じる
        assert _unescaped_quotes(built) == 2
        # 値の中の OR / != がクエリの演算子にはなっていない（演算子は最初の `= ` の 1 つだけ）
        assert " AND " not in built
        assert built.index("!=") > built.index("= '")

    def test_backslash_is_escaped(self) -> None:
        assert self._where("a\\b") == r"SELECT Id FROM Account WHERE Name = 'a\\b'"

    def test_double_quote_is_escaped(self) -> None:
        assert self._where('say "hi"') == r"SELECT Id FROM Account WHERE Name = 'say \"hi\"'"

    def test_control_characters_are_escaped(self) -> None:
        built = self._where("a\nb\r\tc\bd\fe")
        assert built == "SELECT Id FROM Account WHERE Name = 'a\\nb\\r\\tc\\bd\\fe'"
        # 生の改行などが SOQL の中へ混ざらない
        assert "\n" not in built

    def test_like_wildcards_are_passed_through(self) -> None:
        assert self._where("A%B_C", operator="LIKE") == (
            "SELECT Id FROM Account WHERE Name LIKE 'A%B_C'"
        )

    def test_like_quote_is_still_escaped(self) -> None:
        assert self._where("50%_O'x", operator="LIKE").endswith(r"LIKE '50%_O\'x'")

    def test_quotes_inside_in_list_are_escaped(self) -> None:
        assert self._where(["a'b", 'c"d'], operator="IN") == (
            r"SELECT Id FROM Account WHERE Name IN ('a\'b', 'c\"d')"
        )


class TestValueTypes:
    """値の型ごとの出力。"""

    def test_bool_is_rendered_as_true_false(self) -> None:
        built = Soql("Account").select("Id").where("IsDeleted", "=", True).build()
        assert built == "SELECT Id FROM Account WHERE IsDeleted = true"
        built = Soql("Account").select("Id").where("IsDeleted", "=", False).build()
        assert built == "SELECT Id FROM Account WHERE IsDeleted = false"

    def test_numbers(self) -> None:
        query = Soql("Opportunity").select("Amount").where("Amount", ">=", 100).build()
        assert query == "SELECT Amount FROM Opportunity WHERE Amount >= 100"
        query = Soql("Opportunity").select("Amount").where("Amount", "<", 1.5).build()
        assert query == "SELECT Amount FROM Opportunity WHERE Amount < 1.5"

    @pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
    def test_nan_and_inf_are_rejected(self, value: float) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Opportunity").select("Amount").where("Amount", "=", value)

    @pytest.mark.parametrize("operator", ["=", "!="])
    def test_none_becomes_null_for_equality(self, operator: str) -> None:
        built = Soql("Account").select("Id").where("ParentId", operator, None).build()
        assert built == f"SELECT Id FROM Account WHERE ParentId {operator} null"

    def test_none_is_rejected_for_ordering_operators(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Amount", "<", None)

    def test_date(self) -> None:
        built = Soql("Opportunity").select("Id").where("CloseDate", "=", date(2026, 10, 21)).build()
        assert built == "SELECT Id FROM Opportunity WHERE CloseDate = 2026-10-21"

    def test_aware_datetime_is_converted_to_utc(self) -> None:
        value = datetime(2026, 10, 21, 9, 30, 45, tzinfo=JST)
        built = Soql("Opportunity").select("Id").where("CreatedDate", ">=", value).build()
        assert built == "SELECT Id FROM Opportunity WHERE CreatedDate >= 2026-10-21T00:30:45Z"

    def test_aware_datetime_truncates_microseconds(self) -> None:
        value = datetime(2026, 10, 21, tzinfo=UTC, microsecond=999_999)
        built = Soql("Opportunity").select("Id").where("CreatedDate", ">", value).build()
        assert built == "SELECT Id FROM Opportunity WHERE CreatedDate > 2026-10-21T00:00:00Z"

    def test_naive_datetime_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Opportunity").select("Id").where(
                "CreatedDate",
                "=",
                datetime(2026, 10, 21),  # noqa: DTZ001  # 検査したいのは tzinfo 無しの値そのもの
            )

    @pytest.mark.parametrize(
        "container", [list, tuple, set, frozenset], ids=["list", "tuple", "set", "frozenset"]
    )
    def test_in_accepts_containers(self, container: type) -> None:
        built = Soql("Account").select("Id").where("Name", "IN", container(["a", "b"])).build()
        assert built.startswith("SELECT Id FROM Account WHERE Name IN (")
        # set は順序が保証されないので、要素が両方入っていることだけ見る
        assert "'a'" in built
        assert "'b'" in built

    def test_in_keeps_list_order(self) -> None:
        assert (
            Soql("Account")
            .select("Id")
            .where("Name", "IN", ["b", "a"])
            .build()
            .endswith("WHERE Name IN ('b', 'a')")
        )

    def test_in_accepts_values_that_need_escaping(self) -> None:
        built = Soql("Account").select("Id").where("Name", "NOT IN", ["O'B"]).build()
        assert built == r"SELECT Id FROM Account WHERE Name NOT IN ('O\'B')"

    def test_empty_in_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", "IN", [])

    def test_string_for_in_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", "IN", "abc")

    def test_sequence_for_equality_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", "=", ["a"])

    def test_nested_sequence_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", "IN", [["a"]])

    def test_includes_requires_strings(self) -> None:
        built = Soql("Contact").select("Id").where("Languages__c", "INCLUDES", ["en"]).build()
        assert built == "SELECT Id FROM Contact WHERE Languages__c INCLUDES ('en')"
        with pytest.raises(SoqlBuildError):
            Soql("Contact").select("Id").where("Languages__c", "EXCLUDES", [1])

    def test_unsupported_type_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", "=", {"a": 1})

    @pytest.mark.parametrize("operator", ["==", "=>", "", "AND", "NOT"])
    def test_unknown_operator_is_rejected(self, operator: str) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where("Name", operator, "x")

    def test_unknown_operator_message_lists_the_allowed_operators_intact(self) -> None:
        """使える演算子の一覧が、1 文字ずつに分かれずに読める形で出る。"""
        with pytest.raises(SoqlBuildError) as info:
            Soql("Account").select("Id").where("Name", "~~", "x")

        assert "= / != / < / <= / > / >= / LIKE / IN / NOT IN / INCLUDES / EXCLUDES" in str(
            info.value
        )

    def test_error_belongs_to_the_salesforce_category(self) -> None:
        """既存の Salesforce 例外の分類に入っている（ComkenError 直下に増やさない規約）。"""
        assert issubclass(SoqlBuildError, SalesforceError)

    @pytest.mark.parametrize(
        ("given", "value", "expected"),
        [("like", "%a%", "LIKE"), ("in", ["a"], "IN"), ("not  in", ["a"], "NOT IN")],
    )
    def test_operator_case_and_spacing_are_normalised(
        self, given: str, value: object, expected: str
    ) -> None:
        built = Soql("Account").select("Id").where("Name", given, value).build()
        rendered = "'%a%'" if expected == "LIKE" else "('a')"
        assert built == f"SELECT Id FROM Account WHERE Name {expected} {rendered}"


class TestDateLiterals:
    """日付リテラルは引用符なしで出る。"""

    @pytest.mark.parametrize("literal", ALL_DATE_CONSTANTS)
    def test_constants_are_not_quoted(self, literal: DateLiteral) -> None:
        built = Soql("Account").select("Id").where("CreatedDate", "=", literal).build()
        assert built == f"SELECT Id FROM Account WHERE CreatedDate = {literal.text}"
        assert "'" not in built.split("WHERE")[1]

    def test_str_is_quoted_but_constant_is_not(self) -> None:
        quoted = Soql("Account").select("Id").where("CreatedDate", "=", "TODAY").build()
        assert quoted == "SELECT Id FROM Account WHERE CreatedDate = 'TODAY'"
        constant = Soql("Account").select("Id").where("CreatedDate", "=", TODAY).build()
        assert constant == "SELECT Id FROM Account WHERE CreatedDate = TODAY"

    @pytest.mark.parametrize(
        ("factory", "count", "expected"),
        [
            (last_n_days, 30, "LAST_N_DAYS:30"),
            (next_n_days, 30, "NEXT_N_DAYS:30"),
            (last_n_weeks, 4, "LAST_N_WEEKS:4"),
            (next_n_weeks, 4, "NEXT_N_WEEKS:4"),
            (last_n_months, 3, "LAST_N_MONTHS:3"),
            (next_n_months, 3, "NEXT_N_MONTHS:3"),
            (last_n_years, 2, "LAST_N_YEARS:2"),
            (next_n_years, 2, "NEXT_N_YEARS:2"),
        ],
    )
    def test_relative_functions_render_without_quotes(
        self,
        factory: Callable[[int], DateLiteral],
        count: int,
        expected: str,
    ) -> None:
        built = Soql("Account").select("Id").where("CreatedDate", ">=", factory(count)).build()
        assert built == f"SELECT Id FROM Account WHERE CreatedDate >= {expected}"

    @pytest.mark.parametrize(
        "factory",
        [
            last_n_days,
            next_n_days,
            last_n_weeks,
            next_n_weeks,
            last_n_months,
            next_n_months,
            last_n_years,
            next_n_years,
        ],
    )
    @pytest.mark.parametrize("count", [0, -1, True, 1.0, "3"])
    def test_relative_functions_reject_bad_counts(
        self, factory: Callable[[int], DateLiteral], count: object
    ) -> None:
        with pytest.raises(SoqlBuildError):
            factory(count)  # type: ignore[arg-type]

    def test_str_of_date_literal_is_the_soql_text(self) -> None:
        assert str(TODAY) == "TODAY"
        assert str(last_n_days(7)) == "LAST_N_DAYS:7"


class TestWhereAny:
    """``where_any`` は括弧付きの OR のまとまりにする。"""

    def test_conditions_are_wrapped_in_parentheses(self) -> None:
        built = (
            Soql("Opportunity")
            .select("Id")
            .where_any(("StageName", "=", "Closed Won"), ("StageName", "=", "Closed Lost"))
            .build()
        )
        assert built == (
            "SELECT Id FROM Opportunity "
            "WHERE (StageName = 'Closed Won' OR StageName = 'Closed Lost')"
        )

    def test_combines_with_and(self) -> None:
        built = (
            Soql("Opportunity")
            .select("Id")
            .where("Amount", ">", 0)
            .where_any(("A", "=", 1), ("B", "=", 2))
            .where("CloseDate", "=", TODAY)
            .build()
        )
        assert built == (
            "SELECT Id FROM Opportunity WHERE Amount > 0 AND (A = 1 OR B = 2) AND CloseDate = TODAY"
        )

    def test_three_conditions(self) -> None:
        built = (
            Soql("Account")
            .select("Id")
            .where_any(("A", "=", 1), ("B", "=", 2), ("C", "=", 3))
            .build()
        )
        assert built == "SELECT Id FROM Account WHERE (A = 1 OR B = 2 OR C = 3)"

    @pytest.mark.parametrize("conditions", [(), (("A", "=", 1),)])
    def test_fewer_than_two_conditions_is_rejected(
        self, conditions: tuple[tuple[str, str, object], ...]
    ) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where_any(*conditions)

    def test_bad_shape_is_rejected(self) -> None:
        with pytest.raises(SoqlBuildError):
            Soql("Account").select("Id").where_any(("A", "=", 1), ("B", "="))  # type: ignore[arg-type]

    def test_values_are_escaped_inside_the_group(self) -> None:
        built = (
            Soql("Account")
            .select("Id")
            .where_any(("Name", "=", "O'B"), ("Name", "=", "a\\b"))
            .build()
        )
        assert built == r"SELECT Id FROM Account WHERE (Name = 'O\'B' OR Name = 'a\\b')"


def _limit_with_str() -> Soql:
    """型として壊れた値を `limit()` に渡す（検査が働くことの確認用）。"""
    return Soql("Account").select("Id").limit("3")  # type: ignore[arg-type]


class TestErrorMessages:
    """メッセージは「どこで何をしたら駄目か」が分かり、末尾に「対処:」がある。"""

    def test_is_a_comken_error(self) -> None:
        with pytest.raises(ComkenError):
            Soql("Account").select("Id; DELETE")

    @pytest.mark.parametrize(
        ("build", "expected"),
        [
            (lambda: Soql("Account").select("Id; DELETE"), ["Id; DELETE", "SELECT"]),
            (lambda: Soql("Account").select("Id").where("Name)", "=", 1), ["Name)"]),
            (lambda: Soql("Account").select("Id").where("Name", "==", 1), ["=="]),
            (lambda: Soql("Account").select("Id").where("Amount", "<", None), ["Amount", "None"]),
            (lambda: Soql("Account").select("Id").limit(-3), ["-3"]),
            (_limit_with_str, ["3"]),
            (lambda: Soql("Account").where("Name", "=", "x").build(), ["SELECT"]),
            (lambda: last_n_days(0), ["0"]),
            (
                lambda: Soql("Account").select("Id").where("Name", "IN", "abc"),
                ["abc", "IN"],
            ),
        ],
    )
    def test_message_contains_target_and_treatment(self, build, expected: list[str]) -> None:
        with pytest.raises(SoqlBuildError) as caught:
            build()
        message = str(caught.value)
        for part in expected:
            assert part in message
        assert "対処: " in message
        # 「対処:」行は必ず末尾
        assert message.rstrip().split("\n")[-1].startswith("対処: ")
