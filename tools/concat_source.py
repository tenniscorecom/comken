r"""concat_source.py — comken/ 配下の .py を 1 ファイルに物理結合する。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken/tools/`` に同梱されて ``python -m comken init`` から呼ばれる
``new_project.py`` とは役割が違うので、混同しないこと。

``export_for_chat.py`` が ``__all__`` ベースの**公開 API リファレンス**を作るのに対し、
このスクリプトは ``comken/`` 配下の **.py ファイルの中身そのものを**そのまま
``comken_all_source.py`` へつなぎ合わせる。社内チャットや LLM へ貼る用途、
ライブラリの全体像を 1 ファイルで配る用途を想定。

使い方:
    python tools/concat_source.py
    python tools/concat_source.py --output F:\tmp\comken.py
    python tools/concat_source.py --root F:\dev\comken

``--root`` の直下にある ``comken/`` フォルダ配下を再帰的に走査する。
``tests/``、``docs/``、``examples/``、``tools/``（このスクリプト自身の置き場所）、
``setup_comken.bat``、``.github/`` は仕様により含めない。
"""

import argparse
import sys
from pathlib import Path

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# comken/ 配下を再帰的に走査する。キャッシュ類は Path.rglob のフィルタで除外する。
PACKAGE_NAME = "comken"

# rglob のフィルタで弾くディレクトリ名（**どの階層でも除外**）
EXCLUDED_DIR_NAMES = frozenset(
    {
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
    }
)


def _collect_python_files(package_root: Path) -> list[Path]:
    """``comken/`` 配下の .py を lexical ソートして返す。

    除外ディレクトリ以外の全階層で ``.py`` だけを拾う。``.pyc`` は拡張子で除外される。
    if で 1 ファイルずつ ``is_dir`` 判定しつつ rglob を回す。
    """
    if not package_root.is_dir():
        raise FileNotFoundError(f"走査対象が見つかりません: {package_root}")
    files: list[Path] = []
    for path in sorted(package_root.rglob("*.py")):
        # パスの途中に除外ディレクトリが含まれていたらスキップする
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(package_root).parts):
            continue
        if not path.is_file():
            continue
        files.append(path)
    return files


def _concatenate(files: list[Path], package_root: Path) -> tuple[str, int, int]:
    """各ファイルの前に区切りヘッダを差し込み、結合テキストと統計を返す。

    戻り値は (テキスト, 総行数, 総バイト数) 。行数は ``splitlines()`` ベースで数える。
    ファイル末尾には必ず改行を 1 つ足してから結合する（連結が崩れないように）。
    """
    chunks: list[str] = []
    total_bytes = 0
    for path in files:
        relative = path.relative_to(package_root.parent)  # comken/ からの相対パス
        header = f"# ===== FILE: {relative.as_posix()} =====\n"
        body = path.read_text(encoding="utf-8")
        if not body.endswith("\n"):
            body += "\n"
        chunks.append(header)
        chunks.append(body)
        total_bytes += len(header.encode("utf-8")) + len(body.encode("utf-8"))
    text = "".join(chunks)
    line_count = len(text.splitlines())
    return text, line_count, total_bytes


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python concat_source.py",
        description="comken/ 配下の .py を 1 ファイルに物理結合する",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=f"リポジトリルート（省略時: このスクリプトから推定した {ROOT}）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / f"{PACKAGE_NAME}_all_source.py",
        help=f"結合先ファイル（省略時: <root>/{PACKAGE_NAME}_all_source.py）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """指定されたルート配下の comken/ を結合して書き出す。"""
    args = _build_parser().parse_args(argv)
    root: Path = args.root.resolve()
    output: Path = args.output
    package_root = root / PACKAGE_NAME

    files = _collect_python_files(package_root)
    text, line_count, total_bytes = _concatenate(files, package_root)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")

    print(f"走査対象: {package_root}")  # noqa: T201
    print(f"出力ファイル: {output}")  # noqa: T201
    print(f"ファイル数: {len(files)}")  # noqa: T201
    print(f"総行数: {line_count:,}")  # noqa: T201
    print(f"総バイト数: {total_bytes:,}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
