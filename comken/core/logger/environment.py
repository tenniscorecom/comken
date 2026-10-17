"""comken/core/logger/environment.py — 社内環境向けの root logger 構築。

アプリ全体のログを集めるため root logger を設定する。二重 handler は同じメッセージを
重複出力するため、設定済みなら上書きせず例外にする。保存先は端末名（小文字化して照合）を
``LOG_FOLDER_NAMES`` から引き、日付ごとのファイルとコンソールへ同じ形式で出力する。
``LOG_FOLDER_NAMES`` に登録がない端末や、値が空文字／パス区切りを含んでいて使えない
端末は ``LOG_ROOT/_etc/etc_{ホスト名}/`` へ分けて書く。未登録の端末が複数あっても
ログが混ざらないように、ホスト名のサブフォルダで区別する。
"""

import logging
import os
import socket
import sysconfig
from pathlib import Path

from comken.core.dates import today
from comken.core.logger.site import LoggerSite
from comken.exceptions import (
    LoggingAlreadyConfiguredError,
    LoggingConflictError,
    LogRootNotConfiguredError,
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

logger = logging.getLogger(__name__)

# comken のバージョンを INFO ログへ出す 1 プロセス 1 回だけのフラグ。
# モジュール側に持ち、 ``setup_logging()`` と ``setup_local_logging()`` の両方で
# 共有する。 出力先を用意する関数が出力先を確定した直後にだけ True にするので、
# 出力先が用意できずに終わったときは log が出ず、フラグも立たない。
_version_logged = False


class _ExternalDebugFilter(logging.Filter):
    """``with debug():`` で comken の handler が DEBUG まで通すようになった結果、
    pip で入れた外部ライブラリの DEBUG まで画面とログファイルへ流れるのを止める。

    Selenium の WebDriver 送受信コマンド本文には ``Page.input()`` などが渡した
    パスワードがそのまま含まれる。 35 章で ``selenium.webdriver.remote.remote_connection``
    ロガー単体を INFO に固定したが、urllib3・openpyxl・requests など他ライブラリには
    同じ手は取れない。 そこで comken の handler に共通するフィルタとして、
    「標準ライブラリか pip ライブラリの置き場所にあり、かつ comken 由来でない
    DEBUG」を一律に落とす方針にした。

    判定は ``record.pathname``（``logging.LogRecord`` が log 呼び出し時に収集する
    ソースファイルの絶対パス）と ``sysconfig.get_paths()`` の ``stdlib`` /
    ``platstdlib`` / ``purelib`` / ``platlib`` のパスの包含で行う。 "site-packages"
    のような文字列探しではなくパスの包含にしたのは、venv・system Python・ユーザー
    site など構成が違っても同じロジックで動くようにするため。 大文字小文字は
    ``os.path.normcase`` で Windows の扱いに合わせる。
    """

    # sysconfig.get_paths() を見るキー。 4 つの置き場所を 1 度だけ問い合わせて
    # 以降はローカル参照にする（フィルタは log 1 件ごとに走るため）。
    _PATH_KEYS = (
        "stdlib",
        "platstdlib",
        "purelib",
        "platlib",
    )

    def __init__(self) -> None:
        super().__init__()
        # 空文字列が返ることがまれにあり（壊れた venv 等）、空文字を root として
        # 持つと全 DEBUG が startswith("") で True になり全部落ちる事故になるため、
        # 真に非空の値だけを拾う。
        self._external_roots: tuple[str, ...] = tuple(
            os.path.normcase(p) for key in self._PATH_KEYS if (p := sysconfig.get_paths().get(key))
        )

    def filter(self, record: logging.LogRecord) -> bool:
        """外部ライブラリ由来の DEBUG を ``False`` で落として握り潰す。

        ``logging.Handler.handle()`` から record ごとに呼ばれ、 ``True`` を
        返すとその handler は ``emit(record)`` へ進む。
        """
        # INFO 以上は comken 内外問わず常に通す。 外部ライブラリの警告や
        # エラーを握り潰すと問題に気付けないため。
        if record.levelno >= logging.INFO:
            return True
        # DEBUG 以下: comken 自身の logger はそのまま通す（comken/core/logger/ 配下の
        # logger.debug もここで通る）。 comken が pip で site-packages に入っている
        # 場合も、名前で通す。
        if record.name == "comken" or record.name.startswith("comken."):
            return True
        # 利用側プロジェクトの main.py / src/*.py は purelib 外に置く想定なので、
        # ここで startswith に引っかからず True に落ちる。
        # resolve() は log 1 件ごとにファイルシステムを走るので、 normcase + abspath
        # だけの正規化に留める。 包含は「root と一致するか、 root + os.sep で
        # 始まるか」とし、 ``<root>`` の兄弟フォルダ（例: ``<stdlib>`` が
        # ``.../Lib`` のときの ``.../Lib2``）を誤って含めない。
        pathname = os.path.normcase(os.path.abspath(record.pathname))  # noqa: PTH100
        return all(
            pathname != root and not pathname.startswith(root + os.sep)
            for root in self._external_roots
        )


# モジュールに 1 つだけのインスタンス。 setup_logging() / setup_local_logging() が
# それぞれの handler へ ``addFilter`` する。 同じインスタンスなので setup_logging() が
# setup_local_logging() の console handler を使い回す場合に ``Handler.addFilter`` 側の
# 同一性チェック (``filter in self.filters``) で二重に付かない。
_external_debug_filter = _ExternalDebugFilter()


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
        console_handler.addFilter(_external_debug_filter)
        root_logger.addHandler(console_handler)
    environment_file_handler = logging.FileHandler(log_path, encoding="utf-8")
    environment_file_handler.set_name(ENVIRONMENT_HANDLER_NAME)
    environment_file_handler.setLevel(logging.INFO)
    environment_file_handler.setFormatter(formatter)
    environment_file_handler.addFilter(_external_debug_filter)
    root_logger.addHandler(environment_file_handler)

    root_logger.setLevel(_compute_root_level(root_logger.handlers))

    # 警告は comken の handler を root に追加し終えてから出す。先に出すと
    # 警告が comken のログファイルに残らず、何と共存したか追跡できなくなる。
    if external_allowed:
        _warn_external_handlers_allowed("setup_logging()", existing)
    # 出力先が用意できた直後（かつ例外で途中終了しなかったとき）にだけ記録する。
    # 出力先が無い段階で出すと、その行は捨てられてフラグだけ立ち、
    # あとでログを設定しても 1 行も出ない（cf. HISTORY.md 27 章）。
    _log_version_once()


def _compute_root_level(handlers: list[logging.Handler]) -> int:
    """comken 管理下の handler のうち最も低いレベルを返す。"""
    levels = [h.level for h in handlers if h.name in COMKEN_HANDLER_NAMES]
    return min(levels) if levels else logging.INFO


def _log_version_once() -> None:
    """comken のバージョンを INFO ログへ 1 回だけ記録する。

    ``setup_logging()`` / ``setup_local_logging()`` の両方で呼ばれても
    1 回しか出さない（プロセス内 1 回）。 モジュール ``comken`` の
    ``__version__`` は import 順で循環しないよう関数内で遅延 import する。
    config.ini を読む経路とは無関係に動くので、 config を使わない利用側
    （Salesforce レポートダウンローダー等）でもログが出せる。
    """
    global _version_logged
    if _version_logged:
        return
    from comken import __version__

    logger.info("comken v%s", __version__)
    _version_logged = True


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
    書く。``set_name()`` を呼ばないライブラリが多いため、``None`` がそのまま
    出ると読み手が戸惑う。表記は handler の種類によらず統一する。
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
