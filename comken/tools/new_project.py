"""comken/tools/new_project.py — 新しいプロジェクトのフォルダ一式を、ひな形から作る。

`templates/新規プロジェクト/` をコピーし、プロジェクト名を差し込み、
ひな形の説明文（作り終えたら消す節）を取り除く。
`config.ini` はここでは作らない（初回実行時に `config.ini.example` から
`comken` が作って確認を促す作り）。

**このファイルはパッケージに同梱されている（配布される）。** ``comken init``
（``comken/__main__.py`` から）はここを呼ぶ。リポジトリ直下の ``tools/`` に
入っている開発用スクリプト（``export_for_chat.py``）とは役割が違うので、
混同しないこと。

使い方:
    python -m comken init 受注取込
    python -m comken init 受注取込 --into "C:\\作業\\tools"
"""

import argparse
import shutil
from pathlib import Path

# このファイルは comken/tools/ にあるので、comken パッケージのルートは1つ上。
# テンプレートは同じ comken/ の下にある（comken/templates/新規プロジェクト）。
ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = ROOT / "templates" / "新規プロジェクト"

# PYTHONPATH へ入れる場所は **comken パッケージそのものではなく、その親**。
# import comken できるのは親を通したときで、パッケージ自身を通しても読めない。
# 生成する bat も %PYTHON_LIBRARY%\comken\__init__.py の実在を確かめる（＝親を期待する）
IMPORT_ROOT = ROOT.parent

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
# comken パッケージの**親**（PYTHONPATH へ入れる場所）を指す
PLACEHOLDER_PYTHON_LIBRARY = r"\\server\share\tools"

# comken の場所を書いてあるファイル。bat は \ 区切り、settings.json は JSON なので / 区切り。
# 雛形には 2 つの bat と settings.json がある（実行.bat・認証情報の登録.bat・settings.json）。
PYTHON_LIBRARY_FILES = (
    "実行.bat",
    "認証情報の登録.bat",
    ".vscode/settings.json",
)


def create(project_name: str, into: Path, python_library: Path = IMPORT_ROOT) -> Path:
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
    _fill_python_library(target, python_library)

    # NOTE: config.ini はここでは作らない。初回実行時に comken が
    #       config.ini.example から作って確認を促す（作り忘れの受け皿はそちらに一本化）。
    return target


def main() -> None:
    """``python tools/new_project.py <名前>`` 形式で直接呼ばれたときの本体。

    ``python -m comken init ...`` から呼ぶ形が標準。**テストや動作確認用**
    に残してある（``if __name__ == "__main__"`` ブロックから呼ばれる）。
    """
    parser = argparse.ArgumentParser(description="新しいプロジェクトのひな形を作る")
    parser.add_argument("project_name", help="プロジェクト名（フォルダ名になる）")
    parser.add_argument(
        "--into",
        type=Path,
        default=Path.cwd(),
        help="作成先のフォルダ（省略すると今いるフォルダ）",
    )
    parser.add_argument(
        "--python-library",
        type=Path,
        default=IMPORT_ROOT,
        help="PYTHONPATH へ入れる場所（comken パッケージの親）",
    )
    args = parser.parse_args()

    # 非エンジニアがダブルクリックで使うため、想定内の失敗は traceback を見せない。
    # OSError で受けるのは、使えない文字（: * ?）をフォルダ名に入れた場合も拾うため。
    try:
        target = create(args.project_name, args.into, args.python_library)
    except OSError as e:
        print(f"[!] {e}")
        print(r'[!] フォルダ名に使えない文字（\ / : * ? " < > |）が無いか確認してください。')
        raise SystemExit(1) from None

    print(f"作成しました: {target}")
    print(f"comken の場所: {args.python_library}")
    print(
        "  （実行.bat と 認証情報の登録.bat と .vscode/settings.json に書きました。"
        "違う場合は3つとも直してください）"
    )
    print("")
    print("次にやること:")
    print("  1. 実行.bat を1度動かすか python main.py を実行すると config.ini が作られる")
    print("     ので、値を書き換える")
    print("  2. src/run.py の run() に処理を書く")
    print("  3. docs/使い方.md・docs/仕様書.md の（ここを書く）を埋める")


def _encoding_of(path: Path) -> str:
    """そのファイルの文字コード。bat は cmd.exe に合わせて CP932。"""
    return "cp932" if path.suffix.lower() == ".bat" else "utf-8"


def _fill_project_name(target: Path, project_name: str) -> None:
    """ひな形の（プロジェクト名）を実際の名前に置き換える。"""
    for name in NAMED_FILES:
        path = target / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8-sig")
        if PLACEHOLDER_NAME in text:
            path.write_text(text.replace(PLACEHOLDER_NAME, project_name), encoding="utf-8")


def _fill_python_library(target: Path, python_library: Path) -> None:
    """ひな形に書いてある comken の場所を、実際の場所に置き換える。

    実行.bat と 認証情報の登録.bat（実行時の PYTHONPATH）と .vscode/settings.json
    （VS Code の補完・定義ジャンプ）で同じ場所が要る。手で両方を直す形にすると
    片方を忘れ、動くのに補完だけ効かない状態になる。
    忘れようがないよう、ここでまとめて入れる。
    """
    slash_placeholder = PLACEHOLDER_PYTHON_LIBRARY.replace("\\", "/")
    slash_root = str(python_library).replace("\\", "/")
    for name in PYTHON_LIBRARY_FILES:
        path = target / name
        if not path.is_file():
            continue
        encoding = _encoding_of(path)
        text = path.read_text(encoding=encoding)
        # JSON は \ が特殊文字なので / 区切りで書いてある。先に / 版を replace する
        text = text.replace(slash_placeholder, slash_root)
        text = text.replace(PLACEHOLDER_PYTHON_LIBRARY, str(python_library))
        path.write_text(text, encoding=encoding)


def _strip_template_notes(readme: Path, project_name: str) -> None:
    """README からひな形向けの節を落とし、プロジェクト名を入れる。"""
    text = readme.read_text(encoding="utf-8-sig")
    head, separator, _ = text.partition(TEMPLATE_ONLY_HEADING)
    if separator:
        # 節の直前の区切り線（---）も一緒に落とす
        head = head.rstrip().removesuffix("---").rstrip() + "\n"
    readme.write_text(head.replace(PLACEHOLDER_NAME, project_name), encoding="utf-8")


if __name__ == "__main__":
    main()
