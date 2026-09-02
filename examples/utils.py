"""サンプル: 差分・再試行・待機・文字列正規化・現在時刻。"""

import logging

from comken.core import (
    DiffResult,
    RowChange,
    diff_rows,
    normalize,
    now,
    remove_spaces,
    retry,
    strip_spaces,
    wait_until,
)
from comken.core.logger import setup_local_logging

RETRY_COUNT = 2

logger = logging.getLogger(__name__)


def main() -> None:
    before = [
        {"社員番号": "001", "氏名": "山田", "所属": "営業"},
        {"社員番号": "002", "氏名": "佐藤", "所属": "総務"},
    ]
    after = [
        {"社員番号": "001", "氏名": "山田", "所属": "企画"},
        {"社員番号": "003", "氏名": "鈴木", "所属": "営業"},
    ]
    result: DiffResult = diff_rows(before, after, key="社員番号")
    change: RowChange = result.changed[0]
    logger.info("DiffResult: 追加=%s 削除=%s", result.added, result.removed)
    logger.info("RowChange: key=%s columns=%s", change.key, change.columns)

    attempts = 0

    @retry(times=RETRY_COUNT, wait=0, on=(RuntimeError,))
    def unstable_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < RETRY_COUNT:
            raise RuntimeError("一時的な失敗")
        return "成功"

    logger.info("retry: %s（%d 回目）", unstable_operation(), attempts)
    logger.info("wait_until: %s", wait_until(lambda: True, timeout=0))
    logger.info(
        "正規化: %s / 前後空白: %s / 全空白: %s",
        normalize("ＡＢＣ１２３"),
        strip_spaces("　山田　"),
        remove_spaces("03 1234　5678"),
    )
    logger.info("clock.now(): %s", now().isoformat())


if __name__ == "__main__":
    logger = setup_local_logging()
    main()
