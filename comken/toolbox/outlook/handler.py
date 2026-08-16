"""comken/toolbox/outlook/handler.py — Classic Outlook の受信メール読み取りと下書き作成。

New Outlook は COM サーバーを持たないため非対応。認証とネットワークが必要な
Graph API や、pst ファイルの直接読み取りによる代替も提供しない。
"""

# 定義中の Outlook を戻り値の型注釈に使うため、注釈の評価を遅延する。
from __future__ import annotations

import datetime
import logging
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import win32com.client

from ...core.clock import now
from ...exceptions import (
    ClassicOutlookNotAvailableError,
    OutlookAttachmentNotFoundError,
    OutlookFolderNotFoundError,
)
from ...runtime import dry_run_log, is_dry_run

logger = logging.getLogger(__name__)

OUTLOOK_INBOX = 6
OUTLOOK_MAIL_ITEM = 0
RECEIVED_TIME_FORMAT = "%m/%d/%Y %I:%M %p"


@dataclass(frozen=True)
class MailMessage:
    """受信メールから読み取った、変更されない値のセット。"""

    subject: str
    sender: str
    sender_address: str
    received_at: datetime.datetime
    body: str
    has_attachments: bool


class Outlook:
    """Classic Outlook を COM で操作する。

    New Outlook は COM を持たないため利用できない。``read_messages()`` はメールの値を
    読むだけで、既読・未読の状態を変更しない。送信機能は提供せず、確認可能な下書き
    の作成だけを行う。
    """

    def __init__(self) -> None:
        try:
            # NOTE: Outlook はシングルインスタンスで、利用者が開いているものを操作する。
            # Excel / Access と違い DispatchEx で別プロセスを作らない。
            self._application = win32com.client.Dispatch("Outlook.Application")
        except Exception as error:
            raise ClassicOutlookNotAvailableError() from error
        self._namespace = self._application.GetNamespace("MAPI")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        # NOTE: Excel / Access と違い Quit() は利用者の Outlook まで閉じるため呼ばない。
        self._namespace = None
        self._application = None

    def read_messages(
        self,
        subject_contains: str = "",
        days: int = 7,
        folder: str = "",
    ) -> Iterator[MailMessage]:
        """受信メールを新しい順に逐次返す。既読・未読の状態は変更しない。"""
        if days < 0:
            raise ValueError("days は0以上で指定してください。")

        selected_folder = self._select_folder(folder)
        items = selected_folder.Items
        since = now() - datetime.timedelta(days=days)
        conditions = [f"[ReceivedTime] >= '{since.strftime(RECEIVED_TIME_FORMAT)}'"]
        if subject_contains:
            escaped_subject = subject_contains.replace("'", "''")
            conditions.append(f"[Subject] LIKE '%{escaped_subject}%'")

        # Outlook 側で先に絞り込み、数万件の受信箱を Python で全件走査しない。
        restricted_items = items.Restrict(" AND ".join(conditions))
        restricted_items.Sort("[ReceivedTime]", True)
        for item in restricted_items:
            yield self._to_message(item)

    def save_draft(
        self,
        to: str | Sequence[str],
        subject: str,
        body: str,
        attachments: Sequence[str | Path] | None = None,
        cc: str | Sequence[str] = "",
    ) -> None:
        """メールを送信せず、利用者が確認する下書きとして保存する。"""
        attachment_paths = [Path(path).resolve() for path in attachments or ()]
        for path in attachment_paths:
            if not path.is_file():
                raise OutlookAttachmentNotFoundError(path)

        recipients = _join_recipients(to)
        carbon_copy = _join_recipients(cc)
        if is_dry_run():
            dry_run_log(
                "Outlook 下書き作成: 宛先=%s, CC=%s, 件名=%s, 添付=%s",
                recipients,
                carbon_copy,
                subject,
                ", ".join(str(path) for path in attachment_paths) or "なし",
            )
            return

        draft = self._application.CreateItem(OUTLOOK_MAIL_ITEM)
        draft.To = recipients
        draft.CC = carbon_copy
        draft.Subject = subject
        draft.Body = body
        for path in attachment_paths:
            draft.Attachments.Add(str(path))
        draft.Save()
        logger.info("Outlook の下書きフォルダに保存しました: %s", subject)

    def _select_folder(self, folder: str):
        inbox = self._namespace.GetDefaultFolder(OUTLOOK_INBOX)
        if not folder:
            return inbox

        folders = inbox.Folders
        names = [folders.Item(index).Name for index in range(1, folders.Count + 1)]
        for name in names:
            if name == folder:
                return folders.Item(name)
        raise OutlookFolderNotFoundError(folder, names)

    def _to_message(self, item) -> MailMessage:
        received_at = item.ReceivedTime
        if received_at.tzinfo is None:
            received_at = received_at.replace(tzinfo=now().tzinfo)
        # Body は Outlook が HTML メールから生成するプレーンテキスト本文も返す。
        return MailMessage(
            subject=str(item.Subject or ""),
            sender=str(item.SenderName or ""),
            sender_address=_sender_address(item),
            received_at=received_at,
            body=str(item.Body or ""),
            has_attachments=item.Attachments.Count > 0,
        )


def _join_recipients(recipients: str | Sequence[str]) -> str:
    if isinstance(recipients, str):
        return recipients
    return "; ".join(recipients)


def _sender_address(item) -> str:
    if getattr(item, "SenderEmailType", "") == "EX":
        exchange_user = item.Sender.GetExchangeUser()
        if exchange_user is not None and exchange_user.PrimarySmtpAddress:
            return str(exchange_user.PrimarySmtpAddress)
    return str(item.SenderEmailAddress or "")
