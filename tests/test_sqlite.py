"""SQLite API の読み書き・dry-run・SQL インジェクション対策の契約を確認する。

各テストは ``tmp_path`` に SQLite ファイルを作って動かす。
実装側の不変条件・プレースホルダー規約・トランザクション境界が
崩れたら落ちることを第一の狙いとする。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from comken import dry_run
from comken.core.table import Table
from comken.exceptions import ComkenFileNotFoundError, SQLiteError
from comken.toolbox.sqlite import SQLite

# ── テスト用フィクスチャ ──────────────────────────────────────────────────


def _new_db(tmp_path: Path, *, name: str = "顧客") -> tuple[SQLite, Path]:
    """テスト用の DB を作り、``顧客`` 表を作る。"""
    path = tmp_path / "data.db"
    SQLite(path, create=True)
    db = SQLite(path)
    db.table(name).create(
        columns=["顧客ID", "状態", "金額"],
        types={"顧客ID": str, "状態": str, "金額": int},
        primary_key="顧客ID",
    )
    return db, path


def _seed(db: SQLite, name: str = "顧客") -> None:
    """テストデータを入れる。"""
    rows = Table(
        ["顧客ID", "状態", "金額"],
        [
            {"顧客ID": "001", "状態": "有効", "金額": 1000},
            {"顧客ID": "002", "状態": "有効", "金額": 2000},
            {"顧客ID": "003", "状態": "解約", "金額": 500},
            {"顧客ID": "004", "状態": "有効", "金額": 1500},
        ],
    )
    db.table(name).insert(rows)


# ── 読み込み ──────────────────────────────────────────────────────────


class TestRead:
    def test_read_returns_table(self, tmp_path: Path) -> None:
        """``read()`` は ``Table`` を返し、列順は指定通りになる。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        table = db.table("顧客").read()
        assert isinstance(table, Table)
        assert table.columns == ["顧客ID", "状態", "金額"]
        assert len(table) == 4  # _seed で 4 行入っている

    def test_seed_then_read_returns_rows(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        rows = db.table("顧客").read().to_rows()
        assert len(rows) == 4

    def test_read_with_columns_returns_only_those_in_order(self, tmp_path: Path) -> None:
        """``read(columns=[...])`` はその列だけを指定順で返す。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        table = db.table("顧客").read(columns=["金額", "顧客ID"])
        assert table.columns == ["金額", "顧客ID"]
        # 値は変わらない、行の列順は Table 側（dict）の挿入順
        first = table[0]
        assert "金額" in first and "顧客ID" in first

    def test_read_returns_null_as_none(self, tmp_path: Path) -> None:
        """NULL は None（v2 の方針）。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        # NULL を作る
        db.table("顧客").insert(
            Table(["顧客ID", "状態", "金額"], [{"顧客ID": "005", "状態": None, "金額": 0}])
        )
        rows = db.table("顧客").read().to_rows()
        target = next(r for r in rows if r["顧客ID"] == "005")
        assert target["状態"] is None  # "" ではない
        assert target["状態"] != ""

    def test_where_all_operators(self, tmp_path: Path) -> None:
        """where の全演算子が仕様通り動く。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        q = db.table("顧客")
        # =
        assert len(q.where("状態", "=", "有効").read()) == 3
        # !=
        assert len(q.where("状態", "!=", "有効").read()) == 1
        # <
        assert len(q.where("金額", "<", 1500).read()) == 2
        # <=
        assert len(q.where("金額", "<=", 1500).read()) == 3
        # >
        assert len(q.where("金額", ">", 1500).read()) == 1
        # >=
        assert len(q.where("金額", ">=", 1500).read()) == 2
        # in
        assert len(q.where("顧客ID", "in", ["001", "002"]).read()) == 2
        # not in
        assert len(q.where("顧客ID", "not in", ["001", "002"]).read()) == 2
        # like
        assert len(q.where("顧客ID", "like", "00_").read()) == 4
        # is_null
        db.table("顧客").insert(
            Table(["顧客ID", "状態", "金額"], [{"顧客ID": "006", "状態": None, "金額": 0}])
        )
        assert len(q.where("状態", "is_null").read()) == 1
        # not_null
        assert len(q.where("状態", "not_null").read()) == 4

    def test_where_rejects_unknown_operator(self, tmp_path: Path) -> None:
        """where の op が一覧に無いと ValueError"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="where の op"):
            db.table("顧客").where("状態", "between", ("有効", "解約"))

    def test_where_in_requires_list_or_tuple(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="list または tuple"):
            db.table("顧客").where("顧客ID", "in", "001")  # type: ignore[arg-type]

    def test_where_in_empty_raises(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="空にできません"):
            db.table("顧客").where("顧客ID", "in", [])

    def test_where_is_null_rejects_value(self, tmp_path: Path) -> None:
        """``is_null`` / ``not_null`` は value を渡してはいけない。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="value を渡さないでください"):
            db.table("顧客").where("状態", "is_null", "x")

    def test_where_equality_requires_value(self, tmp_path: Path) -> None:
        """``=`` などの比較演算子は value が必要。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="value が必要"):
            db.table("顧客").where("状態", "=")

    def test_multiple_wheres_combined_as_and(self, tmp_path: Path) -> None:
        """複数の where は AND で結合される。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        rows = (
            db.table("顧客").where("状態", "=", "有効").where("金額", ">=", 1500).read().to_rows()
        )
        # 状態=有効 かつ 金額>=1500 は "002" と "004"
        ids = sorted(r["顧客ID"] for r in rows)
        assert ids == ["002", "004"]

    def test_order_by_single_and_desc(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        rows_asc = db.table("顧客").order_by("金額").read().to_rows()
        rows_desc = db.table("顧客").order_by("金額", desc=True).read().to_rows()
        assert [r["金額"] for r in rows_asc] == [500, 1000, 1500, 2000]
        assert [r["金額"] for r in rows_desc] == [2000, 1500, 1000, 500]

    def test_order_by_multiple_priority(self, tmp_path: Path) -> None:
        """複数 order_by は優先順に並ぶ（先に指定した列が優先）。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        # 状態が同じ金額で順序が安定するか
        rows = db.table("顧客").order_by("状態").order_by("金額", desc=True).read().to_rows()
        # 状態 asc, 金額 desc のはず
        states = [r["状態"] for r in rows]
        amounts = [r["金額"] for r in rows]
        assert states == sorted(states)
        # 同じ状態の塊内では金額は降順
        for state in {"有効", "解約"}:
            sub = [a for s, a in zip(states, amounts, strict=True) if s == state]
            assert sub == sorted(sub, reverse=True)

    def test_limit(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        rows = db.table("顧客").order_by("顧客ID").limit(2).read().to_rows()
        assert len(rows) == 2
        assert [r["顧客ID"] for r in rows] == ["001", "002"]

    def test_limit_must_be_positive(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(ValueError, match="1 以上"):
            db.table("顧客").limit(0)
        with pytest.raises(ValueError):
            db.table("顧客").limit(-1)

    def test_count(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        q = db.table("顧客")
        assert q.count() == 4
        assert q.where("状態", "=", "有効").count() == 3


# ── 不変性 ──────────────────────────────────────────────────────────


class TestImmutability:
    def test_query_chaining_does_not_mix_results(self, tmp_path: Path) -> None:
        """``base = db.table(...).where(...)`` を使い回しても結果が混ざらない。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        base = db.table("顧客").where("状態", "=", "有効")
        # base はそのまま。base を変えない派生クエリを 2 つ作って両方読む。
        derived_a = base.order_by("顧客ID")
        derived_b = base.order_by("金額", desc=True).limit(1)
        rows_a = derived_a.read().to_rows()
        rows_b = derived_b.read().to_rows()
        # 派生 A は where 条件のみ → 3 件
        assert len(rows_a) == 3
        # 派生 B は limit 1 → 1 件
        assert len(rows_b) == 1
        # base を読み直しても 3 件のまま（途中で何かに影響を受けていない）
        assert len(base.read()) == 3

    def test_where_does_not_mutate_original(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        original = db.table("顧客")
        after_where = original.where("状態", "=", "有効")
        # 元の全件と派生後を比べると
        assert len(original.read()) == 4
        assert len(after_where.read()) == 3


# ── SQL インジェクション ──────────────────────────────────────────────────


class TestSqlInjection:
    def test_value_with_drop_table_does_not_drop(self, tmp_path: Path) -> None:
        """値に ``'; DROP TABLE 顧客; --`` を入れても表は消えない。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        payload = "'; DROP TABLE 顧客; --"
        # where 値として渡す
        rows = db.table("顧客").where("状態", "=", payload).read().to_rows()
        # 一致しないので 0 件
        assert len(rows) == 0
        # 表は無事
        assert db.table("顧客").count() == 4

    def test_value_with_drop_table_inserted_as_literal(self, tmp_path: Path) -> None:
        """同じ文字列を挿入しても文字列として扱われる（= で再検索できる）。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        payload = "001'; DROP TABLE 顧客; --"
        db.table("顧客").insert(
            Table(["顧客ID", "状態", "金額"], [{"顧客ID": "999", "状態": payload, "金額": 0}])
        )
        rows = db.table("顧客").where("状態", "=", payload).read().to_rows()
        assert len(rows) == 1
        assert rows[0]["状態"] == payload
        # 表も無事
        assert db.table("顧客").count() == 5

    def test_column_name_with_quote_is_supported(self, tmp_path: Path) -> None:
        """``"`` を含む列名も表・列のエスケープで扱える。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        # 列名に " を含める
        col_name = 'weird"col'
        db.table("t").create(columns=["id", col_name], primary_key="id")
        db.table("t").insert(Table(["id", col_name], [{"id": "1", col_name: "v"}]))
        rows = db.table("t").read().to_rows()
        assert rows[0][col_name] == "v"


# ── 名前解決 ──────────────────────────────────────────────────────────


class TestNameResolution:
    def test_table_not_found_raises_with_list(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError) as exc_info:
            db.table("存在しない").read()
        message = str(exc_info.value)
        assert "表が見つかりません" in message
        assert "存在しない" in message
        assert "顧客" in message

    def test_column_not_found_raises_with_list(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError) as exc_info:
            db.table("顧客").where("存在しない列", "=", 1)
        message = str(exc_info.value)
        assert "列が見つかりません" in message
        assert "顧客.存在しない列" in message
        assert "顧客ID" in message  # 存在する列が含まれている

    def test_read_with_unknown_column_raises(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="列が見つかりません"):
            db.table("顧客").read(columns=["無い列"])


# ── 書き込み ──────────────────────────────────────────────────────────


class TestWrite:
    def test_insert_returns_count(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        n = db.table("顧客").insert(
            Table(["顧客ID", "状態", "金額"], [{"顧客ID": "1", "状態": "有効", "金額": 100}])
        )
        assert n == 1

    def test_insert_with_extra_column_raises(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="列が見つかりません"):
            db.table("顧客").insert(
                Table(
                    ["顧客ID", "状態", "金額", "余分"],
                    [{"顧客ID": "1", "状態": "有効", "金額": 0, "余分": "x"}],
                )
            )

    def test_insert_with_datetime_serialized_as_iso(self, tmp_path: Path) -> None:
        """日付・datetime は ISO 文字列で保存される。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("events").create(
            columns=["id", "d", "dt"],
            types={"id": str},
            primary_key="id",
        )
        # Table の型ヒントを尊重してそのまま渡す
        # ``datetime`` / ``date`` / pandas Timestamp は ``_value_for_sql`` が ISO 文字列へ変換する
        d = date(2024, 1, 15)
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        db.table("events").insert(Table(["id", "d", "dt"], [{"id": "1", "d": d, "dt": dt}]))
        # 保存された中身は文字列
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT d, dt FROM events").fetchone()
        assert row[0] == "2024-01-15"
        # ``tzinfo=UTC`` を付けたので ISO 文字列にも ``+00:00`` が付く
        assert row[1] == "2024-01-15T10:30:00+00:00"

    def test_insert_midway_failure_keeps_zero(self, tmp_path: Path) -> None:
        """primary_key 重複で insert が失敗したら、表は 0 行のまま。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        before = db.table("顧客").count()
        with pytest.raises(SQLiteError):
            db.table("顧客").insert(
                Table(
                    ["顧客ID", "状態", "金額"],
                    [
                        {"顧客ID": "010", "状態": "有効", "金額": 100},
                        {"顧客ID": "001", "状態": "有効", "金額": 999},  # PK 重複
                        {"顧客ID": "011", "状態": "有効", "金額": 200},
                    ],
                )
            )
        # 全件巻き戻し → before のまま
        assert db.table("顧客").count() == before

    def test_insert_zero_row_table_returns_zero(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        n = db.table("顧客").insert(Table(["顧客ID", "状態", "金額"], []))
        assert n == 0

    def test_update_requires_where(self, tmp_path: Path) -> None:
        """where が無い update はエラー"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="where 条件が必要"):
            db.table("顧客").update({"状態": "退会"})

    def test_update_rejects_limit(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="limit は付けられません"):
            (db.table("顧客").where("顧客ID", "=", "001").limit(1).update({"状態": "退会"}))

    def test_update_rejects_order_by(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="order_by は付けられません"):
            (
                db.table("顧客")
                .where("顧客ID", "=", "001")
                .order_by("顧客ID")
                .update({"状態": "退会"})
            )

    def test_update_returns_count(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        n = db.table("顧客").where("状態", "=", "有効").update({"金額": 0})
        assert n == 3

    def test_update_with_unknown_column_raises(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="列が見つかりません"):
            db.table("顧客").where("顧客ID", "=", "001").update({"無い列": "x"})

    def test_update_empty_values_raises(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(ValueError, match="values は空"):
            db.table("顧客").where("顧客ID", "=", "001").update({})

    def test_delete_requires_where(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="where 条件が必要"):
            db.table("顧客").delete()

    def test_delete_rejects_limit(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        with pytest.raises(SQLiteError, match="limit は付けられません"):
            (db.table("顧客").where("顧客ID", "=", "001").limit(1).delete())

    def test_delete_returns_count(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        n = db.table("顧客").where("状態", "=", "解約").delete()
        assert n == 1
        assert db.table("顧客").count() == 3


# ── create ──────────────────────────────────────────────────────────


class TestCreate:
    def test_create_creates_table(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("t").create(columns=["a", "b"], primary_key="a")
        assert "t" in db.tables()

    def test_create_with_types(self, tmp_path: Path) -> None:
        """``types`` で渡した列は対応する SQLite 型になる。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("t").create(
            columns=["a", "b", "c", "d"],
            types={"a": str, "b": int, "c": float},
        )
        # PRAGMA で型を確認
        with sqlite3.connect(path) as conn:
            rows = conn.execute('PRAGMA table_info("t")').fetchall()
        types_by_col = {r[1]: r[2] for r in rows}
        assert types_by_col["a"] == "TEXT"
        assert types_by_col["b"] == "INTEGER"
        assert types_by_col["c"] == "REAL"
        # 型指定なし
        assert types_by_col["d"] == ""

    def test_create_with_primary_key(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("t").create(columns=["id", "value"], primary_key="id")
        with sqlite3.connect(path) as conn:
            rows = conn.execute('PRAGMA table_info("t")').fetchall()
        # pk 1 = primary key 列
        pk_cols = [r[1] for r in rows if r[5] == 1]
        assert pk_cols == ["id"]

    def test_create_fails_if_table_exists(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="既に存在します"):
            db.table("顧客").create(columns=["a"], primary_key="a")

    def test_create_requires_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        with pytest.raises(ValueError, match="1 つ以上"):
            db.table("t").create(columns=[])

    def test_create_primary_key_must_be_in_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        with pytest.raises(ValueError, match="primary_key は"):
            db.table("t").create(columns=["a"], primary_key="b")


# ── dry-run ──────────────────────────────────────────────────────────


class TestDryRun:
    def test_insert_dry_run_returns_count_and_does_not_change_file(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        before_bytes = path.read_bytes()
        with dry_run():
            n = db.table("顧客").insert(
                Table(["顧客ID", "状態", "金額"], [{"顧客ID": "X", "状態": "有効", "金額": 1}])
            )
        assert n == 1
        assert path.read_bytes() == before_bytes

    def test_update_dry_run_returns_count_and_does_not_change_file(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        before_bytes = path.read_bytes()
        with dry_run():
            n = db.table("顧客").where("状態", "=", "有効").update({"金額": 0})
        assert n == 3
        assert path.read_bytes() == before_bytes

    def test_delete_dry_run_returns_count_and_does_not_change_file(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        before_bytes = path.read_bytes()
        with dry_run():
            n = db.table("顧客").where("状態", "=", "解約").delete()
        assert n == 1
        assert path.read_bytes() == before_bytes

    def test_create_dry_run_does_not_create_table(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        with dry_run():
            db = SQLite(path)
            db.table("t").create(columns=["a"], primary_key="a")
            # dry-run 中は create が no-op なので表は無い
            assert "t" not in db.tables()
        # dry-run を抜けても表は作られていない
        db2 = SQLite(path)
        assert "t" not in db2.tables()

    def test_create_true_dry_run_does_not_create_file(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        with dry_run():
            SQLite(path, create=True)
        assert not path.exists()


# ── ファイル管理 ────────────────────────────────────────────────────────


class TestFileHandling:
    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "missing.db"
        with pytest.raises(ComkenFileNotFoundError):
            SQLite(path)

    def test_create_true_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "new.db"
        SQLite(path, create=True)
        assert path.exists()
        assert path.stat().st_size == 0  # ファイル本体は空（表はまだ無い）

    def test_can_rename_after_read(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        db.table("顧客").read()
        path.rename(tmp_path / "renamed.db")
        assert (tmp_path / "renamed.db").exists()

    def test_can_delete_after_read(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        db.table("顧客").read()
        path.unlink()
        assert not path.exists()

    def test_can_rename_after_write(self, tmp_path: Path) -> None:
        db, path = _new_db(tmp_path)
        _seed(db)
        db.table("顧客").where("顧客ID", "=", "001").update({"金額": 0})
        path.rename(tmp_path / "renamed.db")
        assert (tmp_path / "renamed.db").exists()


# ── 日本語 ──────────────────────────────────────────────────────────


class TestJapanese:
    def test_japanese_table_and_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("顧客マスタ").create(
            columns=["顧客ID", "氏名", "状態"],
            types={"顧客ID": str, "氏名": str, "状態": str},
            primary_key="顧客ID",
        )
        rows = Table(
            ["顧客ID", "氏名", "状態"],
            [
                {"顧客ID": "001", "氏名": "山田太郎", "状態": "有効"},
                {"顧客ID": "002", "氏名": "鈴木花子", "状態": "解約"},
            ],
        )
        db.table("顧客マスタ").insert(rows)
        results = db.table("顧客マスタ").where("状態", "=", "有効").read().to_rows()
        assert len(results) == 1
        assert results[0]["氏名"] == "山田太郎"


# ── iter_rows ────────────────────────────────────────────────────────


class TestIterRows:
    def test_iter_rows_yields_dicts_one_at_a_time(self, tmp_path: Path) -> None:
        """``iter_rows()`` は 1 行ずつ dict で流す。"""
        db, _ = _new_db(tmp_path)
        _seed(db)
        iterator = db.table("顧客").iter_rows()
        assert not isinstance(iterator, list)
        rows: list[dict[str, object]] = list(iterator)
        assert len(rows) == 4
        assert all(isinstance(r, dict) for r in rows)

    def test_iter_rows_with_columns(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        iterator = db.table("顧客").iter_rows(columns=["顧客ID"])
        rows = list(iterator)
        assert list(rows[0].keys()) == ["顧客ID"]

    def test_iter_rows_validates_table_and_columns_immediately(self, tmp_path: Path) -> None:
        """表・列のエラーは呼んだ時点で出る（遅延しない）。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="列が見つかりません"):
            # イテレータ変数を消費する前に例外が出る
            db.table("顧客").iter_rows(columns=["無い列"])

    def test_iter_rows_break_closes_connection(self, tmp_path: Path) -> None:
        """``break`` で抜けたあとにファイルをリネームできる（接続が閉じている）。"""
        db, path = _new_db(tmp_path)
        _seed(db)
        for row in db.table("顧客").iter_rows():
            _ = row
            break
        # 接続が閉じていればリネームできる
        path.rename(tmp_path / "after_break.db")
        assert (tmp_path / "after_break.db").exists()

    def test_iter_rows_with_where_and_order(self, tmp_path: Path) -> None:
        db, _ = _new_db(tmp_path)
        _seed(db)
        rows = list(
            db.table("顧客").where("状態", "=", "有効").order_by("金額", desc=True).iter_rows()
        )
        assert [r["金額"] for r in rows] == [2000, 1500, 1000]


# ── 既存例外への露出 ────────────────────────────────────────────────────


class TestExceptionHierarchy:
    def test_sqlite_error_is_comken_error(self) -> None:
        """``SQLiteError`` は ``ComkenError`` を継承している。"""
        from comken.exceptions import ComkenError

        assert issubclass(SQLiteError, ComkenError)


# 軽いサニティチェック: イテレータとして返り、内部関数を分けて実装しているか
# （``iter_rows`` が _iter_rows を呼んでいるかの薄い確認）。
def test_iter_rows_returns_iterator(tmp_path: Path) -> None:
    db, _ = _new_db(tmp_path)
    _seed(db)
    result = db.table("顧客").iter_rows()
    assert isinstance(result, Iterator)
