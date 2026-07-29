"""
rename_package.py — パッケージ名の一括変更ツール（管理者用）

ライブラリのパッケージ名（現在: comken）を新しい名前に一括変更する。
フォルダ名・import 文・ドキュメント・bat・pyproject.toml・環境変数名
（COMKEN_SHARE 等の大文字表記）をまとめて置換する。

使い方:
    # まず変更内容の確認（何も書き換えない）
    python rename_package.py 新しい名前 --dry-run

    # 実行（このリポジトリ全体を書き換え、パッケージフォルダをリネーム）
    python rename_package.py 新しい名前

    # プロジェクト側の import も置換したい場合はフォルダを追加で渡す
    python rename_package.py 新しい名前 C:\\dev\\my_project

実行後にやること:
    1. pip install -e . をやり直す（パッケージ名が変わるため）
    2. git で変更を確認してコミット

補足:
    - 現在の名前は pyproject.toml から自動で読むため、二度目以降の改名にも使える
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# 置換対象のテキストファイル
TEXT_SUFFIXES = {".py", ".pyi", ".md", ".toml", ".bat", ".ini", ".cfg", ".txt", ".example"}
# 除外フォルダ
EXCLUDE_DIRS = {".git", "__pycache__", ".venv", "node_modules", "logs"}


def current_package_name(root: Path = ROOT) -> str:
    """pyproject.toml から現在のパッケージ名を読む。"""
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^name\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise SystemExit("pyproject.toml から name を読み取れませんでした。")
    return match.group(1)


def _read_text(path: Path) -> tuple[str, str] | None:
    """テキストとエンコーディングを返す。バイナリ等で読めなければ None。

    bat ファイルは cp932 のため、UTF-8 → cp932 の順に試す
    （書き戻しも同じエンコーディングで行い、ファイルを壊さない）。
    """
    for encoding in ("utf-8", "cp932"):
        try:
            return path.read_text(encoding=encoding), encoding
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def replace_in_file(path: Path, old: str, new: str, dry_run: bool) -> bool:
    """1ファイル内の旧名を置換する。変更があれば True を返す。"""
    loaded = _read_text(path)
    if loaded is None:
        return False
    text, encoding = loaded

    replaced = text.replace(old, new).replace(old.upper(), new.upper())
    if replaced == text:
        return False
    if not dry_run:
        path.write_text(replaced, encoding=encoding)
    return True


def rename_package(
    new_name: str, extra_folders: list[Path], dry_run: bool, root: Path = ROOT
) -> None:
    old_name = current_package_name(root)

    if not re.fullmatch(r"[a-z][a-z0-9_]*", new_name):
        raise SystemExit(
            f"パッケージ名として無効です: {new_name}\n"
            "小文字英字で始まり、小文字英数字とアンダースコアのみ使えます。"
        )
    if new_name == old_name:
        raise SystemExit(f"現在の名前と同じです: {old_name}")

    mode = "【確認モード（書き換えなし）】" if dry_run else ""
    print(f"{mode}{old_name} → {new_name} に一括変更します。")
    print()

    # ── テキストファイルの置換 ──
    changed = []
    for folder in [root, *extra_folders]:
        for path in sorted(folder.rglob("*")):
            if any(part in EXCLUDE_DIRS or part.endswith(".egg-info") for part in path.parts):
                continue
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            if replace_in_file(path, old_name, new_name, dry_run):
                changed.append(path)
    for path in changed:
        print(f"  置換: {path}")

    # ── パッケージフォルダのリネーム ──
    package_dir = root / old_name
    if package_dir.is_dir():
        print(f"  フォルダ: {package_dir} → {root / new_name}")
        if not dry_run:
            package_dir.rename(root / new_name)

    print()
    print(f"完了（{len(changed)} ファイルを置換）。")
    if dry_run:
        print("実行するには --dry-run を外してもう一度実行してください。")
    else:
        print("次にやること:")
        print("  1. pip install -e . をやり直す（パッケージ名が変わったため）")
        print("  2. git diff で変更を確認してコミット")
        print("  3. 各プロジェクトの import 置換がまだなら、プロジェクトフォルダを")
        print(f"     引数に渡して再実行する（例: python rename_package.py {new_name} パス）")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    is_dry_run = "--dry-run" in sys.argv
    if not args:
        print(__doc__)
        raise SystemExit(1)
    rename_package(args[0], [Path(p) for p in args[1:]], is_dry_run)
