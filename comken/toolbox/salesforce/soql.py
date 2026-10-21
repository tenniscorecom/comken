"""comken/toolbox/salesforce/soql.py — SOQL を組み立てる

SOQL（Salesforce のクエリ）を Python の呼び出しで組み立て、`.build()` で文字列にする。
通信はせず `requests` にも依存しない。実行は今まで通り `SalesforceBase.query()` へ
文字列を渡すだけ。

    from comken.toolbox.salesforce.soql import Soql, last_n_days

    soql = (
        Soql("Opportunity")                                 # FROM にあたる対象
        .where("CloseDate", ">=", last_n_days(30))          # 以降は書く順番を問わない
        .where("StageName", "=", "Closed Won")
        .select("Id", "Name", "Amount")
        .order_by("Amount", desc=True)
        .limit(100)
        .build()
    )

    with Solution() as sf:
        rows = sf.query(soql)

**`from` は Python の予約語なのでメソッド名に使えない。** 対象オブジェクトは
コンストラクタ（`Soql("Opportunity")`）で渡し、あとは順不同で組み立てて `build()` が
SOQL の正しい並びに組み直す。

**SOQL には `SELECT *` が無く、値を差し込む変数（バインド変数）も無い。**
つまり値は必ず文字列へ埋め込むのでエスケープが要るが、その事故を
利用者が意識せずに済むよう、このクラスが常にエスケープする。

作っていないもの: `NOT`・入れ子の OR/AND・サブクエリ・`HAVING`・`OFFSET`・
`FIELDS(ALL)`。足りなくなったら足す。

設計の理由は docs/HISTORY.md「SOQL を組み立てる Soql クラスを追加した」を参照。
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Never

from comken.exceptions import SoqlBuildError

# SOQL の識別子。`Account.Name` のように `.` で連結できるが、それ以外の記号は入れない。
# インジェクション（`Id; DELETE` やコメント）を SOQL に入れる前に弾くための規則。
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_FIELD = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*"
_FIELD_PATTERN = re.compile(_FIELD)
# `SELECT` に並べる式。集計関数は COUNT() だけ引数を省略できる。
# 別名は関数の後ろに空白1つ＋識別子で付ける（`SUM(Amount) total`）。
_FUNCTION = rf"(?:COUNT\(\)|COUNT(?:_DISTINCT)?\({_FIELD}\)|(?:SUM|AVG|MIN|MAX)\({_FIELD}\))"
_SELECT_PATTERN = re.compile(rf"(?:{_FIELD}|{_FUNCTION}(?: {_IDENTIFIER})?)")

_OPERATORS = frozenset(
    {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN", "NOT IN", "INCLUDES", "EXCLUDES"}
)
# 値を list / tuple / set で取る演算子。文字列1つでは「複数の値」にならない。
_SEQUENCE_OPERATORS = frozenset({"IN", "NOT IN", "INCLUDES", "EXCLUDES"})
_EQUALITY_OPERATORS = frozenset({"=", "!="})
# 要素が文字列に限られる演算子（複数選択項目は文字列で受ける）。
_STRING_ONLY_OPERATORS = frozenset({"INCLUDES", "EXCLUDES"})
_SEQUENCE_TYPES = (list, tuple, set, frozenset)

_DATE_FORMAT = "%Y-%m-%d"
_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
_UTC_SUFFIX = "Z"  # 秒以下は strftime が切り捨てるので、書式には入れず手で足す

_BOOLEANS: dict[bool, str] = {True: "true", False: "false"}
_OPERATOR_LIST = " / ".join(
    ("=", "!=", "<", "<=", ">", ">=", "LIKE", "IN", "NOT IN", "INCLUDES", "EXCLUDES")
)


def _fail(problem: str, treatment: str) -> Never:
    """組み立ての指定が不正なときに止める。メッセージ末尾に「対処:」1行を必ず付ける。"""
    raise SoqlBuildError(f"{problem}\n対処: {treatment}")


def _identifier(text: object, *, place: str) -> str:
    """オブジェクト名・項目名を検査し、そのまま返す。"""
    if not isinstance(text, str) or not _FIELD_PATTERN.fullmatch(text):
        _fail(
            f"SOQL の{place}の指定が不正です: {text!r}",
            "英字または _ で始まり、英字・数字・_ だけで書く（項目の途中だけ . で連結できる）。"
            "例: Opportunity / Name / Account.Name / Owner.Profile.Name / Custom__c",
        )
    return text


def _select_expression(text: object) -> str:
    """`SELECT` に並べる式（項目、または集計関数と別名）を検査し、そのまま返す。"""
    if not isinstance(text, str) or not _SELECT_PATTERN.fullmatch(text):
        _fail(
            f"SOQL の SELECT に並べる式が不正です: {text!r}",
            "英字・数字・_ だけで項目名を書くか、集計関数（COUNT / COUNT_DISTINCT / SUM / "
            "AVG / MIN / MAX）に続けて項目名を書き、別名を付けるなら後ろに空白1つ＋識別子を"
            "置く。例: Id / Account.Name / COUNT() / COUNT(Id) / SUM(Amount) total",
        )
    return text


def _operator(op: object) -> str:
    """比較演算子を SOQL の表記（大文字）にそろえて返す。"""
    if not isinstance(op, str):
        _fail(
            f"SOQL の比較演算子が文字列ではありません: {op!r}",
            f"比較演算子は {_OPERATOR_LIST} のどれかを文字列で渡す",
        )
    normalized = " ".join(op.split()).upper()
    if normalized not in _OPERATORS:
        _fail(
            f"SOQL の比較演算子が不正です: {op!r}",
            f"比較演算子は {_OPERATOR_LIST} のいずれかにする",
        )
    return normalized


def _quote(text: str) -> str:
    """文字列リテラルの中身として安全な形へエスケープする。

    バックスラッシュを先に置き換えないと、あとから足した `\\` が二重に逃げる。
    `LIKE` の `%` と `_` は利用者が書いたワイルドカードなのでそのまま通す。
    """
    escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return escaped.replace("\b", "\\b").replace("\f", "\\f")


def _check_value_kind(operator: str, value: object, *, field: str) -> None:
    """演算子と値の型が噛み合っているか（list を `=` に渡す等の事故）を先に弾く。"""
    is_sequence = isinstance(value, _SEQUENCE_TYPES)
    if operator in _SEQUENCE_OPERATORS and not is_sequence:
        _fail(
            f"{field} の {operator} に list / tuple / set 以外を渡しました: {value!r}",
            "複数の値を比べる IN / NOT IN / INCLUDES / EXCLUDES には "
            "list / tuple / set を渡す。1つの値だけなら 1 個渡す",
        )
    if operator not in _SEQUENCE_OPERATORS and is_sequence:
        _fail(
            f"{field} の {operator} に list / tuple / set を渡しました",
            "複数の値を比べるには IN / NOT IN を使い、1つの値と比べるなら 1 個だけ渡す",
        )


def _render_null(*, field: str, operator: str) -> str:
    if operator not in _EQUALITY_OPERATORS:
        _fail(
            f"{field} の {operator} に None を渡しました",
            "null は = / != にしか書けないため、別の値と比べる場合は値を直接渡す",
        )
    return "null"


def _render_number(value: int | float, *, field: str) -> str:
    # nan / inf は SOQL の数値リテラルとして書けない。文字列に変換すると NaN が混ざる
    if isinstance(value, float) and not math.isfinite(value):
        _fail(
            f"{field} の比較に nan / inf を渡しました: {value}",
            "nan と inf は SOQL に書けないため、合計や平均の計算結果ではなく 0 などの値を渡す",
        )
    return str(value)


def _render_datetime(value: datetime, *, field: str) -> str:
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        _fail(
            f"{field} の比較にタイムゾーン無しの datetime を渡しました: {value.isoformat()}",
            "どの時刻か決められないため、タイムゾーンを付けて渡す"
            "（例: datetime(2026, 10, 21, 9, 0, tzinfo=UTC)）",
        )
    return value.astimezone(UTC).strftime(_DATETIME_FORMAT) + _UTC_SUFFIX


def _render_sequence(value: Collection[object], *, field: str, operator: str) -> str:
    if not value:
        _fail(
            f"{field} の {operator} に空の値を渡しました",
            "値を 1 つ以上入れてから渡す（空のままでは条件を組み立てられない）",
        )
    rendered: list[str] = []
    for item in value:
        if isinstance(item, _SEQUENCE_TYPES):
            _fail(
                f"{field} の {operator} に入れ子の値を渡しました: {item!r}",
                "入れ子は書けない。値のリストは 1 段だけにする",
            )
        if operator in _STRING_ONLY_OPERATORS and not isinstance(item, str):
            _fail(
                f"{field} の {operator} の要素が文字列ではありません: {item!r}",
                "INCLUDES / EXCLUDES は複数選択項目の文字列しか受け付けない",
            )
        rendered.append(_render_value(item, field=field, operator=operator))
    return "(" + ", ".join(rendered) + ")"


def _render_value(value: object, *, field: str, operator: str) -> str:
    """``where`` の値を SOQL 側のリテラル文字列へ変換する。"""
    if isinstance(value, DateLiteral):
        return value.text
    if isinstance(value, bool):  # bool は int より先に判定する（True が 1 にならないように）
        return _BOOLEANS[value]
    if isinstance(value, datetime):  # datetime は date の子。故に先に判定する
        return _render_datetime(value, field=field)
    if isinstance(value, date):
        return value.strftime(_DATE_FORMAT)
    if isinstance(value, str):
        return f"'{_quote(value)}'"
    if isinstance(value, (int, float)):
        return _render_number(value, field=field)
    if isinstance(value, _SEQUENCE_TYPES):
        return _render_sequence(value, field=field, operator=operator)
    if value is None:
        return _render_null(field=field, operator=operator)
    _fail(
        f"{field} の比較に SOQL に書けない型を渡しました: {type(value).__name__}",
        "str / bool / int / float / date / datetime / DateLiteral / None か、"
        "IN などに list / tuple / set を渡す",
    )


def _render_condition(field: str, operator: str, value: object) -> str:
    """``where`` の 1 条件（``Field OP Value``）を組み立てる。"""
    name = _identifier(field, place="条件の項目")
    op = _operator(operator)
    _check_value_kind(op, value, field=name)
    return f"{name} {op} {_render_value(value, field=name, operator=op)}"


def _render_grouped_condition(condition: object) -> str:
    """``where_any`` の 1 条件（``(field, operator, value)`` のタプル）を組み立てる。"""
    if not isinstance(condition, tuple) or len(condition) != 3:
        _fail(
            f"where_any() の条件は (項目名, 演算子, 値) のタプルである必要があります:"
            f" {condition!r}",
            "(Name, '=', 'value') のように 3 つのタプルで渡す",
        )
    field, operator, value = condition
    return _render_condition(field, operator, value)


@dataclass(frozen=True)
class Soql:
    """SOQL を組み立てる。すべて不変で、各メソッドは新しい ``Soql`` を返す

    **書く順番は問わない。** `build()` が SOQL の正しい並び
    （`SELECT` → `FROM` → `WHERE` → `GROUP BY` → `ORDER BY` → `LIMIT`）へ組み直す。

        from comken.toolbox.salesforce.soql import Soql, last_n_days

        base = Soql("Opportunity").select("Id", "Name", "CloseDate")
        won = base.where("StageName", "=", "Closed Won").order_by("CloseDate").build()
        lost = base.where("StageName", "=", "Closed Lost").build()   # base は変わらない

    使い終わったら `str(soql)` でも同じ文字列が得られる（`build()` の別名）。

    Args:
        object_name: `FROM` にあたるオブジェクト名（例: ``"Opportunity"``）。
            `from` は Python の予約語なのでメソッドではなくコンストラクタで渡す。

    Raises:
        SoqlBuildError: 識別子・演算子・値が SOQL の書き方に合わないとき。
    """

    object_name: str
    columns: tuple[str, ...] = ()
    filters: tuple[str, ...] = ()
    grouped: tuple[str, ...] = ()
    orderings: tuple[str, ...] = ()
    row_limit: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.object_name, place="対象オブジェクト")

    def select(self, *fields: str) -> Soql:
        """`SELECT` に並べる列（または集計関数）を追加する。重複した式は 1 つにする

        複数回呼べば追加され、書いた順に並ぶ。

        Args:
            fields: ``"Id"`` / ``"Account.Name"`` の項目名、または集計関数
                （``"COUNT()"`` / ``"SUM(Amount)"`` / ``"SUM(Amount) total"``）。

        Returns:
            列を足した新しい ``Soql``。
        """
        added = (_select_expression(field) for field in fields)
        columns = self.columns
        for column in added:
            if column not in columns:
                columns += (column,)
        return replace(self, columns=columns)

    def where(self, field: str, operator: str, value: object) -> Soql:
        """`WHERE` の条件を 1 つ追加する。複数回呼べば `AND` で連結する

        Args:
            field: 項目名。
            operator: ``=`` ``!=`` ``<`` ``<=`` ``>`` ``>=`` ``LIKE`` ``IN``
                ``NOT IN`` ``INCLUDES`` ``EXCLUDES`` のいずれか（大文字小文字は問わない）。
            value: Python の値。文字列は引用符つき・`'` などがエスケープされて出る。
                ``IN`` 系は list / tuple / set。値は ``str`` ``bool`` ``int`` ``float``
                ``date`` ``datetime`` ``DateLiteral`` ``None`` を扱える。

        Returns:
            条件を足した新しい ``Soql``。
        """
        return replace(self, filters=(*self.filters, _render_condition(field, operator, value)))

    def where_any(self, *conditions: tuple[str, str, object]) -> Soql:
        """`OR` で結んだ条件のまとまりを 1 つとして追加する

        Args:
            conditions: ``(field, operator, value)`` のタプルを 2 つ以上。
                ``where()`` と同じ値を渡す。

        Returns:
            条件のまとまりを足した新しい ``Soql``。

        Raises:
            SoqlBuildError: 2 つ未満、または要素の形がタプルでないとき。
        """
        if len(conditions) < 2:
            _fail(
                f"where_any() に条件が {len(conditions)} 個しかありません",
                "括弧が付くのは 2 個以上のときだけ。1 個なら where() を使う",
            )
        rendered = [_render_grouped_condition(condition) for condition in conditions]
        return replace(self, filters=(*self.filters, f"({' OR '.join(rendered)})"))

    def group_by(self, *fields: str) -> Soql:
        """`GROUP BY` に並べる項目を追加する（集計関数と同じ項目を指定する）

        Args:
            fields: ``"StageName"`` の項目名。

        Returns:
            項目を足した新しい ``Soql``。
        """
        added = tuple(_identifier(field, place="GROUP BY の項目") for field in fields)
        return replace(self, grouped=(*self.grouped, *added))

    def order_by(self, field: str, desc: bool = False) -> Soql:
        """`ORDER BY` に並べる項目を 1 つ追加する。複数回呼んだ順に並ぶ

        Args:
            field: ``"Amount"`` の項目名。
            desc: ``True`` で降順（`DESC` を付ける）。

        Returns:
            項目を足した新しい ``Soql``。
        """
        name = _identifier(field, place="ORDER BY の項目")
        direction = " DESC" if desc else ""
        return replace(self, orderings=(*self.orderings, f"{name}{direction}"))

    def limit(self, count: int) -> Soql:
        """`LIMIT` を設定する。複数回呼んだときは最後の値が勝つ

        Args:
            count: 取得する行数（0 以上の整数）。

        Returns:
            行数を設定した新しい ``Soql``。
        """
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            _fail(
                f"LIMIT に 0 以上の整数を渡してください: {count!r}",
                "limit() には行数の整数だけ渡す",
            )
        return replace(self, row_limit=count)

    def build(self) -> str:
        """SOQL の文字列を組み立てる

        Returns:
            ``SELECT`` → ``FROM`` → ``WHERE`` → ``GROUP BY`` → ``ORDER BY`` →
            ``LIMIT`` の順に並べた SOQL。

        Raises:
            SoqlBuildError: `SELECT` が 1 つも無いとき（SOQL に `SELECT *` は無い）。
        """
        if not self.columns:
            _fail(
                "SELECT に並べる列が 1 つもありません",
                'SOQL には SELECT * が無いので、select("Id", "Name") のように列を選ぶ',
            )
        parts = [f"SELECT {', '.join(self.columns)}", f"FROM {self.object_name}"]
        if self.filters:
            parts.append(f"WHERE {' AND '.join(self.filters)}")
        if self.grouped:
            parts.append(f"GROUP BY {', '.join(self.grouped)}")
        if self.orderings:
            parts.append(f"ORDER BY {', '.join(self.orderings)}")
        if self.row_limit is not None:
            parts.append(f"LIMIT {self.row_limit}")
        return " ".join(parts)

    def __str__(self) -> str:
        """`build()` と同じ文字列を返す"""
        return self.build()


# NOTE: DateLiteral はすぐ下の定数を定義する前に置く必要がある。定数が import 時に
#       DateLiteral のインスタンスを作るので、この順序を逆にすると import で落ちる。
@dataclass(frozen=True)
class DateLiteral:
    """SOQL の日付リテラル。引用符なしでそのまま SOQL へ入る値

    `str` のインスタンスと区別するためにこの型で持つ。`where("CloseDate", ">=", "TODAY")`
    は文字列なので `'TODAY'` と引用されるが、`where("CloseDate", ">=", TODAY)` は引用なし。

    Args:
        text: SOQL へそのまま出すリテラル（例: ``"TODAY"`` / ``"LAST_N_DAYS:30"``）。
    """

    text: str

    def __str__(self) -> str:
        """SOQL へ出すリテラルの文字列を返す"""
        return self.text


TODAY = DateLiteral("TODAY")
YESTERDAY = DateLiteral("YESTERDAY")
TOMORROW = DateLiteral("TOMORROW")
THIS_WEEK = DateLiteral("THIS_WEEK")
LAST_WEEK = DateLiteral("LAST_WEEK")
NEXT_WEEK = DateLiteral("NEXT_WEEK")
THIS_MONTH = DateLiteral("THIS_MONTH")
LAST_MONTH = DateLiteral("LAST_MONTH")
NEXT_MONTH = DateLiteral("NEXT_MONTH")
THIS_QUARTER = DateLiteral("THIS_QUARTER")
LAST_QUARTER = DateLiteral("LAST_QUARTER")
NEXT_QUARTER = DateLiteral("NEXT_QUARTER")
THIS_YEAR = DateLiteral("THIS_YEAR")
LAST_YEAR = DateLiteral("LAST_YEAR")
NEXT_YEAR = DateLiteral("NEXT_YEAR")


def _relative_period(name: str, count: int) -> DateLiteral:
    """`LAST_N_DAYS:30` のように「名前:個数」のリテラルを作る。"""
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        _fail(
            f"日付リテラル {name} の個数が不正です: {count!r}",
            f"{name.lower()}() には 1 以上の整数を渡す",
        )
    return DateLiteral(f"{name}:{count}")


def last_n_days(count: int) -> DateLiteral:
    """`LAST_N_DAYS:30` を作る（過去 n 日）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("LAST_N_DAYS", count)


def next_n_days(count: int) -> DateLiteral:
    """`NEXT_N_DAYS:30` を作る（未来 n 日）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("NEXT_N_DAYS", count)


def last_n_weeks(count: int) -> DateLiteral:
    """`LAST_N_WEEKS:4` を作る（過去 n 週間）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("LAST_N_WEEKS", count)


def next_n_weeks(count: int) -> DateLiteral:
    """`NEXT_N_WEEKS:4` を作る（未来 n 週間）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("NEXT_N_WEEKS", count)


def last_n_months(count: int) -> DateLiteral:
    """`LAST_N_MONTHS:3` を作る（過去 n か月）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("LAST_N_MONTHS", count)


def next_n_months(count: int) -> DateLiteral:
    """`NEXT_N_MONTHS:3` を作る（未来 n か月）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("NEXT_N_MONTHS", count)


def last_n_years(count: int) -> DateLiteral:
    """`LAST_N_YEARS:1` を作る（過去 n 年）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("LAST_N_YEARS", count)


def next_n_years(count: int) -> DateLiteral:
    """`NEXT_N_YEARS:1` を作る（未来 n 年）

    Args:
        count: 1 以上の整数。

    Returns:
        ``where()`` に渡せる :class:`DateLiteral`。
    """
    return _relative_period("NEXT_N_YEARS", count)
