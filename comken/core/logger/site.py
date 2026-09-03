"""comken/core/logger/site.py — ログ出力先となる社内環境の定義。

ログのルート（``LOG_ROOT``）と、その下に作る端末ごとのフォルダ名（``LOG_FOLDER_NAMES``）
を環境クラスに集約する。実行端末が ``LOG_FOLDER_NAMES`` に未登録でも停止せず、
``LOG_ROOT/_etc/etc_{ホスト名}/`` というホスト名別のサブフォルダへ分けて書かれる。
未登録の端末が複数あってもログが混ざらないようにし、設定漏れに気づきつつ
業務は止めないため。
"""

from typing import ClassVar

from comken.exceptions import SiteOwnerRequiredError


class LoggerSite:
    """環境別ログ設定の基底クラス。

    Attributes:
        NAME: ログファイル名に使う識別子（``"backoffice"`` / ``"intranet"`` など）。
        LOG_ROOT: ログを保存するルートの**絶対パスまたは UNC**。空文字だと
            ``setup_logging()`` がファイルを書き始める前に ``LogRootNotConfiguredError``
            で止まる。
        LOG_FOLDER_NAMES: ``{端末名: その下へ作るフォルダ名}`` の文字列辞書。key は
            ``socket.gethostname()`` の戻り値（小文字化して照合するので
            ``LOG_FOLDER_NAMES`` 側の登録値も大文字で書いてよい）。登録がない、
            もしくは値が空文字／パス区切りを含む場合は ``LOG_ROOT/_etc/etc_{ホスト名}/``
            へ書く（未登録の端末が複数あってもログが混ざらないように、ホスト名の
            サブフォルダで区別する）。
        OWNER: 継承元を示す識別子。comken 共通のクラスは ``"comken"``、
            現地の環境クラスは ``"プロジェクト名 / 担当者"`` のように書く。

    運用メモ:
        ``LOG_FOLDER_NAMES`` の value は**フォルダ名だけ**を書く（例 ``"bo-logs"``）。
        ``/`` や ``\\`` を含む値、絶対パス、UNC 文字列などが書かれた場合は
        **未登録として扱い** ``LOG_ROOT/_etc/etc_{ホスト名}/`` 配下に書かれる。
        これは ``Path(LOG_ROOT) / value`` の ``/`` 演算子が ``value`` が絶対パスの
        ときに ``LOG_ROOT`` を捨てて ``value`` 側へ書き込む**罠**を避けるためのガード。
        登録値は単純なフォルダ名に統一しておくと、ログサーバーを移行しても
        各端末の ``LOG_FOLDER_NAMES`` 行を 1 行ずつ書き換えずに済む。
    """

    NAME: ClassVar[str] = ""
    LOG_ROOT: ClassVar[str] = ""
    LOG_FOLDER_NAMES: ClassVar[dict[str, str]] = {}
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

    NAME = "backoffice"
    # 設置時に LOG_ROOT = "\\\\server\\share\\logs" と
    # LOG_FOLDER_NAMES = {"PC-001": "bo-logs", ...} を実値へ書き換える。
    LOG_ROOT = ""
    LOG_FOLDER_NAMES: ClassVar[dict[str, str]] = {}
    OWNER = "comken"


class Intranet(LoggerSite):
    """イントラネット環境のログ設定。

    comken 共通のクラス。OWNER は ``"comken"``。
    """

    NAME = "intranet"
    # 設置時に LOG_ROOT = "\\\\server\\share\\logs" と
    # LOG_FOLDER_NAMES = {"PC-001": "intra-logs", ...} を実値へ書き換える。
    LOG_ROOT = ""
    LOG_FOLDER_NAMES: ClassVar[dict[str, str]] = {}
    OWNER = "comken"
