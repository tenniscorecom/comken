"""comken/core/logging_run_id.py — 1回の実行処理を識別する run_id

ログを後から追うとき「どの実行のログか」を一発で識別できるように、
UUID ベースの run_id をコンテキスト変数へ保存する。
``setup_logging()`` が ``[RUN:xxxxx]`` プレフィックスをログに付けるので、
業務スクリプトの最初に ``new_run_id()`` を呼ぶだけで全ログに同じ ID が乗る。

    import logging

    from comken.core.logger import setup_logging
    from comken.core.logging_run_id import new_run_id

    setup_logging()
    run_id = new_run_id()                       # このプロセスの ID
    logging.getLogger(__name__).info("処理開始")
    # → [RUN:xxxxx] 2026-08-19 10:00:00 INFO ...: 処理開始

**「1回の業務実行を1つの run_id で追跡できる」ことを最優先の設計。**

並列実行モデルでの挙動 (``new_run_id()`` を呼ばないときのデフォルト):

- ``concurrent.futures.ThreadPoolExecutor``: 各ワーカースレッドは独立した
  ``ContextVar`` を持つため、明示的に ``new_run_id()`` を呼ばないと
  ``current_run_id()`` が ``"-"`` を返す。**各スレッドで別 ID を持たせたい
  場合はワーカー関数内で ``new_run_id()`` を呼ぶこと**
- ``concurrent.futures.ProcessPoolExecutor``: ワーカープロセスは
  完全に独立した Python インタプリタで動くため、**メイン側で呼んだ
  ``new_run_id()`` は子プロセスへ伝わらない**。各ワーカーで個別に
  ``new_run_id()`` を呼ぶこと
- ``asyncio``: ``asyncio.create_task()`` でタスク生成時に
  ``contextvars.copy_context()`` で親コンテキストが**コピー**される。
  タスク内で ``new_run_id()`` を呼ばないと**全部同じ run_id** になる。
  **タスクごとに別 ID を付けたい場合はタスク関数の冒頭で
  ``new_run_id()`` を呼ぶこと**

「並列処理を走らせれば自動で別 ID」ではないことに注意。自動独立を期待
したい場合は、各ワーカー / 各タスクの冒頭で ``new_run_id()`` を呼ぶこと。
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

__all__ = [
    "RunIdFilter",
    "current_run_id",
    "new_run_id",
]

# 1つの実行処理を識別するコンテキスト変数。
# プロセスの最初に ``new_run_id()`` で値を入れる。
# 未設定のときは ``None`` が入り、``current_run_id()`` が ``"-"`` に置換する。
_RUN_ID_VAR: ContextVar[str | None] = ContextVar("comken_run_id", default=None)

# ログに出力するときの run_id 省略値。grep で run_id 位置が揺れないよう固定長。
_RUN_ID_PLACEHOLDER = "-"
# UUID4 の先頭8文字 (16^8 ≈ 42 億通り) を run_id として使う。
# 12-3456-... のハイフン付き UUID より読みやすく、衝突確率も十分低い。
_RUN_ID_LENGTH = 8


def new_run_id() -> str:
    """UUID4 を生成し、コンテキスト変数へ保存して返す。

    プロセスの開始時に1回だけ呼ぶ想定。同じプロセス内で2回呼ぶと
    2回目以降が上書きされ、それ以降のログは新しい run_id で記録される。

    並列実行でタスクごとに別 ID を持ちたい場合は、各ワーカー関数 /
    各 asyncio タスク関数の冒頭で ``new_run_id()`` を呼ぶこと (詳細は
    モジュール docstring を参照)。
    """
    run_id = uuid.uuid4().hex[:_RUN_ID_LENGTH]
    _RUN_ID_VAR.set(run_id)
    return run_id


def current_run_id() -> str:
    """現在の run_id を返す。コンテキストに無ければ ``"-"`` を返す。"""
    return _RUN_ID_VAR.get() or _RUN_ID_PLACEHOLDER


class RunIdFilter(logging.Filter):
    """LogRecord に ``run_id`` 属性を注入するフィルター。

    ``setup_logging()`` がハンドラへ取り付ける。``extra={"run_id": ...}``
    を明示したログは、その値を尊重する (上書きしない)。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """LogRecord に run_id を入れて、そのまま通過させる。

        ``extra={"run_id": ...}`` を明示したログは、その値を尊重する (上書きしない)。
        """
        # extra で run_id が指定されていなければコンテキスト変数の値を入れる
        if not hasattr(record, "run_id"):
            record.run_id = current_run_id()
        return True
