"""サンプル: State で前回の実行結果を次回へ持ち越す。"""

import logging
from pathlib import Path

from comken import dry_run
from comken.core import State
from comken.core.logger import local

HERE = Path(__file__).parent
STATE_PATH = HERE / "output" / "state.ini"
LAST_ORDER_KEY = "LAST_ORDER_ID"
FIRST_ORDER_ID = 1000

logger = logging.getLogger(__name__)


def main() -> None:
    state = State(STATE_PATH)
    previous_order_id = int(state.get(LAST_ORDER_KEY, FIRST_ORDER_ID))
    next_order_id = previous_order_id + 1
    logger.info("前回の最終注文番号: %d", previous_order_id)
    logger.info("今回処理する注文番号: %d", next_order_id)

    # 試運転で「処理済み」を書くと本番が飛ぶため、dry-run 中は状態を変更しない。
    with dry_run():
        state.set(LAST_ORDER_KEY, next_order_id + 100)
    logger.info("dry-run 後の値: %s（変更なし）", state.get(LAST_ORDER_KEY, "未保存"))

    state.set(LAST_ORDER_KEY, next_order_id)
    logger.info("次回用に保存: %s = %d", LAST_ORDER_KEY, next_order_id)


if __name__ == "__main__":
    logger = local()
    main()
