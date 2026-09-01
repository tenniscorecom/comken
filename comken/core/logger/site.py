"""comken/core/logger/site.py — ログ出力先となる社内環境の定義。

ログのルート（``LOG_ROOT``）を環境クラスに集約し、保存先フォルダ名は実行端末の
ホスト名（小文字）から ``setup_logging()`` が自動で作る。旧設計の ``LOG_FOLDER_NAMES``
のような端末別の登録辞書は廃止し、二重管理を避ける。
"""

from typing import ClassVar

from comken.exceptions import SiteOwnerRequiredError


class LoggerSite:
    """環境別ログ設定の基底クラス。

    Attributes:
        LOG_ROOT: ログを保存するルートの**絶対パスまたは UNC**。空文字だと
            ``setup_logging()`` がファイルを書き始める前に ``LogRootNotConfiguredError``
            で止まる。
        OWNER: 継承元を示す識別子。comken 共通のクラスは ``"comken"``、
            現地の環境クラスは ``"プロジェクト名 / 担当者"`` のように書く。

    運用メモ:
        ログは ``LOG_ROOT/{hostname(小文字)}/python/{日付}/{ファイル名}`` に書かれる。
        フォルダ名は端末ごとに登録する必要がなく、ホスト名から自動で作られる
        （Windows の大小揺らぎに合わせて小文字化）。
        ログサーバーの移行は ``LOG_ROOT`` の1行書き換えだけで済む。
    """

    LOG_ROOT: ClassVar[str] = ""
    OWNER: ClassVar[str] = ""

    @classmethod
    def check_owner(cls) -> None:
        """OWNER が未設定ならログ構築前に停止する。"""
        if not cls.OWNER:
            raise SiteOwnerRequiredError(cls, "LoggerSite")


class Backoffice(LoggerSite):
    """バックオフィス環境のログ設定。

    comken 共通のクラス。OWNER は ``"comken"``。
    """

    # 設置時に LOG_ROOT = "\\\\server\\share\\logs" を実値へ書き換える。
    LOG_ROOT = ""
    OWNER = "comken"


class Intranet(LoggerSite):
    """イントラネット環境のログ設定。

    comken 共通のクラス。OWNER は ``"comken"``。
    """

    # 設置時に LOG_ROOT = "\\\\server\\share\\logs" を実値へ書き換える。
    LOG_ROOT = ""
    OWNER = "comken"
