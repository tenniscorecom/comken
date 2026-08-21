"""comken/core/logger/site.py — ログ出力先となる社内環境の定義。

端末ごとにログサーバーや共有フォルダが異なる運用を、環境クラスの ``LOG_FOLDERS`` に
集約する。実行端末が未登録なら誤った場所へ保存せず、設定不足として停止する。
"""

from typing import ClassVar

from comken.exceptions import SiteOwnerRequiredError


class LoggerSite:
    """環境別ログ設定の基底クラス。

    ``LOG_FOLDERS`` は ``端末名: 保存先フォルダ`` の文字列辞書。key には
    ``socket.gethostname()`` の戻り値、value には絶対パスや UNC パスを文字列で指定する。
    設定値を単純な文字列に揃え、利用者が ``Path`` を意識せず編集できるようにする。
    """

    NAME: ClassVar[str] = ""
    LOG_FOLDERS: ClassVar[dict[str, str]] = {}
    OWNER: ClassVar[str] = ""

    @classmethod
    def check_owner(cls) -> None:
        """OWNER が未設定ならログ構築前に停止する。"""
        if not cls.OWNER:
            raise SiteOwnerRequiredError(cls, "LoggerSite")


class Backoffice(LoggerSite):
    """バックオフィス環境のログ設定。"""

    NAME = "backoffice"
    # 管理者が実際の端末名と、その端末から使える保存先フォルダを登録する。
    LOG_FOLDERS: ClassVar[dict[str, str]] = {}
    OWNER = "バックオフィス / 担当者"


class Intranet(LoggerSite):
    """イントラネット環境のログ設定。"""

    NAME = "intranet"
    # 管理者が実際の端末名と、その端末から使える保存先フォルダを登録する。
    LOG_FOLDERS: ClassVar[dict[str, str]] = {}
    OWNER = "イントラネット / 担当者"
