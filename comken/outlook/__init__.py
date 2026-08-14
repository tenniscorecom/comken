"""comken/outlook/__init__.py — Classic Outlook の受信メール読み取りと下書き作成。"""

from __future__ import annotations

from .handler import MailMessage, Outlook

__all__ = ["Outlook", "MailMessage"]
