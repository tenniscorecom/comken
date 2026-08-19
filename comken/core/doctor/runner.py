"""comken/core/doctor/runner.py — 純粋な検査関数。

`comken/core/doctor/cli.py` から呼ばれる検査ロジックを置く。
**このモジュールは toolbox / services に依存しない**。
共有サーバーのパスや Salesforce 認証の有無など、上位の層が必要な
値は呼び出し側（cli.py）から引数として受け取る。
"""

from __future__ import annotations

import configparser
import logging
import sys
from pathlib import Path

import comken
from comken.core.result import DoctorResult

logger = logging.getLogger(__name__)

# comken パッケージのルート（リポジトリルート）を __file__ から逆算する。
# 検査対象の 3 ファイル（配置時に書き換える）への絶対パスに使う。
_COMKEN_ROOT = Path(comken.__file__).resolve().parent.parent

# 配置時に書き換える 3 ファイル。
_RPA_PATH = _COMKEN_ROOT / "comken" / "toolbox" / "rpa.py"
_SANDBOX_PATH = _COMKEN_ROOT / "comken" / "toolbox" / "salesforce" / "sites" / "sandbox.py"
_SERVICE_PATH = _COMKEN_ROOT / "comken" / "services" / "salesforce_downloader" / "service.py"

# 3 ファイルに残っている「仮名」の目印。配置が完了したら消える文字列。
_RPA_MARKER = "example_libs.v0000"
_SANDBOX_MARKER = "example--sandbox"
_SERVICE_MARKER = r"\\server\share"

# Python の最低バージョン。comken が要求する 3.11 に合わせておく。
MIN_PYTHON = (3, 11)

# config.ini を読む場所。`project_dir()` は main.py のフォルダを返すため、
# `python -m comken doctor` をそのフォルダで打つ運用と一致する。
_RUN_SECTION_NAME = "RUN"




# ── comken 自体の情報 ────────────────────────────────────────────────────────


def check_comken_version() -> DoctorResult:
    """comken 自体のバージョン。"""
    return DoctorResult("comken.version", "ok", f"v{comken.__version__}")


def check_python_version() -> DoctorResult:
    """実行中の Python のバージョンが要件を満たすか。

    `MIN_PYTHON` 未満なら NG。`sys.version_info` を直接見るので、
    `python` コマンドが指す Python をそのまま判定できる。
    """
    info = sys.version_info
    version_str = f"{info.major}.{info.minor}.{info.micro}"
    required = ".".join(str(part) for part in MIN_PYTHON)
    if (info.major, info.minor) >= MIN_PYTHON:
        return DoctorResult("python.version", "ok", f"{version_str} (>= {required})")
    return DoctorResult("python.version", "ng", f"{version_str} (< {required} が必須)")


def check_comken_path() -> DoctorResult:
    """今読んでいる comken の置き場所。PYTHONPATH の通し方が分かる。"""
    return DoctorResult("comken.path", "ok", str(Path(comken.__file__).resolve().parent))


# ── 依存モジュール ────────────────────────────────────────────────────────────


def check_dependency(name: str, module_name: str) -> DoctorResult:
    """依存モジュールが import できるか。"""
    result_name = f"deps.{name}"
    try:
        __import__(module_name)
    except ImportError:
        return DoctorResult(result_name, "ng", "not installed")
    except Exception as e:  # ImportError 以外のエラー（依存の初期化失敗など）も一応拾う
        return DoctorResult(result_name, "ng", f"import 失敗: {type(e).__name__}")
    return DoctorResult(result_name, "ok", "")


def check_pywin32() -> DoctorResult:
    """pywin32 は Windows 専用。Windows 以外では SKIP。"""
    if sys.platform != "win32":
        return DoctorResult("deps.pywin32", "skip", "Windows only")
    return check_dependency("pywin32", "win32crypt")


# ── 設定の正しさ ──────────────────────────────────────────────────────────────


def check_run_section() -> DoctorResult:
    """config.ini に廃止された ``[RUN]`` セクションが残っていないか。

    comken は ``[RUN]`` を config.ini に書く方式をやめ、環境変数 + setter
    （``comken.runtime``）に統一した。config.ini に残っているのは古い設定が
    そのまま使われている兆候で、書き換え漏れに気付ける。
    """
    # 検査対象はカレントディレクトリではなく main.py と同じ階層の config.ini。
    # `python -m comken doctor` をプロジェクトのルートで打つ運用に合わす。
    from comken.core.files.ops import project_dir

    path = project_dir() / "config.ini"
    if not path.is_file():
        return DoctorResult("config.run_section", "skip", "config.ini が見つかりません")
    cfg = configparser.ConfigParser()
    # utf-8-sig: メモ帳等で保存すると BOM 付き UTF-8 になるため（BOM なしも読める）
    cfg.read(path, encoding="utf-8-sig")
    sections = {s.strip() for s in cfg.sections()}
    if _RUN_SECTION_NAME in sections:
        return DoctorResult("config.run_section", "ng", "[RUN] section found")
    return DoctorResult("config.run_section", "ok", "無し")


def check_placeholder(path: Path, marker: str, name: str) -> DoctorResult:
    """ファイル内に「仮名」の目印が残っていないか。"""
    if not path.is_file():
        # 通常はあり得ない（comken のソースが読み込めない状態）。検査続行のため SKIP。
        return DoctorResult(name, "skip", f"{path.name} が見つかりません")
    text = path.read_text(encoding="utf-8")
    if marker in text:
        return DoctorResult(name, "ng", f'still has "{marker}"')
    return DoctorResult(name, "ok", "")


def check_rpa_placeholder() -> DoctorResult:
    """``comken/toolbox/rpa.py`` の import がまだ仮名のままか。"""
    return check_placeholder(_RPA_PATH, _RPA_MARKER, "config.placeholder.rpa")


def check_sandbox_placeholder() -> DoctorResult:
    """``comken/toolbox/salesforce/sites/sandbox.py`` の URL がまだ仮のままか。"""
    return check_placeholder(_SANDBOX_PATH, _SANDBOX_MARKER, "config.placeholder.sandbox")


def check_service_placeholder() -> DoctorResult:
    """``comken/services/salesforce_downloader/service.py`` のパスがまだ仮のままか。"""
    return check_placeholder(_SERVICE_PATH, _SERVICE_MARKER, "config.placeholder.service")


# ── 共有サーバー ──────────────────────────────────────────────────────────────


def check_share_path(name: str, path: Path) -> DoctorResult:
    """パスがファイルとして存在するか。フォルダしかない／無い場合は NG。

    `.is_file()` だけ見る。共有サーバーが落ちていれば False が返るだけで、
    ブロックはしない。値は出さない（パスの名前だけ表示）。
    """
    if path.is_file():
        return DoctorResult(name, "ok", str(path))
    return DoctorResult(name, "ng", "not accessible")


def check_master_path(master_path: Path) -> DoctorResult:
    """レポート管理表のパスが共有サーバーにあるか。

    パスは呼び出し側（cli.py）が ``_paths`` から解決して渡す。
    """
    return check_share_path("share.master_path", master_path)


def check_history_path(history_path: Path) -> DoctorResult:
    """ダウンロード履歴のパスが共有サーバーにあるか。"""
    return check_share_path("share.history_path", history_path)


# ── Salesforce ───────────────────────────────────────────────────────────────


def check_salesforce(
    names: list[str],
    sandbox_cls: type | None,
) -> DoctorResult:
    """Salesforce 接続を検査する（純粋関数）。

    資格情報のキー名一覧（``list_names()`` の結果）と Salesforce 組織クラスを
    受け取って検査する。**資格情報が無いとき sandbox_cls は ``None``** で
    渡される（BO 環境で ``requests`` を import しないため）。

    どのキーを DPAPI に登録すべきかは組織クラスの ``CREDENTIAL_PREFIX`` から
    組み立てる (Refresh Token Flow 前提):
    ``<prefix>_client_id`` / ``<prefix>_client_secret`` / ``<prefix>_refresh_token``
    の 3 個。各キーの登録状態を ``details`` に 1 行ずつ返すので、
    **どれが未登録でセットアップが途中か**を 1 回の doctor 実行で把握できる。

    Args:
        names: DPAPI に登録された認証情報のキー名一覧。空なら SKIP。
        sandbox_cls: 組織の Salesforce クラス（例: ``Sandbox``）。
            ``None`` のときは Salesforce モジュールが見つからないものとして SKIP。

    Returns:
        ``DoctorResult``。status は ok / ng / skip のいずれか。
        ``details`` に ``<prefix>_<key>: 登録済 / 未登録`` を 1 行ずつ。
    """
    # 認証情報が無いなら SKIP（Salesforce 接続には進まない）
    if not names:
        return DoctorResult(
            "salesforce.connectivity",
            "skip",
            "認証情報なし (DPAPI に登録が無い、または BO 環境)",
        )

    if sandbox_cls is None:
        return DoctorResult(
            "salesforce.connectivity",
            "skip",
            "Salesforce モジュールが見つかりません",
        )

    # Refresh Token Flow に必要な 3 つのキーを組み立てる
    prefix = sandbox_cls.CREDENTIAL_PREFIX
    required_keys = (
        f"{prefix}_client_id",
        f"{prefix}_client_secret",
        f"{prefix}_refresh_token",
    )
    name_set = set(names)
    key_status = {key: (key in name_set) for key in required_keys}
    details: list[str] = [
        f"{key}: {'登録済' if registered else '未登録'}"
        for key, registered in key_status.items()
    ]

    # 接続テストには client_id / client_secret が必須
    has_id_secret = key_status[f"{prefix}_client_id"] and key_status[f"{prefix}_client_secret"]
    if not has_id_secret:
        return DoctorResult(
            "salesforce.connectivity",
            "skip",
            f"{prefix} の client_id / client_secret が未登録",
            details=tuple(details),
        )

    # refresh_token が無いと Refresh Token Flow は走らない
    # (client_credentials 経由に切り替えていない限り) ので NG
    if not key_status[f"{prefix}_refresh_token"]:
        return DoctorResult(
            "salesforce.connectivity",
            "ng",
            f"{prefix}_refresh_token が未登録 (初回認可が必要です)",
            details=tuple(details),
        )

    # 認証情報があるので、実際に繋いで確かめる。
    try:
        with sandbox_cls() as sf:
            sf.request("GET", sf.data_path("/limits"), component="doctor")
    except Exception as e:
        # 接続失敗は NG。メッセージは1行目だけ（スタックトレースは出さない）
        msg = str(e).splitlines()[0] if str(e) else type(e).__name__
        return DoctorResult(
            "salesforce.connectivity",
            "ng",
            msg[:200],
            details=tuple(details),
        )

    return DoctorResult(
        "salesforce.connectivity",
        "ok",
        f"API v{sandbox_cls.API_VERSION}",
        details=tuple(details),
    )


