"""comken/core/logger/site.py — 社内環境向けのログ設定。

ログのルート（``LOG_ROOT``）と、その下に作る端末ごとのフォルダ名（``LOG_FOLDER_NAMES``）
を環境クラスに集約する。実行端末が ``LOG_FOLDER_NAMES`` に未登録でも停止せず、
``LOG_ROOT/_etc/etc_{ホスト名}/`` というホスト名別のサブフォルダへ分けて書かれる。
未登録の端末が複数あってもログが混ざらないようにし、設定漏れに気づきつつ
業務は止めないため。

``setup_logging()`` はサイトクラスに従い root logger を設定する。
二重 handler は同じメッセージが重複出力するため、設定済みなら上書きせず
例外にする。保存先は端末名（小文字化して照合）を ``LOG_FOLDER_NAMES`` から引き、
日付ごとのファイルとコンソールへ同じ形式で出力する。``LOG_FOLDER_NAMES`` に
登録がない端末や、値が空文字／パス区切りを含んでいて使えない端末は
``LOG_ROOT/_etc/etc_{ホスト名}/`` へ分けて書く。未登録の端末が複数あっても
ログが混ざらないように、ホスト名のサブフォルダで区別する。
"""

import logging
import os
import socket
from pathlib import Path
from typing import ClassVar

from comken.core.dates import today
from comken.exceptions import (
    LoggingAlreadyConfiguredError,
    LoggingConflictError,
    LogRootNotConfiguredError,
    SiteOwnerRequiredError,
)

LOG_FORMAT = "%(asctime)s %(levelname)s [pid=%(pid)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_HANDLER_NAME = "comken.console"
ENVIRONMENT_HANDLER_NAME = "comken.environment"
LOCAL_HANDLER_NAME = "comken.local"
# 未登録・不正値の端末をまとめる1階層目の固定フォルダ名。
# 2階層目に ``etc_{hostname}`` を置いて、混ざらないように区別する。
ETC_FOLDER_NAME = "_etc"
# comken が root に付けた handler だけレベル集計の対象にする。
# 外部の NOTSET ハンドラーが混ざると root が NOTSET に巻き戻され、
# isEnabledFor() が DEBUG まで通す穴になるため (回帰テスト #10)。
COMKEN_HANDLER_NAMES = frozenset(
    {CONSOLE_HANDLER_NAME, ENVIRONMENT_HANDLER_NAME, LOCAL_HANDLER_NAME}
)


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


def setup_logging(site: type[LoggerSite], *, allow_existing: bool = False) -> None:
    """site の指定に従い root logger を設定する。

    PID は同じ端末で同時に動くプロセスを見分ける値であり、保存先を選ぶ端末名とは
    用途が異なる。Formatter の固定値として渡し、ログ呼び出し側へ負担を増やさない。

    ``setup_local_logging()`` が先に走っている場合（root に console と local
    ファイルだけがある場合）は console を再利用し、environment ファイルだけを
    追加する。逆順（``setup_logging()`` が先）では通常どおり console と
    environment ファイルを追加する。両方がすでに走っている場合は
    ``LoggingAlreadyConfiguredError`` を送出して、二重出力を防ぐ。

    comken 以外の handler が root に混ざっている場合は ``LoggingConflictError``
    を送出する。既存 handler の出力先やレベルを勝手に変えてしまうため。
    ``allow_existing=True`` を指定すると、その判定を**警告ログだけ**に留めて処理を
    続行する（comken の handler が両方走っているケースは許可しない — 何が3つ目に
    なるか曖昧になり、誤って出力に気付くのが遅れるため）。
    """
    root_logger = logging.getLogger()
    existing = root_logger.handlers[:]
    external_allowed = _guard_root_handlers(existing, side="setup", allow_existing=allow_existing)

    site.check_owner()
    # ファイルを作る前に止める。空のフォルダが現場へ残ると
    # 「設定忘れか、運用で消すのか」が判断できなくなるため。
    if not site.LOG_ROOT:
        raise LogRootNotConfiguredError(site)
    # 登録は大文字／小文字どちらでもよく、運用取得側も大小揺れるので
    # キー側も問い合わせ側も小文字化した上で照合する。
    hostname = socket.gethostname().lower()
    folder_name = next(
        (value for key, value in site.LOG_FOLDER_NAMES.items() if key.lower() == hostname),
        None,
    )
    # 未登録、または値にパス区切りが含まれている場合は _etc 扱い。
    # 後者は Path の `/` 演算子が絶対パス値を見ると LOG_ROOT を捨てて
    # 別の場所へ書き込む罠なので、未登録としてガードする。
    # 未登録のまま 1 つの固定フォルダにまとめてしまうと、複数台の未登録端末の
    # ログが区別できなくなるため、ホスト名ごとのサブフォルダへ分けて書く。
    if not folder_name or "/" in folder_name or "\\" in folder_name:
        log_dir = Path(site.LOG_ROOT) / ETC_FOLDER_NAME / f"etc_{hostname}"
    else:
        log_dir = Path(site.LOG_ROOT) / folder_name
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{site.NAME}-{today().isoformat()}.log"

    formatter = logging.Formatter(
        LOG_FORMAT,
        datefmt=DATE_FORMAT,
        defaults={"pid": os.getpid()},
    )

    if LOCAL_HANDLER_NAME in {h.name for h in existing}:
        # setup_local_logging() が既に console を備えている。console は使い回して
        # environment ファイルだけを追加する（重複出力を避ける）。console のレベルは
        # setup_local_logging() が決めた値をそのまま使う。
        console_handler = next(h for h in existing if h.name == CONSOLE_HANDLER_NAME)
    else:
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    environment_file_handler = logging.FileHandler(log_path, encoding="utf-8")
    environment_file_handler.set_name(ENVIRONMENT_HANDLER_NAME)
    environment_file_handler.setLevel(logging.INFO)
    environment_file_handler.setFormatter(formatter)
    root_logger.addHandler(environment_file_handler)

    root_logger.setLevel(_compute_root_level(root_logger.handlers))

    # 警告は comken の handler を root に追加し終えてから出す。先に出すと
    # 警告が comken のログファイルに残らず、何と共存したか追跡できなくなる。
    if external_allowed:
        _warn_external_handlers_allowed("setup_logging()", existing)


def _compute_root_level(handlers: list[logging.Handler]) -> int:
    """comken 管理下の handler のうち最も低いレベルを返す。"""
    levels = [h.level for h in handlers if h.name in COMKEN_HANDLER_NAMES]
    return min(levels) if levels else logging.INFO


def _classify_root_handlers(
    handlers: list[logging.Handler],
) -> tuple[bool, bool, bool, bool]:
    """root logger に付いている handler を分類する。

    判定は純粋関数に閉じ、呼び出し側が ``setup_logging()`` / ``setup_local_logging()``
    のどちらから呼ばれても同じ意味の結果を受け取る。raise まではこの関数では行わない。

    Returns:
        (has_environment, has_local, has_both, has_external):
            has_environment: comken の environment handler が root に付いている
            has_local: comken の local handler が root に付いている
            has_both: 両方付いている
            has_external: comken 以外（他ライブラリ由来）の handler が1つでも付いている
    """
    names = {h.name for h in handlers}
    has_environment = ENVIRONMENT_HANDLER_NAME in names
    has_local = LOCAL_HANDLER_NAME in names
    has_both = has_environment and has_local
    has_external = any(name not in COMKEN_HANDLER_NAMES for name in names)
    return has_environment, has_local, has_both, has_external


def _guard_root_handlers(
    handlers: list[logging.Handler],
    side: str,
    allow_existing: bool,
) -> bool:
    """``setup_logging()`` / ``setup_local_logging()`` の入口で root logger の
    状態を検査し、進めるか判定する。

    二重出力や既存 handler の破壊を防ぐための分岐と raise を1か所にまとめる。
    呼び出し側は「自分がどちら側か（``side="setup"`` か ``"local"``）」と
    「外部 handler を許すか（``allow_existing``）」だけを渡す。
    警告ログへ渡す ``"setup_logging()"`` / ``"setup_local_logging()"`` の表示名は
    ``side`` から導出し、呼び出し側で二重に書かない。各分岐の理由（なぜ止めるか）は
    元々の ``setup_logging()`` / ``setup_local_logging()`` 内のコメントを引き継ぎ、
    情報を落とさない。

    ``side`` は ``"setup"`` か ``"local"`` を想定する（呼び出し側で警告を出す
    際の関数名 ``f"{side}()"`` を組み立てる）。

    Returns:
        外部 handler を ``allow_existing=True`` で通した場合に ``True``。
        呼び出し側は comken の handler を root に追加し終えた**後**に
        ``_warn_external_handlers_allowed()`` を呼び、警告が comken の
        ログファイルへ確実に残る順序にする。判定と分岐はこの関数内に
        閉じ、呼び出し側へ散らさない。
    """
    has_environment, has_local, has_both, has_external = _classify_root_handlers(handlers)

    if has_both:
        # setup_logging() と setup_local_logging() が両方走った後に再度走ると、ログが
        # 画面と各ファイルに二重に出たり、出力先がどちらのルールに従うのか曖昧になる。
        raise LoggingAlreadyConfiguredError()
    if side == "setup" and has_environment and not has_local:
        # setup_logging() 直後の状態。2 回目の setup_logging() は3 つ目を足す操作なので止める。
        raise LoggingAlreadyConfiguredError()
    if side == "local" and has_local and not has_environment:
        # 既に setup_local_logging() が走った後に再度 setup_local_logging() を呼んでいる。
        # 上書きすると既存 handler の出力先やレベルを変えてしまうので止める。
        raise LoggingAlreadyConfiguredError()
    if has_external and not allow_existing:
        # comken 以外（他ライブラリ由来）の handler が混ざっている。
        # 既存 handler の出力先やレベルを勝手に変えてしまうため。
        raise LoggingConflictError(_format_external_handlers(handlers))
    return has_external and allow_existing


def _format_external_handlers(handlers: list[logging.Handler]) -> list[str]:
    """外部 handler の正体を、運用担当者に渡せる1行ずつに整形する。

    例外メッセージにそのまま埋め込む文字列で、クラス名・名前・レベルをまとめて
    1行にする。``logging.FileHandler`` だけは ``baseFilename`` から出力先パスも
    取り出す（出力先がはっきりしないものは分からない旨を明記）。

    ``handler.name`` が空 (``None`` または空文字) のときは ``name=(未設定)`` と
    書く。``set_name()`` を呼ばないライブラリが多いため、``None`` がそのまま出ると
    読み手が戸惑う。表記は handler の種類によらず統一する。
    """
    lines: list[str] = []
    for handler in handlers:
        if handler.name in COMKEN_HANDLER_NAMES:
            continue
        class_name = type(handler).__name__
        level_name = logging.getLevelName(handler.level)
        # 名前の表記は handler の種類によらず1つに揃える。set_name() を呼ばない
        # ライブラリが多く、その場合に None がそのまま出ると読み手が戸惑うため。
        name_text = repr(handler.name) if handler.name else "(未設定)"
        description = f"class={class_name}, name={name_text}, level={level_name}"
        if isinstance(handler, logging.FileHandler):
            # 出力先が分かると、どのライブラリが設定したかを追える。
            description += f", path={handler.baseFilename}"
        lines.append(description)
    return lines


def _warn_external_handlers_allowed(func_name: str, handlers: list[logging.Handler]) -> None:
    """``allow_existing=True`` で外部 handler を残したまま処理を進めた事実を警告ログに残す。"""
    external_descriptions = _format_external_handlers(handlers)
    logging.getLogger().warning(
        "root logger に comken 以外の handler が%d個残ったまま %s を実行します"
        "（allow_existing=True）。混在している handler: %s",
        len(external_descriptions),
        func_name,
        "; ".join(external_descriptions) if external_descriptions else "(なし)",
    )
