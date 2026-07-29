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


def _strip_template_notes(readme: Path, project_name: str) -> None:
    """README からひな形向けの節を落とし、プロジェクト名を入れる。"""
    text = readme.read_text(encoding="utf-8-sig")
    head, separator, _ = text.partition(TEMPLATE_ONLY_HEADING)
    if separator:
        # 節の直前の区切り線（---）も一緒に落とす
        head = head.rstrip().removesuffix("---").rstrip() + "\n"
    readme.write_text(head.replace(PLACEHOLDER_NAME, project_name), encoding="utf-8")


def create(project_name: str, into: Path) -> Path:
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
    args = parser.parse_args()

    # 非エンジニアがダブルクリックで使うため、想定内の失敗は traceback を見せない。
    # OSError で受けるのは、使えない文字（: * ?）をフォルダ名に入れた場合も拾うため。
    try:
        target = create(args.project_name, args.into)
    except OSError as e:
        print(f"[!] {e}")  # noqa: T201
        print(r'[!] フォルダ名に使えない文字（\ / : * ? " < > |）が無いか確認してください。')  # noqa: T201
        raise SystemExit(1) from None

    print(f"作成しました: {target}")  # noqa: T201
    print("")  # noqa: T201
    print("次にやること:")  # noqa: T201
    print("  1. 実行.bat の COMKEN_ROOT を共有サーバー上の comken の場所に合わせる")  # noqa: T201
    print("  2. 実行.bat を1度動かすと config.ini が作られるので、値を書き換える")  # noqa: T201
    print("  3. src/run.py の run() に処理を書く")  # noqa: T201
    print("  4. docs/使い方.md・docs/仕様書.md の（ここを書く）を埋める")  # noqa: T201


if __name__ == "__main__":
    main()
