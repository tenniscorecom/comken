"""comken/core/config/cli.py — ``python -m comken config`` から呼ばれる本体。

旧 ``python -m comken.core.config`` は廃止。入口は ``python -m comken`` に
集約したので、このファイルは直接実行されない（``__main__.py`` ではないため）。

このファイルが持つもの:
- ``main()`` — 既定では補完用スタブを生成する。``--check <path>`` を付けると
  config.ini の診断（``run_check``）に切り替わる。
"""

from __future__ import annotations

import argparse
import sys

from comken.core.config.check import run_check
from comken.core.config.stubs import generate_stub


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken config",
        description=("config.ini を取り扱う: 補完用スタブ（.pyi）の生成（既定） / 診断（--check）"),
    )
    parser.add_argument(
        "--check",
        nargs="?",
        const="config.ini",
        default=None,
        metavar="PATH",
        help=("config.ini を診断する（パス省略時は ./config.ini）。値は出力しない"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """``python -m comken config`` の本体。

    Args:
        argv: コマンドライン引数。省略時は ``sys.argv[1:]``。

    Returns:
        終了コード（0=成功 / 1=失敗）。
        ``--check`` を付けたときは指摘が 1 件でも見つかったら 1。
    """
    parser = _build_parser()
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.check is not None:
        return run_check(args.check)

    # 既存のスタブ生成（既定の挙動。変えない）
    stub_path = generate_stub()
    print(f"補完用スタブを生成しました: {stub_path.resolve()}")
    print("以後は Config() を呼ぶたびに自動更新されます。")
    return 0
