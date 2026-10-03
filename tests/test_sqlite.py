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


def _admin_share_for(tmp_path: Path) -> str:
    """``tmp_path`` のドライブレターに対応する Windows 管理共有パスを返す。

    ``C:\\...`` なら ``\\\\localhost\\C$``。Home エディション等では
    管理共有が無効なので ``Path.is_dir()`` で開けるか別途確かめる。
    """
    drive_letter = tmp_path.drive.rstrip(":")
    return f"\\\\localhost\\{drive_letter}$"


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


# ── ファイルを作らない経路 ──────────────────────────────────────────────


class TestNoSideEffectsOnRead:
    """``_open()`` がファイルを作らないこと・dry-run 中で create=true でも作らないこと。"""

    def test_tables_on_missing_file_in_dry_run_returns_empty(self, tmp_path: Path) -> None:
        """dry-run 中でファイルが無い状態でも ``tables()`` は ``[]`` を返し、ファイルを作らない。"""
        path = tmp_path / "missing.db"
        assert not path.exists()
        with dry_run():
            SQLite(path, create=True)  # dry-run 中はファイルが作られない
            db = SQLite(path)  # dry-run 中はインスタンスだけ作れる
            assert db.tables() == []
        assert not path.exists()

    def test_tables_does_not_grow_file(self, tmp_path: Path) -> None:
        """通常時で ``tables()`` を呼んでも既存のファイルサイズは変化しない。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)  # 0 byte のファイルを作る
        before_size = path.stat().st_size
        db = SQLite(path)
        db.tables()
        assert path.stat().st_size == before_size

    def test_read_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """ファイルが有っても存在しない表を ``read()`` すると「表が見つかりません」。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").read()

    def test_iter_rows_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``iter_rows()`` も呼んだ時点で「表が見つかりません」を出す。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").iter_rows()

    def test_where_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``where()`` で存在しない表の列を指定すると「列が見つかりません」ではなく
        「表が見つかりません」を出す（打ち間違いの利用者向け）。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").where("顧客ID", "=", "001")

    def test_order_by_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``order_by()`` でも同じ。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").order_by("顧客ID")

    def test_count_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``count()`` でも表を先に確かめる。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").count()

    def test_insert_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``insert()`` も表を先に確かめる（既存表への列チェックで失敗する前に）。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").insert(Table(["顧客ID"], [{"顧客ID": "1"}]))

    def test_update_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``update()`` も表を先に確かめる。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").where("顧客ID", "=", "001").update({"状態": "退会"})

    def test_delete_on_missing_table_raises_table_not_found(self, tmp_path: Path) -> None:
        """``delete()`` も表を先に確かめる。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError, match="表が見つかりません"):
            db.table("存在しない表").where("顧客ID", "=", "001").delete()


class TestDryRunNoFileCreation:
    """``dry-run`` 中で ``create=True`` にしても、その後の操作でファイルができないこと。"""

    def test_tables_does_not_create_file_in_dry_run(self, tmp_path: Path) -> None:
        path = tmp_path / "dryrun.db"
        assert not path.exists()
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            assert db.tables() == []
        assert not path.exists()

    def test_create_table_does_not_create_file_in_dry_run(self, tmp_path: Path) -> None:
        path = tmp_path / "dryrun.db"
        assert not path.exists()
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            db.table("t").create(columns=["a", "b"], primary_key="a")
        # dry-run 中の create().table() はファイルも表も作らない
        assert not path.exists()

    def test_insert_does_not_create_file_in_dry_run(self, tmp_path: Path) -> None:
        path = tmp_path / "dryrun.db"
        assert not path.exists()
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            n = db.table("t").insert(Table(["a", "b"], [{"a": "1", "b": "x"}]))
        # 渡した件数を返す
        assert n == 1
        # ファイルは作られない
        assert not path.exists()

    def test_read_does_not_create_file_in_dry_run(self, tmp_path: Path) -> None:
        """dry-run 中でファイルが無い場合の read は「表が見つかりません」を投げる。"""
        path = tmp_path / "dryrun.db"
        assert not path.exists()
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            with pytest.raises(SQLiteError, match="表が見つかりません"):
                db.table("t").read()
        assert not path.exists()

    def test_count_does_not_create_file_in_dry_run(self, tmp_path: Path) -> None:
        """dry-run 中でファイルが無い場合の count は「表が見つかりません」を投げる。"""
        path = tmp_path / "dryrun.db"
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            with pytest.raises(SQLiteError, match="表が見つかりません"):
                db.table("t").count()
        assert not path.exists()

    def test_update_does_not_create_file_in_dry_run_returns_zero(self, tmp_path: Path) -> None:
        """dry-run 中でファイルが無い場合の update は 0 件を返す。"""
        path = tmp_path / "dryrun.db"
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            n = db.table("t").where("a", "=", "1").update({"b": "y"})
        assert n == 0
        assert not path.exists()

    def test_delete_does_not_create_file_in_dry_run_returns_zero(self, tmp_path: Path) -> None:
        """dry-run 中でファイルが無い場合の delete は 0 件を返す。"""
        path = tmp_path / "dryrun.db"
        with dry_run():
            SQLite(path, create=True)
            db = SQLite(path)
            n = db.table("t").where("a", "=", "1").delete()
        assert n == 0
        assert not path.exists()


class TestFileMissingRaises:
    """``dry-run`` で無い通常時にファイルが消えていたら ``ComkenFileNotFoundError``。"""

    def test_init_raises_file_not_found_when_missing(self, tmp_path: Path) -> None:
        """通常時、ファイルが無いと ``SQLite(path)`` 時点で ``ComkenFileNotFoundError``。"""
        path = tmp_path / "missing.db"
        with pytest.raises(ComkenFileNotFoundError):
            SQLite(path)

    def test_tables_raises_file_not_found_after_delete(self, tmp_path: Path) -> None:
        """ファイル作成後にファイルが消えていたら ``tables()`` で ``ComkenFileNotFoundError``。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        path.unlink()
        with pytest.raises(ComkenFileNotFoundError):
            db.tables()

    def test_read_raises_file_not_found_after_delete(self, tmp_path: Path) -> None:
        """ファイル作成後にファイルが消えていたら ``read()`` で ``ComkenFileNotFoundError``。"""
        path = tmp_path / "data.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("t").create(columns=["a"], primary_key="a")
        path.unlink()
        with pytest.raises(ComkenFileNotFoundError):
            db.table("t").read()


# ── パス周りの特殊ケース ──────────────────────────────────────────────


class TestPathEdgeCases:
    def test_japanese_folder_and_filename_with_space_and_hash(self, tmp_path: Path) -> None:
        """日本語・空白・``#`` を含むフォルダ名・ファイル名でも読み書きできる。"""
        folder = tmp_path / "顧客 #1 フォルダ"
        folder.mkdir()
        path = folder / "data #2.db"
        SQLite(path, create=True)
        db = SQLite(path)
        db.table("顧客マスタ").create(
            columns=["顧客ID", "氏名"],
            types={"顧客ID": str, "氏名": str},
            primary_key="顧客ID",
        )
        rows = Table(
            ["顧客ID", "氏名"],
            [
                {"顧客ID": "001", "氏名": "山田太郎"},
                {"顧客ID": "002", "氏名": "鈴木花子"},
            ],
        )
        db.table("顧客マスタ").insert(rows)
        result = db.table("顧客マスタ").where("氏名", "like", "%山%").read().to_rows()
        assert len(result) == 1
        assert result[0]["氏名"] == "山田太郎"
        # tables() でも取れる
        assert "顧客マスタ" in db.tables()

    def test_relative_path_works(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """相対パスで open / create / insert / read できる。"""
        monkeypatch.chdir(tmp_path)
        # 相対パスで SQLite を作る
        SQLite("rel.db", create=True)
        assert (tmp_path / "rel.db").exists()
        db = SQLite("rel.db")
        db.table("t").create(columns=["id", "value"], primary_key="id")
        db.table("t").insert(Table(["id", "value"], [{"id": "1", "value": "x"}]))
        rows = db.table("t").read().to_rows()
        assert len(rows) == 1
        assert rows[0]["value"] == "x"

    def test_drive_letter_uppercase_no_resolve_to_unc(self, tmp_path: Path) -> None:
        """``resolve()`` を使わないので、ドライブレターが UNC に変わらない。"""
        # tmp_path は既にドライブレター付きの絶対パス
        path = tmp_path / "drive.db"
        SQLite(path, create=True)
        db = SQLite(path)
        # tables() が動くこと（接続できれば UNC になっていない）
        assert db.tables() == []
        db.table("t").create(columns=["a"], primary_key="a")
        assert "t" in db.tables()

    def test_unc_path_create_insert_read(self, tmp_path: Path) -> None:
        """管理共有（``\\\\localhost\\<drv>$``）経由で create / insert / read できる。

        SQLite は UNC パスを ``file:////server/share/path`` の 4 つのスラッシュで
        開ける（``file://server/share/path`` の 2 つだと「ホスト名 server」と
        解釈されて開けない）。Home エディション等、管理共有が無効な環境では
        ``Path.is_dir()`` で開けないため ``pytest.skip`` で逃げる。
        """
        admin_share = _admin_share_for(tmp_path)
        if not Path(admin_share).is_dir():
            pytest.skip(f"管理共有 {admin_share} が開けないため UNC 経由のテストをスキップ")
        # 共有フォルダ内に書き戻す（tmp_path を経由せず直接 touch しても良いが、
        # クリーンアップを pytest に任せるために tmp_path 側で内容を確定させる）
        relative = tmp_path.name + "_unc.db"
        unc_path = Path(admin_share) / tmp_path.relative_to(tmp_path.anchor) / relative
        try:
            SQLite(unc_path, create=True)
            db = SQLite(unc_path)
            db.table("t").create(columns=["id", "value"], primary_key="id")
            db.table("t").insert(Table(["id", "value"], [{"id": "1", "value": "x"}]))
            rows = db.table("t").read().to_rows()
            assert len(rows) == 1
            assert rows[0]["value"] == "x"
        finally:
            if unc_path.exists():
                unc_path.unlink()


# ── `_file_uri()` の文字列組み立て ──────────────────────────────────────────────


class TestFileUri:
    """``SQLite._file_uri()`` の URI 文字列が想定どおり組み立てられるか。

    環境（ファイルシステムの UNC 共有可否）に依らず、文字列の組み立て
    ルール自体は常に同じなので、ここは ``tmp_path`` を経由せず
    ``SQLite(path)`` を直接作って ``_file_uri()`` を呼ぶ（ファイル本体
    が無いと ``__init__`` が ``ComkenFileNotFoundError`` を投げるので、
    touch で空ファイルを作ってから覗く）。
    """

    @staticmethod
    def _uri(path: Path) -> str:
        """``_file_uri()`` を呼ぶために、ファイルを一時的に用意してから覗く。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return SQLite(path)._file_uri()

    def test_drive_letter_path(self, tmp_path: Path) -> None:
        """ドライブレターは ``file:/C:/...`` の 1 つのスラッシュで組み立てる。"""
        uri = self._uri(tmp_path / "x.db")
        # ``file:/C:/...`` の形になること。``file://`` 始まりだと UNC と
        # 同じ形になり SQLite が誤認する。
        assert uri.startswith("file:/")
        assert not uri.startswith("file://")
        # ``file:/`` の後に ``as_posix()`` のパスがそのまま続き、最後が
        # ``?mode=rw`` で終わる。
        assert uri.endswith("/x.db?mode=rw")
        # ドライブレター（例: ``C:``）が ``/`` の直後に来ること
        drive = tmp_path.drive  # 例: ``C:``
        assert f"file:/{drive}/" in uri

    def test_unc_path_uses_four_slashes(self, tmp_path: Path) -> None:
        """UNC パスは ``file:////server/share/...`` の 4 つのスラッシュで組み立てる。

        ``//`` 2 つだけの ``file://server/...`` は SQLite がホスト名として
        解釈して開けない（Access の置き換え用途で致命的）。
        ``as_posix()`` が ``//server/share/...`` を作るパスを直接 ``_path``
        に流し込んで ``_file_uri()`` だけを覗く（ファイル本体は touch で
        用意し、``_path`` を差し替えて URI だけ取り出す）。
        """
        path = tmp_path / "unc_marker.db"
        path.touch()
        db = SQLite(path)
        # ``_path`` は通常の属性（``@dataclass`` ではない）なので代入できる。
        # ``_file_uri()`` は ``self._path`` しか見ないので、本物のファイル
        # を開かずに URI の文字列だけ確認できる。
        db._path = Path("//test_server/share/dir/x.db")  # type: ignore[misc]
        assert db._file_uri() == "file:////test_server/share/dir/x.db?mode=rw"

    def test_special_characters_are_escaped(self, tmp_path: Path) -> None:
        """``#`` 空白 日本語は ``%XX`` エスケープされる。

        エスケープ漏れがあると ``mode=rw`` のクエリが効かなくなる /
        ファイル名の一部がクエリと誤認される事故になる。
        ファイル名に使えない ``?`` は下の ``test_question_mark_is_escaped``
        で ``_path`` を差し替えて ``_file_uri()`` だけを覗く。
        """
        folder = tmp_path / "顧客 #1 フォルダ"
        folder.mkdir()
        path = folder / "data.db"
        uri = self._uri(path)
        path_part, query = uri.rsplit("?", 1)
        # クエリは必ず ``mode=rw`` 1 つだけ
        assert query == "mode=rw"
        # パス部に生の ``#`` 空白 は残らない（URI として壊れる）
        assert "#" not in path_part
        assert " " not in path_part
        # 日本語はパーセントエンコードされる（``%E5%AE%A2`` のような形に
        # 分解される）
        assert "%" in path_part

    def test_question_mark_is_escaped(self, tmp_path: Path) -> None:
        """``?`` がファイル名にあっても URI でエスケープされる。

        Windows のファイル名には ``?`` を使えないので ``_path`` を直接
        差し替えて ``_file_uri()`` の出力だけ覗く。エスケープ漏れがあると
        ``?`` 以降がクエリ文字列として扱われ ``mode=rw`` が効かなくなる。
        """
        path = tmp_path / "marker.db"
        path.touch()
        db = SQLite(path)
        db._path = Path("C:/data/x.db?q=1")  # type: ignore[misc]
        # ``?`` と ``=`` はどちらも ``safe="/:"`` に含まれないので
        # パーセントエンコードされる（``?`` がクエリ区切りとして
        # 効くと ``mode=rw`` が壊れる）。
        assert db._file_uri() == "file:/C:/data/x.db%3Fq%3D1?mode=rw"


# ── `ComkenFileNotFoundError` のメッセージ ──────────────────────────────────────────────


class TestErrorMessages:
    def test_table_not_found_lists_existing_tables(self, tmp_path: Path) -> None:
        """表が見つからないときは「存在する表: [...]」も表示する。"""
        db, _ = _new_db(tmp_path)
        with pytest.raises(SQLiteError) as exc_info:
            db.table("typo").read()
        message = str(exc_info.value)
        assert "表が見つかりません" in message
        assert "typo" in message
        assert "顧客" in message  # 存在する表が含まれる
