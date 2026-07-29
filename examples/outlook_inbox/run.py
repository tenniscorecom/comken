"""Outlook 受信メール → CSV → 結果メール下書きのサンプル。

事前準備:
    Classic Outlook にサインインしておく。
実行:
    python -m examples.outlook_inbox.run
"""

import logging
from pathlib import Path

from comken.csv import CsvWriter
from comken.outlook import Outlook

logger = logging.getLogger(__name__)

OUTPUT_CSV = Path(__file__).parent / "output" / "outlook_messages.csv"
SUBJECT_CONTAINS = "日次データ"
DAYS = 7
DRAFT_TO = "taro@example.co.jp"


def main() -> None:
    """対象メールを CSV に記録し、処理結果を下書きに保存する。"""
    with Outlook() as mail:
        rows = [
            {
                "受信日時": message.received_at.isoformat(),
                "差出人": message.sender,
                "件名": message.subject,
                "本文": message.body,
            }
            for message in mail.messages(subject_contains=SUBJECT_CONTAINS, days=DAYS)
        ]
        CsvWriter(
            OUTPUT_CSV,
            fieldnames=["受信日時", "差出人", "件名", "本文"],
        ).write_rows(rows)
        mail.save_draft(
            to=DRAFT_TO,
            subject="受信メール処理結果",
            body=f"{len(rows)}件を CSV に書き出しました。添付をご確認ください。",
            attachments=[OUTPUT_CSV],
        )
    logger.info("Outlook の受信メールを %d 件処理しました", len(rows))


if __name__ == "__main__":
    main()
