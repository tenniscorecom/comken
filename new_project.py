"""新しいプロジェクトのフォルダ一式を、ひな形から作る。

`templates/新規プロジェクト/` をコピーし、プロジェクト名を差し込み、
`config.ini` を用意し、ひな形の説明文（作り終えたら消す節）を取り除く。

使い方:
    python new_project.py 受注取込
    python new_project.py 受注取込 --into "C:\\作業\\tools"

`新規プロジェクト作成.bat` をダブルクリックしても同じことができる。
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = ROOT / "templates" / "新規プロジェクト"

# コピーしないもの（開発ツールが作るキャッシュと、実行時の生成物）
IGNORED = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    ".git",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
    "typings",
    "logs",
    "config.ini",
)

# README のうち、作り終えたら消す節。ここから下を丸ごと落とす。
TEMPLATE_ONLY_HEADING = "## このひな形の使い方"

PLACEHOLDER_NAME = "（プロジェクト名）"

# プロジェクト名を差し込むファイル（main.py は社内 RPA 基盤へ渡す名前として使う）
NAMED_FILES = ("main.py", "docs/仕様書.md", "docs/使い方.md")

# ひな形に書いてある comken の場所。実際の場所に置き換える。
PLACEHOLDER_COMKEN_ROOT = r"\\server\share\tools\comken"

# comken の場所を書いてあるファイル。bat は \ 区切り、settings.json は JSON なので / 区切り。
COMKEN_ROOT_FILES = ("実行.bat", "スタブ生成.bat", ".vscode/settings.json")


def _fill_project_name(target: Path, project_name: str) -> None:
    """ひな形の（プロジェクト名）を実際の名前に置き換える。"""
    for name in NAMED_FILES:
        path = target / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        if PLACEHOLDER_NAME in text:
            path.write_text(text.replace(PLACEHOLDER_NAME, project_name), encoding="utf-8")


def _fill_comken_root(target: Path, comken_root: Path) -> None:
    """ひな形に書いてある comken の場所を、実際の場所に置き換える。

    実行.bat（実行時の PYTHONPATH）と .vscode/settings.json（VS Code の補完・定義ジャンプ）で
    同じ場所が要る。手で両方を直す形にすると片方を忘れ、動くのに補完だけ効かない状態になる。
    忘れようがないよう、ここでまとめて入れる。
    """
    slash_placeholder = PLACEHOLDER_COMKEN_ROOT.replace("\\", "/")
    slash_root = str(comken_root).replace("\\", "/")
    for name in COMKEN_ROOT_FILES:
        path = target / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        # JSON は \ が特殊文字なので / 区切りで書いてある。先に / 版を replace する
        text = text.replace(slash_placeholder, slash_root)
        text = text.replace(PLACEHOLDER_COMKEN_ROOT, str(comken_root))
        path.write_text(text, encoding="utf-8")


def _strip_template_notes(readme: Path, project_name: str) -> None:
    """README からひな形向けの節を落とし、プロジェクト名を入れる。"""
    text = readme.read_text(encoding="utf-8-sig")
    head, separator, _ = text.partition(TEMPLATE_ONLY_HEADING)
    if separator:
        # 節の直前の区切り線（---）も一緒に落とす
        head = head.rstrip().removesuffix("---").rstrip() + "\n"
    readme.write_text(head.replace(PLACEHOLDER_NAME, project_name), encoding="utf-8")


def create(project_name: str, into: Path, comken_root: Path = ROOT) -> Path:
    """ひな形をコピーして、新しいプロジェクトのフォルダを作る。"""
    if not TEMPLATE_DIR.is_dir():
        raise FileNotFoundError(f"ひな形が見つかりません: {TEMPLATE_DIR}")

    target = into / project_name
    # 既存フォルダを上書きすると、書きかけの中身が消える。必ず止める。
    if target.exists():
        raise FileExistsError(
            f"すでに同じ名前のフォルダがあります: {target}\n"
            "別の名前にするか、既存のフォルダを移動してから実行してください。"
        )

    shutil.copytree(TEMPLATE_DIR, target, ignore=IGNORED)
    _strip_template_notes(target / "README.md", project_name)
    _fill_project_name(target, project_name)
    _fill_comken_root(target, comken_root)

    # NOTE: config.ini はここでは作らない。初回実行時に comken が
    #       config.ini.example から作って確認を促す（作り忘れの受け皿はそちらに一本化）。
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="新しいプロジェクトのひな形を作る")
    parser.add_argument("project_name", help="プロジェクト名（フォルダ名になる）")
    parser.add_argument(
        "--into",
        type=Path,
        default=Path.cwd(),
        help="作成先のフォルダ（省略すると今いるフォルダ）",
    )
    parser.add_argument(
        "--comken-root",
        type=Path,
        default=ROOT,
        help="comken の場所（省略するとこのスクリプトがある場所）",
    )
    args = parser.parse_args()

    # 非エンジニアがダブルクリックで使うため、想定内の失敗は traceback を見せない。
    # OSError で受けるのは、使えない文字（: * ?）をフォルダ名に入れた場合も拾うため。
    try:
        target = create(args.project_name, args.into, args.comken_root)
    except OSError as e:
        print(f"[!] {e}")  # noqa: T201
        print(r'[!] フォルダ名に使えない文字（\ / : * ? " < > |）が無いか確認してください。')  # noqa: T201
        raise SystemExit(1) from None

    print(f"作成しました: {target}")  # noqa: T201
    print(f"comken の場所: {args.comken_root}")  # noqa: T201
    print("  （実行.bat と .vscode/settings.json に入れました。違う場合は両方を直してください）")  # noqa: T201
    print("")  # noqa: T201
    print("次にやること:")  # noqa: T201
    print("  1. 実行.bat を1度動かすと config.ini が作られるので、値を書き換える")  # noqa: T201
    print("  2. src/run.py の run() に処理を書く")  # noqa: T201
    print("  3. docs/使い方.md・docs/仕様書.md の（ここを書く）を埋める")  # noqa: T201


if __name__ == "__main__":
    main()
