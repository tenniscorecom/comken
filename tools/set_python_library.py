r"""set_python_library.py — 各プロジェクトが見ている comken の場所をまとめて変える。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken/tools/`` に同梱されて ``python -m comken init`` から呼ばれる
``new_project.py`` とは役割が違うので、混同しないこと。

共有サーバー上の comken を別の場所へ移すと、利用プロジェクト側の**1プロジェクトにつき
3か所**（実行.bat・認証情報の登録.bat・.vscode/settings.json）が
古い場所を指したままになる。プロジェクトが増えるほど手で直すのは現実的でなくなり、
**直し漏れたプロジェクトだけが動かなくなる**。しかも実行.bat だけ直して
settings.json を忘れると、動くのに補完だけ効かないという分かりにくい状態になる。

使い方:
    python tools/set_python_library.py \\新サーバー\share\tools           確認だけ
    python tools/set_python_library.py \\新サーバー\share\tools --apply   実際に書き換える
    python tools/set_python_library.py \\新サーバー\share\tools F:\案件 --apply

**既定は確認だけで、--apply を付けたときにだけ書き換える。** 打ち間違えたまま
何十ファイルも書き換えると、元がどこを指していたか分からなくなる。先に一覧を見て、
狙ったファイルだけかを確かめてから実行する。

今どこを指していても書き換えられる（決まった値からの置換ではない）ので、
置き場所が定まるまで何度でも通してよい。
"""

import argparse
import re
import sys
from pathlib import Path

# comken の場所を書いてあるファイル。bat は \ 区切り、settings.json は JSON なので / 区切り。
# 新しく場所を書くファイルを増やしたら、ここにも足す（足し忘れるとそこだけ古いままになる）
PYTHON_LIBRARY_FILES = (
    "実行.bat",
    "認証情報の登録.bat",
    ".vscode/settings.json",
)

# bat の `set "PYTHON_LIBRARY=..."` の値だけを置き換える。キー名で特定するので、
# 今そこに何が書かれていても拾える
BAT_PATTERN = re.compile(r'(set\s+"PYTHON_LIBRARY=)([^"]*)(")')

# settings.json の extraPaths の**最初の要素**を置き換える。
# 雛形は extraPaths に comken の親パスしか書かないので「先頭だけ見れば十分」。
# 別の要素が後ろに並んでいても巻き込まないため
JSON_PATTERN = re.compile(r'("python\.analysis\.extraPaths"\s*:\s*\[\s*")([^"]+)(")')


def main(argv: list[str] | None = None) -> int:
    """対象を探して表示し、--apply が付いていれば書き換える。"""
    args = _build_parser().parse_args(argv)
    folders = args.folders or [Path.cwd()]

    changes = _collect_changes(folders, args.python_library)
    if not changes:
        print("書き換える対象が見つかりませんでした。")  # noqa: T201
        print(f"探した場所: {'、'.join(str(folder) for folder in folders)}")  # noqa: T201
        return 1

    for path, old_root, new_root in changes:
        print(path)  # noqa: T201
        print(f"    {old_root}")  # noqa: T201
        print(f"  → {new_root}")  # noqa: T201

    if not args.apply:
        print(f"\n{len(changes)} ファイルが対象です。")  # noqa: T201
        print("内容を確認したら、--apply を付けて実行すると書き換えます。")  # noqa: T201
        return 0

    for path, _, _ in changes:
        _write(path, args.python_library)
    print(f"\n{len(changes)} ファイルを書き換えました。")  # noqa: T201
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python set_python_library.py",
        description="各プロジェクトが見ている comken の場所をまとめて変える",
    )
    parser.add_argument("python_library", help=r"新しい comken の場所（例: \\server\share\tools）")
    parser.add_argument(
        "folders",
        nargs="*",
        type=Path,
        help="探すフォルダ（複数可）。省略すると今いるフォルダの下を探す",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際に書き換える（付けないと確認だけ）",
    )
    return parser


def _collect_changes(folders: list[Path], python_library: str) -> list[tuple[Path, str, str]]:
    """書き換えが必要なファイルを (パス, 今の値, 新しい値) で集める。

    すでに新しい場所を指しているファイルは対象にしない。「何ファイル変わるか」を
    そのまま確認に使えるようにするため。
    """
    changes: list[tuple[Path, str, str]] = []
    seen: set[Path] = set()
    for folder in folders:
        for path in _find_targets(folder):
            if path in seen:  # 探すフォルダが入れ子でも二重に数えない
                continue
            seen.add(path)
            old_root, new_root = _roots_of(path, python_library)
            if old_root is not None and old_root != new_root:
                changes.append((path, old_root, new_root))
    return changes


def _find_targets(folder: Path) -> list[Path]:
    """フォルダの下から、comken の場所を書いているファイルを探す。"""
    found: list[Path] = []
    for name in PYTHON_LIBRARY_FILES:
        # 直下と、その下のプロジェクトフォルダの両方を見る（プロジェクトの中で実行しても、
        # プロジェクトを並べた親フォルダで実行しても同じように使える）
        found.extend(sorted(folder.glob(name)))
        found.extend(sorted(folder.glob(f"*/{name}")))
    return found


def _roots_of(path: Path, python_library: str) -> tuple[str | None, str]:
    """そのファイルが今指している場所と、書き込むべき値を返す。"""
    pattern, new_root = _pattern_and_root(path, python_library)
    matched = pattern.search(path.read_text(encoding=_encoding_of(path)))
    return (matched.group(2) if matched else None), new_root


def _write(path: Path, python_library: str) -> None:
    """そのファイルの comken の場所を書き換える。"""
    pattern, new_root = _pattern_and_root(path, python_library)
    encoding = _encoding_of(path)
    text = pattern.sub(lambda m: f"{m.group(1)}{new_root}{m.group(3)}", path.read_text(encoding))
    path.write_text(text, encoding=encoding)


def _pattern_and_root(path: Path, python_library: str) -> tuple[re.Pattern[str], str]:
    """ファイルの種類ごとの、探す形と書き込む値。"""
    if path.suffix.lower() == ".json":
        # JSON では \ が特殊文字なので区切りは / で書く
        return JSON_PATTERN, python_library.replace("\\", "/")
    return BAT_PATTERN, python_library


def _encoding_of(path: Path) -> str:
    """そのファイルの文字コード。bat は cmd.exe に合わせて CP932。"""
    return "cp932" if path.suffix.lower() == ".bat" else "utf-8"


if __name__ == "__main__":
    sys.exit(main())
