r"""comken/toolbox/salesforce/cli.py — 接続と資格情報ローテーションの確認コマンド

    python -m comken sf check
    python -m comken sf report --report-id 00O...
    python -m comken sf rotate --app-id 1CE... --stage-only

**このモジュールは `comken/__main__.py` から呼ばれる。** `main(argv)` を直接
呼ぶすと（テスト等）動くが、`python -m comken.toolbox.salesforce` は
もう動かない（入口は `python -m comken` に集約）。

つなぎ先は組織クラス（`sites/`）の DOMAIN_URL と CREDENTIAL_PREFIX。
別の組織・別の登録を試すときだけ `--domain` / `--prefix` で上書きする。

client_id / client_secret は **DPAPI に登録したものを読む**。コマンドラインに秘密の値は渡さない。
先に `python -m comken cred import 認証情報.json` で登録しておく。

External Client App の consumer secret を REST API から回せるか（＝ローテーションを
自分たちで回せるか）は組織の設定に依存し、レスポンスの項目名も公開資料で確認できていない。
そのため段階を分けてある。`--stage-only` は Salesforce 側の切り替えを起こさないので、
まずそこまでで形を確かめる。

| コマンド | 何が起きるか |
|---|---|
| `check` | `/limits` の GET で接続確認（副作用なし） |
| `report` | レポートを実行して行数と列名を表示する。読み取りだけ |
| `rotate --stage-only` | **新しい secret が発行される**が、切り替えない |
| `rotate` | DPAPI へ保存し Salesforce 側を切り替える。**旧 secret は猶予後に無効** |
"""

# このファイルは CLI 入口。`print` で結果を出すのが仕事なので
# ファイル全体で T201（print 検出）を許可する
# ruff: noqa: T201

import argparse
import sys

from comken.exceptions import ComkenError
from comken.toolbox.salesforce.rotation import (
    ROTATION_COMPONENT,
    SalesforceCredentialRotator,
    _staged_credentials_of,
)
from comken.toolbox.salesforce.sites import Sandbox

# 値そのものは絶対に出さない。項目名と型だけを見せる。
_SECRET_FIELDS = ("consumersecret", "consumerkey", "secret", "token", "password")


def main(argv: list[str] | None = None) -> int:
    """コマンドを実行して終了コードを返す（0=成功 / 1=失敗）。"""
    args = _build_parser().parse_args(argv)
    try:
        args.run(args)
    except ComkenError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken sf",
        description="Salesforce への接続と、資格情報ローテーションの可否を確かめる",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    checker = subparsers.add_parser("check", help="接続できるか確かめる（副作用なし）")
    _add_common_arguments(checker)
    checker.set_defaults(run=_run_check)

    report = subparsers.add_parser("report", help="レポートを実行して行数と列名を見る")
    _add_common_arguments(report)
    report.add_argument("--report-id", required=True, help="レポート ID（URL の末尾）")
    report.add_argument(
        "--rows",
        type=int,
        default=0,
        help="先頭から何行ぶんの中身を表示するか（既定 0＝列名だけ）",
    )
    report.set_defaults(run=_run_report)

    rotate = subparsers.add_parser("rotate", help="資格情報をローテーションする")
    _add_common_arguments(rotate)
    rotate.add_argument("--app-id", required=True, help="External Client App の ID")
    rotate.add_argument(
        "--stage-only",
        action="store_true",
        help="新しい secret の発行までで止める（Salesforce 側を切り替えない）",
    )
    rotate.add_argument("--yes", action="store_true", help="切り替えの確認を省く")
    rotate.set_defaults(run=_run_rotate)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", default="", help="My Domain の URL（既定は組織クラスの値）")
    parser.add_argument(
        "--prefix", default="", help="DPAPI に登録したシステム名（既定は組織クラスの値）"
    )


def _open(args: argparse.Namespace) -> Sandbox:
    """確認対象の組織へつなぐ。--domain / --prefix があればそちらを使う。"""
    return Sandbox(domain_url=args.domain, prefix=args.prefix)


def _run_check(args: argparse.Namespace) -> None:
    """``/limits`` を GET して接続を確認する（副作用なし）。

    ``--app-id`` で ECA の consumerId まで踏み込む経路は v1.0.0 で削除した。
    ECA の資格情報 API は ``client_id`` / ``client_secret`` / ``refresh_token``
    を返さないため、SF 側の実際の値は画面で確認するしかなく、CLI で
    ``consumerId`` だけ取れても用途が限られるため。
    """
    with _open(args) as sf:
        sf.request("GET", sf.data_path("/limits"), component=ROTATION_COMPONENT)
        print(f"接続できました（API v{sf.API_VERSION}）")


def _run_report(args: argparse.Namespace) -> None:
    """主用途（レポートの読み取り）が通るか確かめる。"""
    with _open(args) as sf:
        rows = sf.report.get(args.report_id, allow_truncated=True)
    print(f"{len(rows)} 行 取得しました")
    if not rows:
        return
    print("列:")
    for column in rows[0]:
        print(f"  {column}")
    for row in rows[: args.rows]:
        print(f"  {row}")


def _run_rotate(args: argparse.Namespace) -> None:
    if args.stage_only:
        _stage_only(args)
        return

    if not args.yes and not _confirm():
        print("中止しました。")
        return

    with _open(args) as sf:
        rotator = SalesforceCredentialRotator(
            sf,
            app_id=args.app_id,
            credential_prefix=args.prefix or Sandbox.CREDENTIAL_PREFIX,
            is_enabled=True,
            interval_days=0,  # 期限に関わらず、この場で実行する
        )
        rotator.rotate_if_due()
    print("ローテーションしました。新しい secret は DPAPI に保存済みです。")
    print("  確認: python -m comken cred list")


def _stage_only(args: argparse.Namespace) -> None:
    """新しい secret を発行するところまでで止める（切り替えない）。"""
    with _open(args) as sf:
        from comken.toolbox.salesforce.rotation import _consumer_id_of

        credentials, _ = sf.request(
            "GET",
            sf.data_path(f"/apps/oauth/credentials/{args.app_id}"),
            component=ROTATION_COMPONENT,
        )
        consumer_id = _consumer_id_of(credentials)
        body, _ = sf.request(
            "POST",
            sf.data_path(f"/apps/oauth/credentials/{args.app_id}/{consumer_id}/staged"),
            component=ROTATION_COMPONENT,
        )
    print("staged 作成の応答:")
    _print_shape(body)
    staged = _staged_credentials_of(body)  # 取り出せるかをここで確かめる
    print(f"\n必要な3項目を取り出せました（staged id: {staged.staged_id}）")
    print("まだ切り替えていません。切り替えるには --stage-only を外して実行してください。")


def _confirm() -> bool:
    answer = input("旧 secret は猶予後に使えなくなります。続けますか？ [y/N]: ")
    return answer.strip().lower() == "y"


def _print_shape(body: object, indent: str = "  ") -> None:
    """応答の形（項目名と型）だけを表示する。秘密の値は出さない。"""
    if isinstance(body, list):
        print(f"{indent}[{len(body)} 件のリスト]")
        if body:
            _print_shape(body[0], indent + "  ")
        return
    if not isinstance(body, dict):
        print(f"{indent}{type(body).__name__}")
        return
    for key, value in body.items():
        if key.lower() in _SECRET_FIELDS:
            print(f"{indent}{key}: *** ({len(str(value))} 文字)")
        elif isinstance(value, dict | list):
            print(f"{indent}{key}:")
            _print_shape(value, indent + "  ")
        else:
            print(f"{indent}{key}: {value!r}")


# このモジュールは `python -m comken.toolbox.salesforce` からは実行しない
# （入口は `python -m comken` に集約）。直接呼ぶのはテスト等だけで、
# CLI としての起動は `comken/__main__.py` から `main(argv)` を呼ぶ形になる。
