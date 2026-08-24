"""comken/__main__.py — ``python -m comken`` の単一入口。

旧来はサブモジュールごとに ``__main__.py`` が散っていて、全体像が見えなかった。
ここで**振り分けだけ**に集約し、実処理は各サブモジュールの ``main(argv)``
に委譲する（ロジックの重複実装はしない）。

    python -m comken init [プロジェクト名]            新規プロジェクト
    python -m comken sf check                        Salesforce 接続確認
    python -m comken sf report --report-id 00O...    レポートを実行
    python -m comken cred import 認証情報.json        認証情報を取り込み
    python -m comken report init レポート管理表.xlsx  管理表の雛形

``sf`` / ``cred`` は ``salesforce`` / ``credentials`` の別名
（``argparse`` の ``add_parser(..., aliases=[...])``）。

サブコマンドの実体は元の ``__main__.py`` に置いたまま呼び出すため、たとえば
``python -m comken.toolbox.salesforce check`` のような旧呼び出しも当面は
動き続ける（配置後は集約する）。
"""

import argparse
import sys
from pathlib import Path

import comken
from comken.exceptions import ComkenError
from comken.tools.new_project import create as create_project

# `--into` の既定値（カレント）は関数のデフォルトとして書く方が自然。
_DEFAULT_INTO = Path.cwd


def main(argv: list[str] | None = None) -> int:
    """コマンドを実行して終了コードを返す（0=成功 / 1=失敗）。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()

    # 引数が無いときはトップの help を出して終わる。
    # argparse には渡さない（サブコマンド必須をここで満たせないため）。
    if not argv:
        parser.print_help()
        return 0

    # 先頭が -h/--help のときはトップの help を出して終わる。
    if argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0

    # サブコマンドの help（例: `sf --help` / `sf check --help`）は
    # parse_known_args でサブコマンドまで消費した残り（`-h`/`--help`）を
    # 下流の parser に渡せば、各サブコマンドの parser が処理する。
    args, remaining = parser.parse_known_args(argv)
    try:
        result = args.run(args, remaining)
    except ComkenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0 if result is None else int(result)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken",
        description=f"comken v{comken.__version__} の CLI 入口",
        # トップレベルでは `--help` を握らない（`sf --help` 等が sf 自身の help
        # を出すようにする）。`main()` の手前で吸収する
        add_help=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="コマンド")

    # init はこの場で組み立てる（旧 __main__.py に相当するものが無い＋対話入力が要る）
    init = subparsers.add_parser(
        "init",
        help="新しいプロジェクトを雛形から作る（カレントに作る／名前は対話入力も可）",
        add_help=False,
    )
    init.add_argument(
        "project_name",
        nargs="?",
        default=None,
        help="プロジェクト名（フォルダ名になる）。省略時は入力を求める",
    )
    init.add_argument(
        "--into",
        type=Path,
        default=_DEFAULT_INTO(),
        help="作成先のフォルダ（省略すると今いるフォルダ）",
    )
    init.add_argument(
        "--python-library",
        type=Path,
        default=None,
        help=(
            "comken の場所（既定はこのパッケージのルート。"
            "雛形の bat と .vscode/settings.json へ書く）"
        ),
    )
    init.set_defaults(run=_run_init)

    # salesforce / sf（下の cli.py へ委譲。--help はそっちの parser に届けたいので
    # ここでは握らない）
    salesforce = subparsers.add_parser(
        "salesforce",
        aliases=["sf"],
        help="Salesforce 接続と資格情報の確認 → check / report / rotate",
        add_help=False,
    )
    salesforce.set_defaults(run=_run_salesforce, _prog="python -m comken sf")

    # credentials / cred
    credentials = subparsers.add_parser(
        "credentials",
        aliases=["cred"],
        help="認証情報の登録・参照・削除（DPAPI） → gui / import / list / delete",
        add_help=False,
    )
    credentials.set_defaults(run=_run_credentials, _prog="python -m comken cred")

    # report
    report = subparsers.add_parser(
        "report",
        help="Salesforce レポート管理表（Excel） → init / check",
        add_help=False,
    )
    report.set_defaults(run=_run_report)

    return parser


# ── 各サブコマンドの実体 ─────────────────────────────────────────────────────


def _run_init(args: argparse.Namespace, _remaining: list[str]) -> int:
    """``python -m comken init [プロジェクト名]`` の本体。

    名前が省略されたら ``input()`` で聞く。``new_project.create()`` が
    既存フォルダを拒否するので、上書き事故はそこで防がれる。
    """
    name = args.project_name
    if not name:
        name = input("プロジェクト名を入力してください: ")
        if not name.strip():
            print("プロジェクト名が入力されなかったので、終了します。", file=sys.stderr)
            return 1
        name = name.strip()

    # PYTHONPATH へ入れるのは comken パッケージの親（__main__.py は comken/ の中にある）
    python_library = args.python_library or Path(__file__).resolve().parent.parent
    try:
        target = create_project(name, args.into, python_library)
    except OSError as e:
        print(f"[!] {e}", file=sys.stderr)
        print(
            '[!] フォルダ名に使えない文字 (\\ / : * ? " < > |) が無いか確認してください。',
            file=sys.stderr,
        )
        return 1

    print(f"作成しました: {target}")
    print(f"comken の場所: {python_library}")
    print(
        "  （実行.bat と 認証情報の登録.bat と .vscode/settings.json に書きました。"
        "違う場合は3つとも直してください）"
    )
    print()
    print("次にやること:")
    print("  1. 実行.bat を1度動かすか python main.py を実行すると config.ini が作られる")
    print("     ので、値を書き換える")
    print("  2. src/run.py の run() に処理を書く")
    print("  3. docs/使い方.md・docs/仕様書.md の（ここを書く）を埋める")
    return 0


def _run_salesforce(_args: argparse.Namespace, remaining: list[str]) -> int:
    """``python -m comken salesforce ...`` / ``python -m comken sf ...`` の本体。

    **各コマンドの import は関数の中に置く。** 冒頭でまとめて読むと、
    その環境に無い依存（Salesforce なら `requests`）で **CLI 全体が起動しなくなる**。
    社内には `requests` が入っていない環境があり、そこで
    `python -m comken init` すら打てなくなるのは困る。`comken/internal/rpa.py` が
    社内ライブラリの import を関数内に置いているのと同じ理由。
    """
    from comken.toolbox.salesforce.cli import main as sf_main

    return sf_main(remaining)


def _run_credentials(_args: argparse.Namespace, remaining: list[str]) -> int:
    """``python -m comken credentials ...`` / ``python -m comken cred ...`` の本体。"""
    from comken.toolbox.credentials.cli import main as cred_main

    return cred_main(remaining)


def _run_report(_args: argparse.Namespace, remaining: list[str]) -> int:
    """``python -m comken report ...`` の本体。"""
    from comken.services.salesforce_downloader.cli import main as report_main

    return report_main(remaining)


if __name__ == "__main__":
    sys.exit(main())
