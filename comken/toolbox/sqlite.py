"""comken/toolbox/sqlite.py — SQLite データベースへの読み書き。

社内で Access の代わりに SQLite を使う場面を想定した薄い API。
SQL 文を直接書かずにメソッドを繋いで読み書きできるようにする。
SQLite は Python 標準の ``sqlite3`` だけで扱い、追加の依存は入れない。

設計の要点:

- 表 / 列は呼び出し時に ``sqlite_master`` / ``PRAGMA table_info`` で
  必ず実在を確かめ、二重引用符で囲んで SQL へ渡す。``"`` は ``""`` に
  エスケープする（SQLite の識別子のエスケープ規則）。
- 値は常に ``?`` プレースホルダーで渡す（SQL 文字列への値の埋め込みはしない）。
- 接続はメソッド単位で開いて閉じる（``with`` で長く開いたままにしない）。
  ファイルがロックされた場合は ``SQLiteError`` にメッセージごと包む。
- 書き込み（create / insert / update / delete）は 1 呼び出し 1 トランザクション。
  途中で失敗したら巻き戻す。
- ``update`` / ``delete`` は ``where`` が無いクエリでは送らない
  （全件書き換え事故を防ぐため）。``limit`` / ``order_by`` を付けた
  クエリでも送らない（意図しない行が当たるのを防ぐため）。
- ``dry-run`` 中は書き込みを実行せずログだけ出し、戻り値は insert なら
  渡した件数、update / delete は ``SELECT COUNT(*)`` で数えた件数、
  create は何もしない。
- 接続は URI 形式で ``mode=rw`` を使うため、ファイルが無いと
  ``OperationalError`` が飛ぶ（黙って新規ファイルを作る挙動を抑止）。
  ファイル作成は ``__init__`` の ``create=True`` だけが担う。
  ``dry-run`` 中でファイルが無い場合は各メソッドが個別に no-op /
  ログのみに分岐する。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from comken.core.table.model import Table
from comken.exceptions import ComkenFileNotFoundError
from comken.exceptions.office import SQLiteError
from comken.runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)

# 接続のタイムアウト秒。SQLite の既定は 5 秒で短いネットワークドライブ等では
# 「database is locked」が頻発するため長めに取る。
CONNECT_TIMEOUT_SECONDS = 30
# iter_rows() が 1 度に fetch する行数。全件メモリに載せないようにするため、
# CSV.iter_rows / Access.iter_rows と同じく小さめのサイズにする。
ROWS_BATCH_SIZE = 1000
# where() で受け付ける演算子の一覧。仕様 §5。
WHERE_OPERATORS: tuple[str, ...] = (
    "=",
    "!=",
    "<",
    "<=",
    ">",
    ">=",
    "in",
    "not in",
    "like",
    "is_null",
    "not_null",
)
# Python の型 → SQLite の型の対応。create() の types 引数だけに見る。
_PY_TYPE_TO_SQLITE_TYPE: dict[type[Any], str] = {
    str: "TEXT",
    int: "INTEGER",
    float: "REAL",
}


@dataclass(frozen=True)
class _WhereClause:
    """where() の1条件を表す内部表現。"""

    column: str
    op: str
    # is_null / not_null のときは値が無い（None）ことを示す。
    value: Any = None


@dataclass(frozen=True)
class _OrderBy:
    """order_by() の1要素を表す内部表現。"""

    column: str
    desc: bool = False


class SQLite:
    """SQLite データベースへの接続設定と表レベル操作。

    ``SQLite`` は接続を **メソッド単位** で開いて閉じる。
    ``with`` 文で包む API ではない（AccessDatabase のような使い方ではない）。
    1 操作ごとに ``sqlite3.connect`` / ``close`` するため、操作のあと
    ファイルをリネーム・削除しても接続は残らない。

    ファイルが無く ``create=False``（既定）なら ``ComkenFileNotFoundError``
    を投げる。``create=True`` なら無ければ作る（``dry-run`` 中は作らない）。
    拡張子の制限はしない（``.db`` / ``.sqlite`` / ``.sqlite3`` 以外でも可）。
    """

    def __init__(self, path: str | Path, *, create: bool = False) -> None:
        self._path = Path(path)
        if self._path.is_file():
            return
        if not create:
            if is_dry_run():
                # dry-run 中は create=False でもインスタンスを作る（ファイルは作らない）。
                # ファイルが無いままでも、その後の各操作は個別に no-op / ログだけになる。
                logger.debug("SQLite dry-run: ファイル無しでもインスタンス作成: %s", self._path)
                return
            raise ComkenFileNotFoundError("SQLite ファイル", self._path)
        if is_dry_run():
            # dry-run 中は create=True でもファイルを作らない（仕様 §9）。
            # ファイルが無いままでも、その後の操作はそれぞれ no-op / ログだけになる。
            logger.debug("SQLite dry-run: ファイル作成をスキップ: %s", self._path)
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 空ファイルを作る（テーブルはまだ無い）。テーブル作成は table().create() で行う。
        self._path.touch()

    @property
    def path(self) -> Path:
        """正規化したファイルパスを返す。"""
        return self._path

    def tables(self) -> list[str]:
        """データベースに含まれる表の名前を ``sqlite_master`` から集めて返す。

        SQLite 内部の表（``sqlite_`` で始まる名前）は除外する。
        並びはSQL の ``ORDER BY`` に任せて決定的になるよう整列済みで返す。
        ``dry-run`` 中でファイルが無いときは ``[]`` を返す（ファイルが
        無いので表も無い）。
        """
        if not self._path.is_file():
            if is_dry_run():
                return []
            raise ComkenFileNotFoundError("SQLite ファイル", self._path)
        with closing(self._open()) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master"
                " WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                " ORDER BY name"
            ).fetchall()
            return [row[0] for row in rows]

    def table(self, name: str) -> SQLiteQuery:
        """表に対する不変なクエリを返す。

        返り値の ``SQLiteQuery`` は **不変**。``where`` / ``order_by`` /
        ``limit`` は新しい ``SQLiteQuery`` を返し、元は変わらない（仕様 §2）。
        同じ ``base`` を使い回しても ``base.read()`` と ``base.where(...).read()``
        の結果が混ざることはない。

        ``create()`` だけは ``table()`` 直後に呼び出せるよう、表の事前検証は
        行わない（まだ存在しない表も対象になるため）。``read`` / ``count`` /
        ``insert`` / ``update`` / ``delete`` / ``iter_rows`` はそれぞれ実行時に
        表の存在を確かめる（仕様 §4）。
        """
        return SQLiteQuery(db=self, table=name)

    def _open(self) -> sqlite3.Connection:
        """新しい接続を開いて返す。``sqlite3.Error`` は ``SQLiteError`` に包む。

        URI 形式で ``mode=rw`` を指定するため、ファイルが無いと
        ``sqlite3.OperationalError`` が飛ぶ（``mode=rwc`` と違い、無ければ
        作らない）。ファイル作成は ``__init__`` の ``create=True`` だけが
        担う（仕様 §3）。``pathlib.Path.resolve()`` を使うと割り当て
        ドライブが UNC に変わるため使わない。
        """
        try:
            return sqlite3.connect(
                self._file_uri(),
                uri=True,
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
        except sqlite3.OperationalError as exc:
            # ``mode=rw`` で既存ファイルが無いときは "unable to open ..." 形式
            # のエラーが返る。それを ``ComkenFileNotFoundError`` に変換する。
            if "unable to open" in str(exc).lower():
                raise ComkenFileNotFoundError("SQLite ファイル", self._path) from exc
            raise _connection_error(self._path, exc) from exc
        except sqlite3.Error as exc:
            raise _connection_error(self._path, exc) from exc

    def _file_uri(self) -> str:
        """``file:...?mode=rw`` 形式の URI を作る。

        Windows パス・日本語・空白・``#`` ``?`` を含むパスでも壊れない
        ように ``urllib.parse.quote`` でエスケープする。ドライブレターは
        先頭に ``/`` を足して ``file:/C:/...`` 形式にする（SQLite の URI
        仕様）。``pathlib.Path.resolve()`` は使わない（割り当てドライブが
        UNC に変わるため）。
        """
        abs_path = self._path if self._path.is_absolute() else self._path.absolute()
        posix = abs_path.as_posix()
        if not posix.startswith("/"):
            posix = "/" + posix
        # ``/`` と ``:`` はそのまま、他はエスケープ（``#`` ``?`` ``%``
        # 日本語・空白 等）。
        escaped = quote(posix, safe="/:")
        return f"file:{escaped}?mode=rw"

    def _ensure_table_exists(self, name: str) -> None:
        """表が ``sqlite_master`` に無ければエラー。"""
        with closing(self._open()) as connection:
            exists = (
                connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                    (name,),
                ).fetchone()
                is not None
            )
        if not exists:
            raise _table_not_found_error(name, self.tables())

    def _table_columns(self, name: str) -> list[str]:
        """``PRAGMA table_info`` から列名一覧を返す（順序は SQLite に従う）。"""
        with closing(self._open()) as connection:
            rows = connection.execute(f"PRAGMA table_info({quote_identifier(name)})").fetchall()
        return [row[1] for row in rows]

    def _ensure_column_exists(self, table: str, column: str) -> None:
        """列が無ければエラー。

        ``dry-run`` 中でファイルが無いときは列チェックをスキップする
        （``update`` / ``delete`` のメソッド本体でファイル無し判定を
        先に行うため、ここでは通す）。通常時でファイルが無いと
        ``ComkenFileNotFoundError`` を投げる。
        """
        if not self._path.is_file():
            if is_dry_run():
                return
            raise ComkenFileNotFoundError("SQLite ファイル", self._path)
        existing = self._table_columns(table)
        if column not in existing:
            raise _column_not_found_error(table, column, existing)

    def _table_exists_in_master(self, name: str) -> bool:
        """``sqlite_master`` に表があるかを返す（``create`` が既存チェックで使う）。

        ``tables()`` は ``sqlite_`` で始まる内部表を除外してソートした結果を
        返すが、``create`` では内部表を含む全表を確認したいので、別途
        ``sqlite_master`` を直接見る。
        """
        with closing(self._open()) as connection:
            row = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            ).fetchone()
        return row is not None


@dataclass(frozen=True)
class SQLiteQuery:
    """1つの表に対する不変な読み書きの問い合わせ。

    ``SQLite.table()`` が返す。``where`` / ``order_by`` / ``limit`` を呼ぶと
    **新しい** ``SQLiteQuery`` が返り、自分自身は変わらない（仕様 §1）。

    書き込み（``create`` / ``insert`` / ``update`` / ``delete``）は
    1 呼び出し 1 トランザクションで実行する。途中で失敗したら巻き戻す
    （insert で 500 件目失敗 → 0 件、仕様 §8）。

    ``dry-run`` 中は書き込みを実行せずログだけ出し、戻り値は
    ``insert`` なら渡した件数、``update`` / ``delete`` なら ``SELECT COUNT(*)``
    で数えた件数、``create`` は何もしない（仕様 §9）。

    ``dry-run`` 中でファイルが無い場合は、各メソッドが個別に
    no-op / 「表が見つかりません」 / ログだけ 0 件 / 渡した件数 のいずれかに
    分岐する（仕様 §9、§10）。通常時にファイルが消えていたら
    ``ComkenFileNotFoundError`` を投げる。
    """

    db: SQLite
    table: str
    wheres: tuple[_WhereClause, ...] = field(default=())
    order_bys: tuple[_OrderBy, ...] = field(default=())
    # フィールド名を ``_limit`` 下にして ``limit()`` メソッドとぶつからないようにする。
    # dataclass 内のフィールド名とメソッド名が同名で重なると Pyright が
    # ``reportDeclaredRedeclaration`` を出すため、片方を下げる。
    _limit: int | None = None

    def where(self, column: str, op: str, value: Any = None) -> SQLiteQuery:
        """条件を追加した新しいクエリを返す。

        複数の ``where`` は AND で結合する（仕様 §5）。
        ``op`` は ``"=" "!=" "<" "<=" ">" ">=" "in" "not in" "like"
        "is_null" "not_null"`` のいずれか。それ以外は ``ValueError``。
        ``in`` / ``not in`` は ``value`` に list / tuple（空なら ``ValueError``）。
        ``is_null`` / ``not_null`` は ``value`` を渡してはいけない。
        """
        if op not in WHERE_OPERATORS:
            raise ValueError(
                f"where の op は次のいずれかから指定してください: {list(WHERE_OPERATORS)}\n"
                f"対処: 受け付ける演算子は {list(WHERE_OPERATORS)} です。"
                "結合・集計は作らない方針なので、Python 側で読んでから行ってください。"
            )
        if op in ("is_null", "not_null"):
            if value is not None:
                raise ValueError(
                    f"where の op が {op!r} のときは value を渡さないでください。"
                    "\n対処: where(column, op) のように value を省略してください。"
                )
        else:
            if value is None:
                raise ValueError(
                    f"where の op が {op!r} のときは value が必要です。"
                    "\n対処: 比較する値を指定してください。"
                    "NULL を比較したいときは 'is_null' / 'not_null' を使ってください。"
                )
            if op in ("in", "not in"):
                if not isinstance(value, (list, tuple)):
                    raise ValueError(
                        f"where の op が {op!r} のときは value に list または tuple を"
                        "指定してください。"
                    )
                if len(value) == 0:
                    raise ValueError(f"where の op が {op!r} のときは value を空にできません。")
        # 列の前に表の存在を先に確かめる。表が無ければ「列が見つかりません」ではなく
        # 「表が見つかりません」を出す（打ち間違いの利用者向け、仕様 §4 補足）。
        self._ensure_table_for_query()
        self.db._ensure_column_exists(self.table, column)
        return replace(
            self,
            wheres=(*self.wheres, _WhereClause(column, op, value)),
        )

    def order_by(self, column: str, *, desc: bool = False) -> SQLiteQuery:
        """並び順を追加した新しいクエリを返す。複数回で優先順に並ぶ（仕様 §6）。"""
        # 列の前に表の存在を先に確かめる。表が無ければ「列が見つかりません」ではなく
        # 「表が見つかりません」を出す。
        self._ensure_table_for_query()
        self.db._ensure_column_exists(self.table, column)
        return replace(
            self,
            order_bys=(*self.order_bys, _OrderBy(column, desc)),
        )

    def limit(self, n: int) -> SQLiteQuery:
        """最大件数を追加した新しいクエリを返す。``n`` は 1 以上（仕様 §6）。"""
        if not isinstance(n, int) or n < 1:
            raise ValueError("limit は 1 以上の整数を指定してください。")
        return replace(self, _limit=n)

    # ── 読み込み ────────────────────────────────────────────────────────

    def read(self, columns: Sequence[str] | None = None) -> Table:
        """クエリに合致する行を読み込み ``Table`` で返す。

        ``columns`` を渡したらその列だけを ``SELECT`` する（順もその順）。
        ``None``（既定）なら全列を返す。``NULL`` は ``None``（仕様 v2）。
        """
        # 表が無ければここで明示的にエラー（``_resolve_columns`` が PRAGMA だけ
        # 叩いて空リストを返すケースを放置しない）。
        result_columns = self._resolve_columns(columns)
        sql, params = self._compile_select(result_columns)
        logger.debug(
            "SQLite read: %s, %d 列, wheres=%d, order_bys=%d, limit=%s",
            self.table,
            len(result_columns),
            len(self.wheres),
            len(self.order_bys),
            self._limit,
        )
        with closing(self.db._open()) as connection:
            try:
                cursor = connection.execute(sql, params)
                rows = [dict(zip(result_columns, row, strict=True)) for row in cursor.fetchall()]
            except sqlite3.Error as exc:
                raise _wrap_sqlite_error("read", self.table, exc) from exc
        return Table(result_columns, rows)

    def iter_rows(self, columns: Sequence[str] | None = None) -> Iterator[dict[str, Any]]:
        """クエリに合致する行を 1 行ずつ ``dict`` で返すイテレータ。

        内部は ``fetchmany`` で少しずつ取るため、全件をメモリに載せない。
        表・列のエラーは **呼んだ時点で** 投げる（仕様 v2）。生成器本体は
        内部関数 ``_iter_rows`` に分けているので、``break`` で抜けると
        ``with closing(...)`` が接続を閉じる。
        """
        # 生成器本体を遅延評価するため、ここでは事前検証だけ済ませて
        # SQL と列名だけ確定する。
        result_columns = self._resolve_columns(columns)
        sql, params = self._compile_select(result_columns)
        logger.debug(
            "SQLite iter_rows: %s, %d 列, wheres=%d, order_bys=%d, limit=%s",
            self.table,
            len(result_columns),
            len(self.wheres),
            len(self.order_bys),
            self._limit,
        )
        return self._iter_rows(sql, params, result_columns)

    def _iter_rows(
        self,
        sql: str,
        params: Sequence[Any],
        result_columns: Sequence[str],
    ) -> Iterator[dict[str, Any]]:
        """``iter_rows()`` の生成器本体。``with closing(...)`` で接続を確実に閉じる。

        ``execute`` / ``fetchmany`` が ``sqlite3.Error`` を投げたら
        ``_wrap_sqlite_error`` で包む（仕様 §12）。接続の ``_open`` 中に
        ``ComkenFileNotFoundError`` が出るのは呼び出し側で先に処理する想定。
        """
        with closing(self.db._open()) as connection:
            try:
                cursor = connection.execute(sql, params)
            except sqlite3.Error as exc:
                raise _wrap_sqlite_error("iter_rows", self.table, exc) from exc
            while True:
                try:
                    rows = cursor.fetchmany(ROWS_BATCH_SIZE)
                except sqlite3.Error as exc:
                    raise _wrap_sqlite_error("iter_rows", self.table, exc) from exc
                if not rows:
                    break
                for row in rows:
                    yield dict(zip(result_columns, row, strict=True))

    def count(self) -> int:
        """クエリに合致する行数を ``SELECT COUNT(*)`` で返す。"""
        # 表が無ければ先に「表が見つかりません」を出す（``_compile_select`` だけ
        # 叩いて空 Table を返すケースを放置しない）。``dry-run`` 中でファイルが
        # 無いときも「表が見つかりません」を投げる（仕様 §1）。
        self._ensure_table_for_query()
        if is_dry_run() and not self.db._path.is_file():
            raise _table_not_found_error(self.table, [])
        sql, params = self._compile_select((), count_only=True)
        with closing(self.db._open()) as connection:
            try:
                row = connection.execute(sql, params).fetchone()
            except sqlite3.Error as exc:
                raise _wrap_sqlite_error("count", self.table, exc) from exc
        assert row is not None  # COUNT(*) は必ず 1 行返す。
        return int(row[0])

    # ── 書き込み ────────────────────────────────────────────────────────

    def insert(self, rows: Table) -> int:
        """``Table`` の全行を表に追加し、追加した件数を返す。

        ``Table`` の列が表に全部あること（無ければエラー）。``Table`` の値を
        そのまま渡す（``None`` → ``NULL``、日付は ISO 文字列に変換）。
        """
        # dry-run 中でファイルが無い場合は、表が無い扱いにして列の検査を
        # 飛ばしログだけ出して渡した件数を返す（仕様 §9）。
        if not self.db._path.is_file():
            if is_dry_run():
                dry_run_log(
                    "SQLite dry-run: 表は未作成（dry-run）のため挿入をスキップ: %s, %d 行, 列=%s",
                    self.table,
                    len(rows),
                    list(rows.columns),
                )
                return len(rows)
            raise ComkenFileNotFoundError("SQLite ファイル", self.db._path)
        # Table の列が DB の表に全部あるか先に検証する。1 行でも欠けると
        # 途中で SQL 落ちして中途半端にコミットされる事故になるため、
        # 表側の存在チェックはトランザクションの外で済ませておく。
        self.db._ensure_table_exists(self.table)
        existing = self.db._table_columns(self.table)
        for column in rows.columns:
            if column not in existing:
                raise _column_not_found_error(self.table, column, existing)
        if len(rows) == 0:
            return 0
        if is_dry_run():
            dry_run_log(
                "SQLite に挿入: %s, %d 行, 列=%s",
                self.table,
                len(rows),
                list(rows.columns),
            )
            return len(rows)

        cols_sql = ", ".join(quote_identifier(c) for c in rows.columns)
        placeholders = ", ".join("?" for _ in rows.columns)
        sql = f"INSERT INTO {quote_identifier(self.table)} ({cols_sql}) VALUES ({placeholders})"
        seq_of_params: list[tuple[Any, ...]] = []
        for row_dict in rows.to_rows():
            seq_of_params.append(tuple(_value_for_sql(row_dict[column]) for column in rows.columns))
        try:
            with closing(self.db._open()) as connection, connection:
                cursor = connection.executemany(sql, seq_of_params)
        except sqlite3.Error as exc:
            # executemany は途中で失敗するとトランザクションが巻き戻る
            # （``with connection:`` がコミットせず例外を投げる）仕様 §12。
            raise _wrap_sqlite_error("insert", self.table, exc) from exc
        return cursor.rowcount

    def update(self, values: dict[str, Any]) -> int:
        """``where`` 条件に合う行の ``values`` を更新し、更新件数を返す。

        ``where`` が無いクエリでは送らない（全件書き換え事故の防止、
        仕様 §7）。``limit`` / ``order_by`` を付けたクエリでも送らない
        （意図しない行が当たるのを防ぐため）。
        """
        self._validate_write_preconditions("update")
        # dry-run 中でファイルが無い、または表が無いときは 0 件を返す（仕様 §9）。
        if not self.db._path.is_file():
            if is_dry_run():
                dry_run_log(
                    "SQLite dry-run: 表は未作成（dry-run）のため update は 0 件: %s, 値=%s",
                    self.table,
                    values,
                )
                return 0
            raise ComkenFileNotFoundError("SQLite ファイル", self.db._path)
        self.db._ensure_table_exists(self.table)
        existing = self.db._table_columns(self.table)
        for column in values:
            if column not in existing:
                raise _column_not_found_error(self.table, column, existing)
        if not values:
            raise ValueError("update の values は空にできません。")
        if is_dry_run():
            count = self.count()
            dry_run_log(
                "SQLite を更新: %s, %d 件, 値=%s",
                self.table,
                count,
                values,
            )
            return count

        set_sql = ", ".join(f"{quote_identifier(c)} = ?" for c in values)
        where_sql, where_params = self._compile_where()
        params: list[Any] = [_value_for_sql(v) for v in values.values()]
        params.extend(where_params)
        sql = f"UPDATE {quote_identifier(self.table)} SET {set_sql}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        try:
            with closing(self.db._open()) as connection, connection:
                cursor = connection.execute(sql, params)
        except sqlite3.Error as exc:
            raise _wrap_sqlite_error("update", self.table, exc) from exc
        return cursor.rowcount

    def delete(self) -> int:
        """``where`` 条件に合う行を削除し、削除件数を返す。

        ``where`` が無いクエリでは送らない（仕様 §7）。``limit`` /
        ``order_by`` を付けたクエリでも送らない。
        """
        self._validate_write_preconditions("delete")
        # dry-run 中でファイルが無い、または表が無いときは 0 件を返す（仕様 §9）。
        if not self.db._path.is_file():
            if is_dry_run():
                dry_run_log(
                    "SQLite dry-run: 表は未作成（dry-run）のため delete は 0 件: %s",
                    self.table,
                )
                return 0
            raise ComkenFileNotFoundError("SQLite ファイル", self.db._path)
        self.db._ensure_table_exists(self.table)
        if is_dry_run():
            count = self.count()
            dry_run_log("SQLite から削除: %s, %d 件", self.table, count)
            return count
        where_sql, where_params = self._compile_where()
        sql = f"DELETE FROM {quote_identifier(self.table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        try:
            with closing(self.db._open()) as connection, connection:
                cursor = connection.execute(sql, where_params)
        except sqlite3.Error as exc:
            raise _wrap_sqlite_error("delete", self.table, exc) from exc
        return cursor.rowcount

    def create(
        self,
        columns: Sequence[str],
        *,
        types: Mapping[str, type[Any]] | None = None,
        primary_key: str | None = None,
    ) -> None:
        """表を作る。既に表があればエラー（仕様 §11）。

        ``types`` に書いた列だけ ``TEXT`` / ``INTEGER`` / ``REAL`` を付ける
        （``str`` → ``TEXT``、``int`` → ``INTEGER``、``float`` → ``REAL``）。
        ``primary_key`` は 1 列だけ指定可（無ければ付けない）。
        """
        if not columns:
            raise ValueError("create の columns は 1 つ以上指定してください。")
        # dry-run 中でファイルが無いときは表作成をスキップしログだけ出す
        # （仕様 §9）。ファイル作成は ``__init__`` の ``create=True`` だけが
        # 担うので、ここでは ``touch()`` しない。
        if not self.db._path.is_file():
            if is_dry_run():
                dry_run_log(
                    "SQLite dry-run: ファイル未作成のため表作成をスキップ: %s, columns=%s",
                    self.table,
                    list(columns),
                )
                return
            raise ComkenFileNotFoundError("SQLite ファイル", self.db._path)
        if self.db._table_exists_in_master(self.table):
            raise SQLiteError(
                f"表が既に存在します: {self.table}\n"
                "対処: 既存の表を使うか、別の表名を指定してください。"
            )
        if primary_key is not None and primary_key not in columns:
            raise ValueError(
                f"primary_key は columns のうちから1つ指定してください: primary_key={primary_key!r}"
            )
        if is_dry_run():
            dry_run_log(
                "SQLite に表を作成: %s, columns=%s, types=%s, primary_key=%s",
                self.table,
                list(columns),
                dict(types) if types else None,
                primary_key,
            )
            return

        column_defs: list[str] = []
        for column in columns:
            sql_type = _sqlite_column_type(types.get(column)) if types else ""
            pk = " PRIMARY KEY" if column == primary_key else ""
            column_defs.append(f"{quote_identifier(column)}{sql_type}{pk}")
        sql = f"CREATE TABLE {quote_identifier(self.table)} ({', '.join(column_defs)})"
        try:
            with closing(self.db._open()) as connection, connection:
                connection.execute(sql)
        except sqlite3.Error as exc:
            raise _wrap_sqlite_error("create", self.table, exc) from exc

    # ── 内部 ────────────────────────────────────────────────────────────

    def _ensure_table_for_query(self) -> None:
        """クエリ用の表・ファイルの存在を確認する。

        通常時はファイルが無いと ``ComkenFileNotFoundError`` を投げ、
        ``dry-run`` 中でファイルが無いときはスキップする（``update`` /
        ``delete`` はメソッド本体でログだけ 0 件に分岐する。読み込み系は
        ``_resolve_columns`` 側で「表が見つかりません」を投げる）。
        表の打ち間違いを「列が見つかりません」扱いしないための入口チェック
        （仕様 §4 補足）。
        """
        if not self.db._path.is_file():
            if is_dry_run():
                return
            raise ComkenFileNotFoundError("SQLite ファイル", self.db._path)
        self.db._ensure_table_exists(self.table)

    def _validate_write_preconditions(self, op: str) -> None:
        """書き込み前の必須条件（``where`` 必須、``limit`` / ``order_by`` 不可）を検査する。"""
        if not self.wheres:
            raise SQLiteError(
                f"{op} には where 条件が必要です。"
                f"（{self.table}）\n"
                "対処: where(...) で条件を指定してから呼び出してください。"
                "全件書き換えは事故のもとなので用意していません。"
            )
        if self._limit is not None:
            raise SQLiteError(
                f"{op} に limit は付けられません。limit を外してから呼び出してください。"
                f"（{self.table}）"
            )
        if self.order_bys:
            raise SQLiteError(
                f"{op} に order_by は付けられません。order_by を外してから呼び出してください。"
                f"（{self.table}）"
            )

    def _resolve_columns(self, columns: Sequence[str] | None) -> list[str]:
        """``read`` / ``iter_rows`` の ``columns`` 引数を確定する（順序保持）。

        表が無ければ先に ``SQLiteError``（表が見つかりません）を投げる。
        ``_table_columns`` は ``PRAGMA table_info`` を叩くため、存在しない表は
        空リストを返してしまう。それで「列が見つかりません」を返すと、原因が
        「表が無いこと」だと利用者に伝わらないため。``dry-run`` 中でファイルが
        無いときは「表が見つかりません」を投げる（仕様 §1）。
        """
        self._ensure_table_for_query()
        if is_dry_run() and not self.db._path.is_file():
            raise _table_not_found_error(self.table, [])
        if columns is None:
            return self.db._table_columns(self.table)
        result = list(columns)
        existing = self.db._table_columns(self.table)
        for column in result:
            if column not in existing:
                raise _column_not_found_error(self.table, column, existing)
        return result

    def _compile_select(
        self,
        columns: Sequence[str],
        *,
        count_only: bool = False,
    ) -> tuple[str, list[Any]]:
        """``SELECT``（または ``SELECT COUNT(*)``）の SQL とプレースホルダー値を返す。"""
        if count_only:
            select_sql = "SELECT COUNT(*)"
        else:
            if not columns:
                select_sql = "SELECT *"
            else:
                select_sql = "SELECT " + ", ".join(quote_identifier(c) for c in columns)
        sql_parts: list[str] = [select_sql, f"FROM {quote_identifier(self.table)}"]
        where_sql, params = self._compile_where()
        if where_sql:
            sql_parts.append(f"WHERE {where_sql}")
        if self.order_bys:
            order_clause = ", ".join(
                f"{quote_identifier(o.column)} {'DESC' if o.desc else 'ASC'}"
                for o in self.order_bys
            )
            sql_parts.append(f"ORDER BY {order_clause}")
        if self._limit is not None and not count_only:
            sql_parts.append(f"LIMIT {int(self._limit)}")
        return " ".join(sql_parts), params

    def _compile_where(self) -> tuple[str, list[Any]]:
        """``WHERE`` 句とプレースホルダー値（``?`` の順）を組み立てる。"""
        if not self.wheres:
            return "", []
        clauses: list[str] = []
        params: list[Any] = []
        for clause in self.wheres:
            column = quote_identifier(clause.column)
            op = clause.op
            value = clause.value
            if op in ("=", "!=", "<", "<=", ">", ">=", "like"):
                clauses.append(f"{column} {op} ?")
                params.append(value)
            elif op in ("in", "not in"):
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f"{column} {op.upper()} ({placeholders})")
                params.extend(value)
            else:  # is_null / not_null
                null_word = "NULL" if op == "is_null" else "NOT NULL"
                clauses.append(f"{column} IS {null_word}")
        return " AND ".join(clauses), params


# ── ヘルパー ──────────────────────────────────────────────────────────────


def quote_identifier(name: str) -> str:
    """SQLite の識別子を二重引用符で囲む。``"`` は ``""`` にエスケープする。

    SQLite の識別子のエスケープ規則に従う。仕様 §4。
    """
    return '"' + name.replace('"', '""') + '"'


def _value_for_sql(value: Any) -> Any:
    """INSERT / UPDATE の値を SQL 用に直す（``None`` → ``NULL``、日付は ISO 文字列）。

    仕様 §13。日付・日時（``datetime.date`` / ``datetime.datetime`` /
    pandas の ``Timestamp``）は ISO 形式の文字列で保存する。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # ``datetime`` は ``date`` の subclass でもあるので先に判定する。
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sqlite_column_type(python_type: type[Any] | None) -> str:
    """Python の型 → SQLite の SQL 型（``TEXT`` / ``INTEGER`` / ``REAL``）。"""
    if python_type is None:
        return ""
    sql_type = _PY_TYPE_TO_SQLITE_TYPE.get(python_type)
    if sql_type is None:
        return ""
    return f" {sql_type}"


def _connection_error(path: Path, detail: sqlite3.Error) -> SQLiteError:
    """接続に失敗したときの ``SQLiteError``。

    「database is locked」はファイルが他で使われているケース。
    仕様 §10 に基づき、ファイル名と「他の人が使っていないか確認」を出す。
    """
    message = str(detail).lower()
    if "locked" in message:
        return SQLiteError(
            f"SQLite ファイルがロックされています: {path}\n"
            "他の人が使っていないか確認してください。"
            f"（詳細: {detail}）"
        )
    return SQLiteError(
        f"SQLite ファイルを開けません: {path}\n"
        "ファイルの場所・読み取り権限・破損の有無を確認してください。"
        f"（詳細: {detail}）"
    )


def _wrap_sqlite_error(op: str, table: str, detail: sqlite3.Error) -> SQLiteError:
    """書き込み操作中の ``sqlite3`` エラーを ``SQLiteError`` に包む（仕様 §12）。"""
    message = str(detail).lower()
    if "locked" in message:
        return SQLiteError(
            f"SQLite ファイルがロックされているため{op}できません: {table}\n"
            "他の人が使っていないか確認してください。"
            f"（詳細: {detail}）"
        )
    return SQLiteError(f"SQLite の{op}に失敗しました: {table}\n（詳細: {detail}）")


def _table_not_found_error(name: str, existing: list[str]) -> SQLiteError:
    """表が見つからないときの ``SQLiteError``。"""
    return SQLiteError(f"表が見つかりません: {name} / 存在する表: {existing}")


def _column_not_found_error(table: str, column: str, existing: list[str]) -> SQLiteError:
    """列が見つからないときの ``SQLiteError``。"""
    return SQLiteError(f"列が見つかりません: {table}.{column} / 存在する列: {existing}")
