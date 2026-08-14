"""comken/credentials/__main__.py — 認証情報の管理コマンド

    python -m comken.credentials import 認証情報.json   平文 JSON を取り込む
    python -m comken.credentials list                    登録済みの認証情報を接頭辞別に表示する
    python -m comken.credentials delete site_a_client_id 1件削除する

取り込んだあと、平文の JSON は**手で消す**。`--delete-source` を付けると
取り込みが成功したときだけ自動で消す。既定で消さないのは、DPAPI が
「登録したユーザー × PC」でしか復号できないため、実行アカウントが違うと
気づく前に元の値を失うことがあるから。実行アカウントで読めることを
`list` で確かめてから消すのが安全。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..exceptions import CredentialError
from .importer import import_json, split_credential_name
from .store import CREDENTIALS_PATH, delete_credential, list_names


def main(argv: list[str] | None = None) -> int:
    """コマンドを実行して終了コードを返す（0=成功 / 1=失敗）。"""
    args = _build_parser().parse_args(argv)
    try:
        args.run(args)
    except CredentialError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken.credentials",
        description=f"認証情報を暗号化して保存する（保存先: {CREDENTIALS_PATH}）",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import", help="平文 JSON を取り込む")
    importer.add_argument("json_path", type=Path, help="取り込む JSON のパス")
    importer.add_argument(
        "--delete-source",
        action="store_true",
        help="取り込みに成功したら、平文の JSON を削除する",
    )
    importer.set_defaults(run=_run_import)

    lister = subparsers.add_parser("list", help="登録済みの認証情報を接頭辞別に表示する")
    lister.set_defaults(run=_run_list)

    deleter = subparsers.add_parser("delete", help="登録済みの認証情報を1件削除する")
    deleter.add_argument("name", help="削除するキー名（例: site_a_client_id）")
    deleter.set_defaults(run=_run_delete)

    return parser


def _run_import(args: argparse.Namespace) -> None:
    names = import_json(args.json_path)
    print(f"{len(names)} 件を取り込みました: {CREDENTIALS_PATH}")
    for name in names:
        print(f"  {name}")
    if args.delete_source:
        try:
            args.json_path.unlink()
        except OSError as e:
            # 取り込み自体は成功しているので、失敗扱いにはせず消し忘れだけ伝える
            print(f"平文の JSON を削除できませんでした（{e}）。手で削除してください。")
        else:
            print(f"平文の JSON を削除しました: {args.json_path}")
    else:
        print()
        print(f"平文の JSON が残っています。中身を確認したら削除してください: {args.json_path}")


def _run_list(args: argparse.Namespace) -> None:
    names = list_names()
    if not names:
        print("登録済みの認証情報はありません。")
        return
    grouped: dict[str, list[str]] = {}
    ungrouped: list[str] = []
    for name in names:
        parts = split_credential_name(name)
        if parts is None:
            ungrouped.append(name)
            continue
        prefix, field = parts
        grouped.setdefault(prefix, []).append(field)

    print(f"登録済みの認証情報（{CREDENTIALS_PATH}）:")
    for prefix, fields in grouped.items():
        print(f"  {prefix}    {' / '.join(fields)}")
    for name in ungrouped:
        print(f"  {name}")


def _run_delete(args: argparse.Namespace) -> None:
    delete_credential(args.name)
    print(f"削除しました: {args.name}")


if __name__ == "__main__":
    sys.exit(main())
