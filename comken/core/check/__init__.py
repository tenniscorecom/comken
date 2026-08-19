"""comken/core/check/__init__.py — プロジェクト健全性検査 (純粋ロジック)

``python -m comken check [path]`` で「comken を更新したことで既存プロジェクトが
壊れていないか」を一括確認する。検査は独立して動き、1 個失敗しても残りは続ける。

検査項目:

| 検査名 | 内容 |
|---|---|
| ``version`` | config.ini に書いた期待バージョンと comken の現在バージョンが一致するか |
| ``imports`` | ``comken.__all__`` の各名前を ``from comken import X`` で読めるか |
| ``deprecations`` | ``deprecated_names()`` の旧名がプロジェクトで使われていないか |
| ``facade`` | ``comken.__all__`` の**名前**が期待どおりか (件数ではなく集合で比べる) |
| ``pyright`` | pyright が ``comken/`` に対して 0 errors を返すか |

各検査は独立した純粋関数が ``CheckResult`` を返す。CLI 入口は
``comken/core/check/cli.py`` に置く。
"""

from __future__ import annotations

import configparser
import logging
import re
import shutil
import subprocess
from pathlib import Path

import comken
from comken.core.result import CheckResult, summarize
from comken.deprecation import deprecated_names

logger = logging.getLogger(__name__)

__all__ = [
    "CheckResult",
    "check_deprecations",
    "check_facade",
    "check_imports",
    "check_pyright",
    "check_version",
    "summarize",
]

# comken のバージョンを書く config.ini のセクションとキー。
# 同じ config に書く設定値を分散させないため、専用のセクション名にする
_VERSION_SECTION = "COMKEN"
_VERSION_KEY = "VERSION"

# 公開 API ファサード (comken.__all__) に並ぶべき名前。
# **件数ではなく名前で比べる。** 件数だけ見ていると、1 つ消して 1 つ足したときに
# 数が変わらず素通りしてしまい、「公開 API が壊れていないか」を確かめられない。
# ``tests/test_facade.py`` の ``expected`` 集合と一致させる
_EXPECTED_FACADE_NAMES = frozenset(
    {
        "Config",
        "DoctorResult",
        "config",
        "debug",
        "doctor",
        "dry_run",
        "is_debug",
        "is_dry_run",
        "setup_logging",
    }
)

# pyright のタイムアウト。``tests/test_pyright_clean.py`` と同じ 600 秒。
PYRIGHT_TIMEOUT_SECONDS = 600

# deprecated スキャンで無視するディレクトリ名。venv やキャッシュは誤検知の元
_SKIP_DIR_NAMES = frozenset({"__pycache__", ".venv", "venv", "node_modules", ".git"})

# deprecation が空のとき表示する文言 (人間が一読して「意図通り」と分かる形)
_NO_DEPRECATIONS_REGISTERED = "deprecated API の登録なし"
_NO_DEPRECATIONS_USED = "使われている deprecated API: なし"




# ── version ───────────────────────────────────────────────────────────────────


def check_version(project_path: Path) -> CheckResult:
    """config.ini の ``[COMKEN] VERSION`` と現在の comken バージョンを比べる。"""
    config_path = project_path / "config.ini"
    if not config_path.is_file():
        return CheckResult(
            name="version",
            status="skip",
            message="config.ini が見つかりません",
        )
    cfg = configparser.ConfigParser()
    # configparser のデフォルトはキー名を小文字に潰すため、大文字キーを維持する
    cfg.optionxform = str  # type: ignore[method-assign]
    try:
        loaded = cfg.read(config_path, encoding="utf-8-sig")
    except configparser.Error as e:
        return CheckResult(name="version", status="ng", message=f"config.ini 解析失敗: {e}")
    if not loaded:
        return CheckResult(name="version", status="skip", message="config.ini が見つかりません")
    if not cfg.has_section(_VERSION_SECTION) or not cfg.has_option(_VERSION_SECTION, _VERSION_KEY):
        return CheckResult(
            name="version",
            status="skip",
            message=f"config.ini に [{_VERSION_SECTION}] {_VERSION_KEY} 指定なし",
        )
    expected = cfg.get(_VERSION_SECTION, _VERSION_KEY).strip()
    actual = comken.__version__
    if expected == actual:
        return CheckResult(
            name="version",
            status="ok",
            message=f"comken: v{actual} / 期待: v{expected}",
        )
    return CheckResult(
        name="version",
        status="ng",
        message=f"comken: v{actual} / 期待: v{expected} (不一致)",
    )


# ── imports ───────────────────────────────────────────────────────────────────


def check_imports() -> CheckResult:
    """``comken.__all__`` の各名前を ``from comken import X`` で読めるか。"""
    details: list[str] = []
    failed: list[str] = []
    for name in comken.__all__:
        try:
            __import__("comken", fromlist=[name])
            getattr(comken, name)
        except Exception as e:
            failed.append(name)
            details.append(f"from comken import {name}: NG ({type(e).__name__})")
        else:
            details.append(f"from comken import {name}: OK")
    if not failed:
        return CheckResult(
            name="imports",
            status="ok",
            message=f"{len(comken.__all__)} 個すべて成功",
            details=tuple(details),
        )
    return CheckResult(
        name="imports",
        status="ng",
        message=f"{len(failed)}/{len(comken.__all__)} 個失敗",
        details=tuple(details),
    )


# ── deprecations ──────────────────────────────────────────────────────────────


def check_deprecations(project_path: Path) -> CheckResult:
    """deprecated な API がプロジェクトのソースで使われていないか。"""
    names = deprecated_names()
    if not names:
        return CheckResult(
            name="deprecations",
            status="ok",
            message=_NO_DEPRECATIONS_REGISTERED,
        )
    used = _scan_deprecated_usage(project_path)
    if not used:
        return CheckResult(
            name="deprecations",
            status="ok",
            message=_NO_DEPRECATIONS_USED,
        )
    return CheckResult(
        name="deprecations",
        status="ng",
        message=f"{len(used)} 件の deprecated API が使われています",
        details=tuple(used),
    )


def _scan_deprecated_usage(project_path: Path) -> list[str]:
    """deprecated な旧名が import / 利用されているソースを再帰的に拾う。"""
    found: list[str] = []
    if not project_path.is_dir():
        return found
    seen: set[tuple[str, str]] = set()
    for py_file in project_path.rglob("*.py"):
        # 除外ディレクトリのパーツを含むものはスキップ (venv / pycache 等)
        if any(part in _SKIP_DIR_NAMES for part in py_file.parts):
            continue
        try:
            text = py_file.read_text(encoding="utf-8")
        except OSError:
            # バイナリ・読み込み失敗などは無視して走査を続ける
            continue
        for old_name in deprecated_names():
            if not _name_used_in_source(text, old_name):
                continue
            rel = py_file.relative_to(project_path).as_posix()
            key = (old_name, rel)
            if key in seen:
                continue
            seen.add(key)
            found.append(f"{old_name} ({rel})")
    return found


def _name_used_in_source(text: str, name: str) -> bool:
    """ソーステキストに ``name`` が identifier として現れるか。

    ``\b`` だけだと「他の識別子の一部」が拾える（``MyOldName`` で
    ``OldName`` がマッチする等）ので Python の identifier ルールで
    文字境界を判定する。
    """
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
    return pattern.search(text) is not None


# ── facade ────────────────────────────────────────────────────────────────────


def check_facade() -> CheckResult:
    """公開 API ファサード (comken.__all__) の名前が期待どおりか。

    件数ではなく**名前の集合**を比べる。件数だけだと、1 つ消して 1 つ足した
    ときに数が変わらず通ってしまい、公開 API の破壊を検出できない。
    """
    actual = frozenset(comken.__all__)
    if actual == _EXPECTED_FACADE_NAMES:
        return CheckResult(
            name="facade",
            status="ok",
            message=f"{len(actual)}個すべて期待どおり",
        )
    missing = sorted(_EXPECTED_FACADE_NAMES - actual)
    extra = sorted(actual - _EXPECTED_FACADE_NAMES)
    details: list[str] = []
    if missing:
        details.append(f"消えた名前: {'、'.join(missing)}")
    if extra:
        details.append(f"増えた名前: {'、'.join(extra)}")
    return CheckResult(
        name="facade",
        status="ng",
        message=f"{len(actual)}個 (期待: {len(_EXPECTED_FACADE_NAMES)}個)",
        details=tuple(details),
    )


# ── pyright ───────────────────────────────────────────────────────────────────


def check_pyright(repo_root: Path) -> CheckResult:
    """pyright が ``comken/`` に対して 0 errors を返すか。

    ``tests/test_pyright_clean.py`` と同じ判定ロジック。
    **``--yes pyright@latest`` は使わない** (BO / オフライン環境で npm
    から最新版を取りに行くため動かない)。代わりに以下の優先順で探す:

    1. PATH にある ``pyright`` コマンドを直接実行
    2. ``npx --no-install pyright`` でローカル npm の pyright を使う
    3. どちらも無ければ SKIP
    """
    # 1. PATH の pyright を直接実行
    pyright = shutil.which("pyright")
    if pyright is not None:
        proc = _run_pyright([pyright, "comken/"], repo_root)
        return _parse_pyright_result(proc)

    # 2. npx --no-install でローカル npm の pyright を使う
    npx = shutil.which("npx")
    if npx is not None:
        proc = _run_pyright([npx, "--no-install", "pyright", "comken/"], repo_root)
        return _parse_pyright_result(proc)

    # 3. どちらも無ければ SKIP
    return CheckResult(
        name="pyright",
        status="skip",
        message="pyright も npx も無いので pyright を実行できません",
    )


def _run_pyright(cmd: list[str], repo_root: Path) -> subprocess.CompletedProcess[str]:
    """pyright を subprocess で実行する。タイムアウト例外は呼び出し側で処理する。"""
    return subprocess.run(
        cmd,
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=PYRIGHT_TIMEOUT_SECONDS,
    )


def _parse_pyright_result(proc: subprocess.CompletedProcess[str]) -> CheckResult:
    """pyright の実行結果を CheckResult に変換する。"""
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"(\d+) errors?", output)
    if match is None:
        # "N errors" の表記が見つからないなら、終了コードで NG / OK を判断
        return CheckResult(
            name="pyright",
            status="ng" if proc.returncode != 0 else "ok",
            message=f"pyright 出力を解釈できません (rc={proc.returncode})",
        )
    count = int(match.group(1))
    if count == 0:
        return CheckResult(name="pyright", status="ok", message="0 errors")
    # エラー出力の最初の数行だけ詳細に載せる (ログに残るのは厳しすぎる)
    short = "\n".join(output.splitlines()[:5])
    return CheckResult(
        name="pyright",
        status="ng",
        message=f"{count} errors",
        details=(short,),
    )


