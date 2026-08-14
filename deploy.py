"""comken を BO 用の共有フォルダへ配置する。

git を使えない環境へ渡すため、`comken/` パッケージだけをコピーする。
配置先を各プロジェクトが常に import しているので、コピー途中の中身を読まれないよう、
同じフォルダの中で作り終えてから名前を差し替える。

バージョンは上げない。リリース手順（仕様書8章）で先に上げてからここへ来る。
同じバージョンを二度配ろうとした場合は、上げ忘れとみなして止める。

使い方:
    python deploy.py "\\\\server\\share\\BO_LIBS"

`deploy_comken.bat` をダブルクリックしても同じことができる。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import comken
from comken.toolbox.utils import now

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT / "comken"
RECORD_NAME = "DEPLOYMENT.txt"
STAGING_NAME = ".comken-staging"

# コピーしないもの（開発ツールが作るキャッシュ）
IGNORED = shutil.ignore_patterns("__pycache__", "*.pyc")


class DeployError(Exception):
    """配置を中止する。メッセージはそのまま利用者へ見せる。"""


def _check_target(target: Path) -> None:
    """配置先として使ってよい場所か確かめる。"""
    if target == ROOT or ROOT in target.parents:
        raise DeployError(
            f"開発リポジトリの中には配置できません: {target}\n"
            "共有フォルダなど、別の場所を指定してください。"
        )
    if target == Path(target.anchor):
        raise DeployError(
            f"ドライブや共有の直下には配置できません: {target}\n"
            "comken 専用のフォルダを作って指定してください。"
        )


def _deployed_version(target: Path) -> str | None:
    """配置先に今入っているバージョン。まだ何も無ければ None。"""
    record = target / RECORD_NAME
    if not record.is_file():
        return None
    for line in record.read_text(encoding="utf-8").splitlines():
        if line.startswith("version="):
            return line.removeprefix("version=").strip()
    return None


def _run(command: list[str], failure: str) -> None:
    """コマンドを実行し、失敗したら配置を中止する。"""
    if subprocess.run(command, cwd=ROOT, check=False).returncode != 0:
        raise DeployError(failure)


def _git_commit() -> str:
    """今のコミット。git が無い環境でも配置は続ける。"""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _verify_import(staging_root: Path, version: str) -> None:
    """差し替える前に、コピーした側が本当に import できるか確かめる。"""
    result = subprocess.run(
        [sys.executable, "-c", f"import comken; assert comken.__version__ == '{version}'"],
        cwd=staging_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DeployError(
            f"コピーした comken を読み込めませんでした。配置を中止します。\n{result.stderr}"
        )


def deploy(target: Path, *, skip_checks: bool = False) -> Path:
    """comken を配置先へ入れ替える。戻り値は配置した comken フォルダ。"""
    target = target.expanduser().resolve()
    version = comken.__version__
    _check_target(target)

    if _deployed_version(target) == version:
        raise DeployError(
            f"配置先には既に v{version} が入っています。\n"
            "先に comken/__init__.py の __version__ を上げてから配置してください。"
        )

    if not skip_checks:
        _run(
            [sys.executable, "-m", "ruff", "check", "."],
            "Ruff で問題が見つかりました。配置を中止します。",
        )
        _run([sys.executable, "-m", "pytest", "-q"], "テストが通りませんでした。配置を中止します。")

    target.mkdir(parents=True, exist_ok=True)
    staging_root = target / STAGING_NAME
    staged = staging_root / "comken"
    current = target / "comken"
    backup = target / "backup" / f"comken-{now():%Y%m%d-%H%M%S}"

    shutil.rmtree(staging_root, ignore_errors=True)
    try:
        shutil.copytree(PACKAGE, staged, ignore=IGNORED)
        _verify_import(staging_root, version)

        # 差し替えは「退避 → 移動」の2手。同じフォルダの中なので一瞬で終わり、
        # 中途半端な comken を他の PC に読ませる時間を最小にする。
        if current.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            current.rename(backup)
        try:
            staged.rename(current)
        except OSError:
            if not current.exists() and backup.exists():
                backup.rename(current)  # 退避した版へ戻す
            raise
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    (target / RECORD_NAME).write_text(
        f"version={version}\n"
        f"deployed_at={now():%Y-%m-%d %H:%M:%S}\n"
        f"git_commit={_git_commit()}\n"
        f"source={ROOT}\n",
        encoding="utf-8",
    )
    return current


def main() -> None:
    parser = argparse.ArgumentParser(description="comken を共有フォルダへ配置する")
    parser.add_argument("target", type=Path, help="配置先のフォルダ")
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Ruff と pytest を省く（急ぎで戻すときだけ）",
    )
    args = parser.parse_args()

    try:
        deployed = deploy(args.target, skip_checks=args.skip_checks)
    except (DeployError, OSError) as e:
        print(f"[!] {e}")  # noqa: T201
        raise SystemExit(1) from None

    print(f"配置しました: {deployed}（v{comken.__version__}）")  # noqa: T201


if __name__ == "__main__":
    main()
