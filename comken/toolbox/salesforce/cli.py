r"""comken/toolbox/salesforce/cli.py — 接続と資格情報ローテーションの確認コマンド

    python -m comken sf report --report-id 00O...
    python -m comken sf rotate --app-id 1CE... --stage-only

**このモジュールは `comken/__main__.py` から呼ばれる。** `main(argv)` を直接
呼ぶすと（テスト等）動くが、`python -m comken.toolbox.salesforce` は
もう動かない（入口は `python -m comken` に集約）。

つなぎ先は組織クラス（`sites/`）の DOMAIN_URL と CREDENTIAL_PREFIX。
`--domain` を指定したときは `site_for()` で URL から組織クラスを自動解決する。
別の登録を試すときだけ `--prefix` で上書きする。

client_id / client_secret は **DPAPI に登録したものを読む**。コマンドラインに秘密の値は渡さない。
先に `python -m comken cred import 認証情報.json` で登録しておく。

External Client App の consumer secret を REST API から回せるか（＝ローテーションを
自分たちで回せるか）は組織の設定に依存し、レスポンスの項目名も公開資料で確認できていない。
そのため段階を分けてある。`--stage-only` は Salesforce 側の切り替えを起こさないので、
まずそこまでで形を確かめる。

| コマンド | 何が起きるか |
|---|---|
| `report` | レポートを実行して行数と列名を表示する。読み取りだけ |
| `rotate --stage-only` | **新しい secret が発行される**が、切り替えない |
| `rotate` | DPAPI へ保存し Salesforce 側を切り替える。**旧 secret は猶予後に無効** |
"""

# このファイルは CLI 入口。`print` で結果を出すのが仕事なので
# ファイル全体で T201（print 検出）を許可する
# ruff: noqa: T201

import argparse
import sys

from comken.exceptions import ComkenError, SalesforceSiteSelectionError
from comken.toolbox.credentials import Credentials
from comken.toolbox.salesforce.auth.oauth_refresh import RefreshTokenOAuth
from comken.toolbox.salesforce.auth.rotation import (
    ROTATION_COMPONENT,
    SalesforceCredentialRotator,
    _staged_credentials_of,
)
from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.sites import SITES, SolutionSandbox, site_for

# 値そのものは絶対に出さない。項目名と型だけを見せる。
_SECRET_FIELDS = ("consumersecret", "consumerkey", "secret", "token", "password")

# ECA の Callback URL 設定と揃える必要がある（salesforce-authentication.md の手順と共通）
_SETUP_CALLBACK_URL = "http://localhost:8080/callback"


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

    setup = subparsers.add_parser(
        "setup", help="組織を選んで Refresh Token Flow の初回認可を対話的に行う"
    )
    setup.set_defaults(run=_run_setup)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain", default="", help="My Domain の URL（既定は組織クラスの値）")
    parser.add_argument(
        "--prefix", default="", help="DPAPI に登録したシステム名（既定は組織クラスの値）"
    )


def _open(args: argparse.Namespace) -> SalesforceBase:
    """確認対象の組織へつなぐ。

    ``--domain`` を指定すると ``site_for()`` で登録済みの組織クラスを
    自動解決する（組織ごとの挙動の違いを正しく反映するため）。
    ``--domain`` を省略すると ``SolutionSandbox``（安全側）を既定にする。
    ``--prefix`` はどちらの経路でも DPAPI のキー名だけを上書きする。
    """
    if args.domain:
        site_class = site_for(args.domain)
        return site_class(domain_url=args.domain, prefix=args.prefix)
    return SolutionSandbox(prefix=args.prefix)


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
            credential_prefix=args.prefix or type(sf).CREDENTIAL_PREFIX,
            is_enabled=True,
            interval_days=0,  # 期限に関わらず、この場で実行する
        )
        rotator.rotate_if_due()
    print("ローテーションしました。新しい secret は DPAPI に保存済みです。")
    print("  確認: python -m comken cred list")


def _stage_only(args: argparse.Namespace) -> None:
    """新しい secret を発行するところまでで止める（切り替えない）。"""
    with _open(args) as sf:
        from comken.toolbox.salesforce.auth.rotation import _consumer_id_of

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


def _select_site() -> type[SalesforceBase]:
    """SITES から番号か名前（大文字小文字を区別しない）で組織クラスを選ばせる。"""
    print("登録済みの組織:")
    for index, site_class in enumerate(SITES, start=1):
        print(f"  {index}. {site_class.__name__}")
    answer = input("番号または組織名を入力してください: ").strip()

    if answer.isdigit():
        position = int(answer)
        if 1 <= position <= len(SITES):
            return SITES[position - 1]
        raise SalesforceSiteSelectionError(answer, [s.__name__ for s in SITES])

    matches = [
        site_class for site_class in SITES if site_class.__name__.casefold() == answer.casefold()
    ]
    if len(matches) == 1:
        return matches[0]
    raise SalesforceSiteSelectionError(answer, [s.__name__ for s in SITES])


def _run_setup(_args: argparse.Namespace) -> None:
    """組織を選び、Refresh Token Flow の初回認可を対話的に行う。"""
    site_class = _select_site()
    prefix = site_class.CREDENTIAL_PREFIX
    print(f"選択: {site_class.__name__}（prefix={prefix}）")

    credentials = Credentials(prefix)
    url, _ = RefreshTokenOAuth.authorization_url(
        credentials.client_id, _SETUP_CALLBACK_URL, site_class.DOMAIN_URL
    )
    print()
    print("次の URL をブラウザで開き、Salesforce にログインして許可してください:")
    print(f"  {url}")
    print()
    print(f"許可すると {_SETUP_CALLBACK_URL}?code=... へリダイレクトされます。")
    code = input("code= の後ろの文字列を貼り付けてください: ").strip()

    RefreshTokenOAuth.exchange_code(
        credentials.client_id,
        credentials.client_secret,
        code,
        _SETUP_CALLBACK_URL,
        site_class.DOMAIN_URL,
        prefix=prefix,
    )
    print()
    print(f"refresh_token を DPAPI に保存しました（{prefix}_refresh_token）。")
    print("動作確認: python -m comken sf report --report-id 00O...")


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
