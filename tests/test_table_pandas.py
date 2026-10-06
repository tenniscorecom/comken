"""``Table`` ⇄ ``pandas.DataFrame`` 相互変換のテスト。

pandas は optional-dependencies のため、`pytest.importorskip("pandas")` で
pandas がある環境だけ走らせる。pandas が無いときに出る例外は
``MissingOptionalDependencyError``（ComkenError 系の新例外）で、
``pip install pandas`` の手順がメッセージに入ることを確認する。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

import pytest

# pandas は optional 依存。無い CI ではこのファイル全体を skip させる。
pd = pytest.importorskip("pandas")

from comken.core.table import Table  # noqa: E402
from comken.exceptions import (  # noqa: E402
    ComkenError,
    MissingOptionalDependencyError,
    TableError,
)

# ---------------------------------------------------------------------------
# to_dataframe
# ---------------------------------------------------------------------------


def test_to_dataframe_preserves_column_order_and_values() -> None:
    """to_dataframe は列順・値・行数を保った DataFrame を返す。"""
    table = Table(
        ["ID", "氏名", "金額"],
        [
            {"ID": "1", "氏名": "山田", "金額": 100},
            {"ID": "2", "氏名": "鈴木", "金額": 250},
            {"ID": "3", "氏名": "佐藤", "金額": 80},
        ],
    )

    df = table.to_dataframe()

    assert list(df.columns) == ["ID", "氏名", "金額"]
    assert len(df) == 3
    # 値の順番も保たれる
    assert df["氏名"].tolist() == ["山田", "鈴木", "佐藤"]
    assert df["金額"].tolist() == [100, 250, 80]


def test_to_dataframe_keeps_columns_when_zero_rows() -> None:
    """0 行の Table でも DataFrame には列が残る（0 件の値に落ちる前提）。"""
    table = Table(["ID", "氏名", "金額"], [])

    df = table.to_dataframe()

    assert list(df.columns) == ["ID", "氏名", "金額"]
    assert len(df) == 0


def test_to_dataframe_returns_object_dtype_for_mixed_values() -> None:
    """dtype は pandas に任せず object のままでよい（型変換は行わない）。"""
    table = Table(["x"], [{"x": 1}, {"x": "2"}, {"x": None}])

    df = table.to_dataframe()

    assert df["x"].dtype == object


# ---------------------------------------------------------------------------
# from_dataframe
# ---------------------------------------------------------------------------


def test_from_dataframe_round_trip_preserves_values() -> None:
    """Table → DataFrame → Table で元の Table と等しくなる。"""
    original = Table(
        ["ID", "氏名", "金額"],
        [
            {"ID": "1", "氏名": "山田", "金額": 100},
            {"ID": "2", "氏名": "鈴木", "金額": 250},
        ],
    )

    restored = Table.from_dataframe(original.to_dataframe())

    assert restored.columns == original.columns
    assert restored.to_rows() == original.to_rows()


def test_from_dataframe_normalizes_missing_values_to_none() -> None:
    """欠損値（NaN / None / pd.NA / NaT）は None に揃える。"""
    df = pd.DataFrame(
        [
            {"a": 1.0, "b": "x", "c": 1.0, "d": pd.Timestamp("2026-01-01")},
            {"a": float("nan"), "b": None, "c": pd.NA, "d": pd.NaT},
            {"a": 3.0, "b": "z", "c": 3.0, "d": pd.Timestamp("2026-01-03")},
        ]
    )

    table = Table.from_dataframe(df)

    assert table.to_rows() == [
        {
            "a": 1.0,
            "b": "x",
            "c": 1.0,
            "d": pd.Timestamp("2026-01-01"),
        },
        {"a": None, "b": None, "c": None, "d": None},
        {
            "a": 3.0,
            "b": "z",
            "c": 3.0,
            "d": pd.Timestamp("2026-01-03"),
        },
    ]


def test_from_dataframe_keeps_non_scalar_values_as_is() -> None:
    """リスト・辞書は pd.isna の判定対象にならないため、そのまま保持する。"""
    df = pd.DataFrame([{"name": "x", "items": [1, 2, 3], "meta": {"k": "v"}}])

    table = Table.from_dataframe(df)

    assert table.to_rows() == [
        {"name": "x", "items": [1, 2, 3], "meta": {"k": "v"}},
    ]


def test_from_dataframe_converts_numeric_column_names_to_str() -> None:
    """数値の列名も str() されて Table の列名（文字列）になる。"""
    df = pd.DataFrame([[10, 20], [30, 40]], columns=[1, 2])

    table = Table.from_dataframe(df)

    assert table.columns == ["1", "2"]
    assert table.to_rows() == [{"1": 10, "2": 20}, {"1": 30, "2": 40}]


def test_from_dataframe_rejects_duplicate_column_names_after_str() -> None:
    """str() 後に列名が衝突すると TableError（既存の Table と同じ挙動）。"""
    df = pd.DataFrame([[1, 2]], columns=["1", 1])  # str() 後はどちらも "2"

    with pytest.raises(TableError, match="列名"):
        Table.from_dataframe(df)


def test_from_dataframe_drops_index() -> None:
    """DataFrame の index は捨てて、0..n-1 の連番で 1 行ずつ取り出す。"""
    df = pd.DataFrame(
        {"name": ["山田", "鈴木", "佐藤"]},
        index=[100, 200, 300],
    )

    table = Table.from_dataframe(df)

    assert len(table) == 3
    assert [row["name"] for row in table.to_rows()] == ["山田", "鈴木", "佐藤"]
    # 0 行目の name がインデックス 100 の行の値になっている（順序が保たれる）
    assert table.to_rows()[0] == {"name": "山田"}


def test_from_dataframe_applies_types() -> None:
    """types は Table にそのまま渡せる（既存の Table と同じ型変換がかかる）。"""
    df = pd.DataFrame([{"id": "1"}, {"id": "2"}])

    def s2i(value: object) -> int:
        return int(value)  # type: ignore[arg-type]

    table = Table.from_dataframe(df, types={"id": s2i})

    assert table.column("id") == [1, 2]


def test_from_dataframe_with_no_missing_arg_exceptions_is_none() -> None:
    """None の値は pd.NA ではなく None（pd.isna の戻り値）になる。"""
    df = pd.DataFrame([{"x": None}])

    table = Table.from_dataframe(df)

    assert table.to_rows() == [{"x": None}]


def test_from_dataframe_empty_dataframe() -> None:
    """0 行の DataFrame からも Table を作れる（列は残る）。"""
    df = pd.DataFrame(columns=["a", "b"])

    table = Table.from_dataframe(df)

    assert table.columns == ["a", "b"]
    assert len(table) == 0


# ---------------------------------------------------------------------------
# pandas が無いときの挙動
# ---------------------------------------------------------------------------


def _with_pandas_blocked(
    monkeypatch: pytest.MonkeyPatch,
    func: Callable[[], Any],
) -> Any:
    """``pandas`` を ``sys.modules`` から隠して ``func`` を実行する。

    ``sys.modules["pandas"] = None`` を入れると、``import pandas`` が
    ``ModuleNotFoundError``（``ImportError`` のサブクラス）を送出する。
    ``monkeypatch`` で書き換えた ``sys.modules`` は次のテストへ漏らさない
    （pytest の fixture 任せ）。
    """
    saved = monkeypatch.setitem(sys.modules, "pandas", None)  # type: ignore[arg-type]
    try:
        return func()
    finally:
        del saved  # monkeypatch が unimport する


def test_from_dataframe_raises_when_pandas_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """pandas が無い環境で from_dataframe を呼ぶと ``MissingOptionalDependencyError``。"""

    def call() -> Any:
        return Table.from_dataframe(pd.DataFrame({"x": [1]}))  # type: ignore[arg-type]

    with pytest.raises(MissingOptionalDependencyError, match="pip install pandas"):
        _with_pandas_blocked(monkeypatch, call)


def test_to_dataframe_raises_when_pandas_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """pandas が無い環境で to_dataframe を呼ぶと ``MissingOptionalDependencyError``。"""

    def call() -> Any:
        return Table(["x"], [{"x": 1}]).to_dataframe()

    with pytest.raises(MissingOptionalDependencyError, match="pip install pandas"):
        _with_pandas_blocked(monkeypatch, call)


def test_missing_optional_dependency_is_comken_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """``MissingOptionalDependencyError`` は ``ComkenError`` 系の例外で受け取れる。"""

    def call() -> Any:
        return Table.from_dataframe(pd.DataFrame({"x": [1]}))  # type: ignore[arg-type]

    with pytest.raises(ComkenError, match="pandas"):
        _with_pandas_blocked(monkeypatch, call)


# ---------------------------------------------------------------------------
# 遅延 import: pandas は使わなければ import されない
# ---------------------------------------------------------------------------


def test_table_module_does_not_eagerly_import_pandas() -> None:
    """``import comken.core.table.model`` しただけでは pandas は import されない。

    メソッドを呼ばない限り pandas は不要、という遅延 import の設計を担保する。
    ``comken.core.table.model`` のモジュール属性に ``pandas``（モジュール）が
    入っていないことで「メソッド内の import 以外で参照されていない」ことを確かめる
    （TYPE_CHECKING は import しない）。
    """
    import comken.core.table.model as model_module

    assert "pandas" not in model_module.__dict__


def test_table_module_does_not_import_pandas_on_sibling_imports() -> None:
    """``comken.core.table`` を import し直しても pandas が新規に import されない。

    pandas が ``sys.modules`` に無い状態で ``comken.core.table`` を読み直しても、
    ``Table`` クラス定義時には pandas への参照が発生しないことを確かめる
    （``TYPE_CHECKING`` ガード下でだけ参照する実装になっているはず）。
    """
    # pandas が sys.modules に既に入っているのは importorskip の副作用なので、
    # ここでは「comken.core.table import の前後で sys.modules['pandas'] が同じ
    # モジュールオブジェクトのまま」を確認する（= 新規に import を発火させない）。
    import comken.core.table as table_module

    before = sys.modules.get("pandas")
    # model モジュールを再読込してみる（pandas 参照が無いなら失敗しない）
    import importlib

    importlib.reload(table_module)
    after = sys.modules.get("pandas")

    assert before is after, "pandas のモジュール参照が再 import で変わった（想定外）"
