"""comken/core/check/cli.py — ``python -m comken check`` の CLI 入口

``runner`` 相当の純粋ロジックは ``comken/core/check/__init__.py`` に置いてある。
このファイルは CLI の組み立てと表示整形だけを担う。

    python -m comken check [path]
"""
# このファイルは CLI 入口。`print` で結果を出すのが仕事なので
# ファイル全体で T201 (print 検出) を許可する
# ruff: noqa: T201

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import comken
from comken.core.check import (
    CheckResult,
    check_deprecations,
    check_facade,
    check_imports,
    check_pyright,
    check_version,
    summarize,
)


def run_all(project_path: Path) -> list[CheckResult]:
    """全ての検査を実行して返す（純粋ロジック呼び出しの集約）。"""
    # pyright は comken 本体に対して走るので、リポジトリルートを別途渡す
    repo_root = Path(comken.__file__).resolve().parent.parent
    return [
        check_version(project_path),
        check_imports(),
        check_deprecations(project_path),
        check_facade(),
        check_pyright(repo_root),
    ]


def main(argv: list[str] | None = None) -> int:
    """CLI 本体。終了コード (0=全 OK / 1=NG あり) を返す。"""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    project_path = Path(args.path).resolve() if args.path else Path.cwd()
    results = run_all(project_path)
    ok, ng, skip = summarize(results)
    _print_human(results, ok, ng, skip)
    return 1 if ng > 0 else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken check",
        description="comken を更新したことでプロジェクトが壊れていないか検査する",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="検査対象のプロジェクトパス（省略時: カレントディレクトリ）",
    )
    return parser


# 表示順を固定する。CLI の出力はセクションごとにまとめて見せる
SECTIONS: list[tuple[str, list[str]]] = [
    ("バージョン", ["version"]),
    ("import", ["imports"]),
    ("deprecations", ["deprecations"]),
    ("ファサード", ["facade"]),
    ("pyright", ["pyright"]),
]


def _print_human(results: list[CheckResult], ok: int, ng: int, skip: int) -> None:
    """人が読む形式で出力する。"""
    print("=== comken check ===")
    print()

    sections = {r.name: r for r in results}
    for title, keys in SECTIONS:
        rows = [(name, sections[name]) for name in keys if name in sections]
        if not rows:
            continue
        print(f"[{title}]")
        for _name, r in rows:
            print(f"  {_status_label(r)}")
            for line in r.details:
                print(f"    {line}")
        print()

    print("=== 結果 ===")
    print(f"OK: {ok} / NG: {ng} / SKIP: {skip}")
    print()
    print(f"終了コード: {1 if ng > 0 else 0}")


def _status_label(r: CheckResult) -> str:
    """status を見やすい文字列に変換する。"""
    if r.status == "ok":
        return r.message if r.message else "OK"
    suffix = f": {r.message}" if r.message else ""
    if r.status == "ng":
        return f"NG{suffix}"
    if r.status == "skip":
        return f"SKIP{suffix}"
    return r.status
