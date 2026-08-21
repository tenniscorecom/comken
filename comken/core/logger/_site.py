"""ログ出力先となる社内環境の定義。"""

from pathlib import Path
from typing import ClassVar

from comken.exceptions import SiteOwnerRequiredError


class LoggerSite:
    """環境別ログ設定の基底クラス。"""

    NAME: ClassVar[str] = ""
    LOG_PATH: ClassVar[Path] = Path()
    USE_HOSTNAME: ClassVar[bool] = False
    CSV_FIELDS: ClassVar[tuple[str, ...]] = ()
    OWNER: ClassVar[str] = ""

    @classmethod
    def check_owner(cls) -> None:
        """OWNER が未設定ならログ構築前に停止する。"""
        if not cls.OWNER:
            raise SiteOwnerRequiredError(cls, "LoggerSite")


class Backoffice(LoggerSite):
    """バックオフィス環境のログ設定。"""

    NAME = "backoffice"
    LOG_PATH = Path()
    USE_HOSTNAME = True
    CSV_FIELDS = ()
    OWNER = "バックオフィス / 担当者"


class Intranet(LoggerSite):
    """イントラネット環境のログ設定。"""

    NAME = "intranet"
    LOG_PATH = Path()
    USE_HOSTNAME = True
    CSV_FIELDS = ()
    OWNER = "イントラネット / 担当者"
