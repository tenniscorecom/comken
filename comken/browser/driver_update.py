"""msedgedriver.exe のバージョン合わせ。

Edge は自動更新で勝手に上がるが、msedgedriver.exe は上がらない。
そのままにしておくと、ある日突然すべての自動化が
「This version of Microsoft Edge WebDriver only supports ...」で止まる。

社内の配布フォルダ（BrowserOptions.DRIVER_SOURCE_DIR）に新しい msedgedriver.exe が
置かれている前提で、バージョン不一致を検出したら自動でコピーして上書きする。

呼び出し側（session.py）は「起動を試す → 失敗したら update_driver() → もう一度だけ起動」
という流れで使う。毎回バージョンを調べに行くと、共有フォルダへのアクセスで
起動が遅くなるため、失敗したときだけ確認する。
"""

import logging
import os
import re
import shutil
import subprocess
import winreg
from pathlib import Path

logger = logging.getLogger(__name__)

DRIVER_FILE_NAME = "msedgedriver.exe"

# --version の出力例: "Microsoft Edge WebDriver 131.0.2903.86 (a1b2c3...)"
_VERSION_PATTERN = re.compile(r"(\d+(?:\.\d+)+)")

# バージョン問い合わせが固まったときに起動処理ごと止まらないようにする
_VERSION_TIMEOUT_SECONDS = 10

# コンソールウィンドウを出さずに msedgedriver.exe --version を実行するためのフラグ
_CREATE_NO_WINDOW = 0x08000000

# インストール済み Edge のバージョンが載っているレジストリ。上から順に試す。
# BLBeacon はユーザー単位、EdgeUpdate は端末単位で、環境によってどちらかが欠けている
_EDGE_VERSION_KEYS = (
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Edge\BLBeacon", "version"),
    (
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
        r"\{56EB18F8-B008-4CBD-B6D2-8C97FE7E9062}",
        "pv",
    ),
)


def update_driver(driver_path: Path, source_dir: Path) -> bool:
    """配布フォルダの msedgedriver.exe を driver_path へコピーして上書きする。

    インストール済み Edge とメジャーバージョンが一致するものを配布フォルダから選ぶ。
    すでに一致していれば何もしない（同じファイルを毎回コピーしない）。

    Args:
        driver_path: 上書き先。selenium に渡している msedgedriver.exe のパス。
        source_dir: 社内の配布フォルダ。直下、またはバージョン別のサブフォルダに
                    msedgedriver.exe が置かれていることを想定する。

    Returns:
        コピーして更新した場合 True、更新が不要だった場合 False。
        呼び出し側は False のときに起動を再試行しても同じ結果になるため、
        再試行せず元の例外を投げ直すこと。

    Raises:
        FileNotFoundError: 配布フォルダが存在しない、または msedgedriver.exe が1つも無い場合。
        PermissionError: 上書き先が他のプロセスに使われていてコピーできない場合。
    """
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"ドライバーの配布フォルダが見つかりません: {source_dir}\n"
            "BrowserOptions.DRIVER_SOURCE_DIR のパスと、共有フォルダに接続できているかを"
            "確認してください。"
        )

    edge_version = _installed_edge_version()
    current_version = _driver_version(driver_path)
    if edge_version and current_version and _major(edge_version) == _major(current_version):
        logger.info(
            "msedgedriver は Edge %s と一致しています（更新不要）: %s",
            edge_version,
            current_version,
        )
        return False

    source = _pick_source(source_dir, edge_version)
    logger.info(
        "msedgedriver を更新します: %s → %s（Edge %s / 現在のドライバー %s）",
        source,
        driver_path,
        edge_version or "不明",
        current_version or "不明",
    )

    _replace_driver(source, driver_path)

    updated_version = _driver_version(driver_path)
    if edge_version and updated_version and _major(edge_version) != _major(updated_version):
        # 起動は再試行させる（動く可能性は残る）が、原因調査の手がかりを残す
        logger.warning(
            "配布フォルダの msedgedriver（%s）が Edge %s と一致していません。"
            "配布フォルダに新しいドライバーが置かれているか確認してください: %s",
            updated_version,
            edge_version,
            source,
        )
    else:
        logger.info("msedgedriver を更新しました: %s", updated_version or "バージョン不明")
    return True


def _replace_driver(source: Path, driver_path: Path) -> None:
    """配布フォルダの exe を driver_path へ置き換える。

    いったん同じフォルダの一時ファイルへコピーしてから置換する。
    共有フォルダからの直接コピーは途中で失敗すると壊れた exe が残り、
    別のプロセスが中途半端なファイルを掴むおそれがあるため。
    """
    driver_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = driver_path.with_name(f".{driver_path.name}.{os.getpid()}.tmp")
    try:
        # copy2 でタイムスタンプも引き継ぐ。次回の「どれが新しいか」判定を狂わせないため
        shutil.copy2(source, temporary)
        temporary.replace(driver_path)
    except PermissionError as exc:
        raise PermissionError(
            f"msedgedriver.exe を上書きできませんでした: {driver_path}\n"
            f"（{exc}）\n"
            "別の Python プロセスやブラウザがドライバーを掴んだままの可能性があります。\n"
            "実行中の自動化をすべて終了してから、もう一度実行してください。"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _pick_source(source_dir: Path, edge_version: str | None) -> Path:
    """配布フォルダからコピー元の msedgedriver.exe を選ぶ。

    配布フォルダの作りは職場ごとに違うため、次の順に探す:
      1. フォルダ直下の msedgedriver.exe（「最新をここに置く」運用）
      2. パスに Edge のメジャーバージョンを含むもの（バージョン別フォルダ運用）
      3. 更新日時が最も新しいもの（上のどちらでもない場合の保険）
    """
    direct = source_dir / DRIVER_FILE_NAME
    if direct.is_file():
        return direct

    candidates = sorted(source_dir.rglob(DRIVER_FILE_NAME))
    if not candidates:
        raise FileNotFoundError(
            f"配布フォルダに {DRIVER_FILE_NAME} が見つかりません: {source_dir}\n"
            f"フォルダ直下か、バージョン別のサブフォルダに {DRIVER_FILE_NAME} を置いてください。"
        )

    if edge_version:
        major = _major(edge_version)
        # 配布フォルダより下のフォルダ名だけを見る。source_dir 自身のパスに
        # たまたま数字が含まれている場合（\\サーバー\ツール131\ 等）に、
        # 配下の全候補が一致してしまうのを防ぐ
        matched = [p for p in candidates if _has_major_in_subpath(p, source_dir, major)]
        if matched:
            return max(matched, key=lambda p: p.stat().st_mtime)

    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    logger.warning(
        "Edge のバージョンに一致する %s が配布フォルダに見つからないため、"
        "更新日時が最新のものを使います: %s",
        DRIVER_FILE_NAME,
        newest,
    )
    return newest


def _has_major_in_subpath(candidate: Path, source_dir: Path, major: str) -> bool:
    """配布フォルダから下のフォルダ名に、メジャーバージョンが含まれるか。

    数字のかたまりとして一致することを求める（"131" が "1310" や "13" に誤爆しないよう、
    前後を数字以外で挟む）。
    """
    try:
        relative = candidate.relative_to(source_dir)
    except ValueError:
        # rglob の結果なので通常は起きないが、シンボリックリンク経由だとあり得る
        return False

    pattern = re.compile(rf"(?<!\d){re.escape(major)}(?!\d)")
    return any(pattern.search(part) for part in relative.parts)


def _installed_edge_version() -> str | None:
    """インストール済み Edge のバージョンを返す。分からない場合は None。

    バージョンが取れなくても更新自体は続行できる（配布フォルダの最新を使う）ため、
    例外にはせず None を返す。
    """
    for root, key_path, value_name in _EDGE_VERSION_KEYS:
        try:
            with winreg.OpenKey(root, key_path) as key:
                version, _ = winreg.QueryValueEx(key, value_name)
                if version:
                    return str(version)
        except OSError:
            continue

    logger.warning("インストール済み Edge のバージョンを取得できませんでした")
    return None


def _driver_version(driver_path: Path) -> str | None:
    """msedgedriver.exe のバージョンを返す。ファイルが無い・応答しない場合は None。"""
    if not driver_path.is_file():
        return None

    try:
        completed = subprocess.run(
            [str(driver_path), "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_TIMEOUT_SECONDS,
            check=False,
            creationflags=_CREATE_NO_WINDOW,
        )
    except OSError:
        logger.warning("msedgedriver のバージョンを取得できませんでした: %s", driver_path)
        return None
    except subprocess.TimeoutExpired:
        logger.warning("msedgedriver がバージョン問い合わせに応答しませんでした: %s", driver_path)
        return None

    matched = _VERSION_PATTERN.search(completed.stdout)
    return matched.group(1) if matched else None


def _major(version: str) -> str:
    """"131.0.2903.86" → "131"。ドライバーと Edge はメジャーが一致していれば動く。"""
    return version.split(".", 1)[0]
