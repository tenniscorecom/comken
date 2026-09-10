r"""comken/toolbox/salesforce/cli.py — 接続と資格情報ローテーションの確認コマンド

    python -m comken sf sites
    python -m comken sf report --site 1 --report-id 00O...
    python -m comken sf setup --site 1
    python -m comken sf rotate --app-id 1CE... --stage-only

**このモジュールは `comken/__main__.py` から呼ばれる。** `main(argv)` を直接
呼ぶすと（テスト等）動くが、`python -m comken.toolbox.salesforce` は
もう動かない（入口は `python -m comken` に集約）。

つなぎ先は組織クラス（`sites/`）の DOMAIN_URL と CREDENTIAL_PREFIX。
`--site` で番号か組織名を指定すれば `site_for()` と同じ結果になる
（URL を丸ごと書かなくて済む）。`--domain` を指定したときは `site_for()` で
URL から組織クラスを自動解決する。別の登録を試すときだけ `--prefix` で上書きする。

client_id / client_secret は **DPAPI に登録したものを読む**。コマンドラインに秘密の値は渡さない。
先に `python -m comken cred gui`（または `cred import 認証情報.json`）で登録しておく。

External Client App の consumer secret を REST API から回せるか（＝ローテーションを
自分たちで回せるか）は組織の設定に依存し、レスポンスの項目名も公開資料で確認できていない。
そのため段階を分けてある。`--stage-only` は Salesforce 側の切り替えを起こさないので、
まずそこまでで形を確かめる。

| コマンド | 何が起きるか |
|---|---|
| `sites` | 登録済みの組織を番号・表示名・DOMAIN_URL・CREDENTIAL_PREFIX 一覧表示 |
| `report --site <番号\|組織名>` | レポートを実行して行数と列名を表示する。読み取りだけ |
| `setup --site <番号\|組織名>` | 組織を選んで Refresh Token Flow の初回認可を対話的に行う |
| `rotate --stage-only` | **新しい secret が発行される**が、切り替えない |
| `rotate` | DPAPI へ保存し Salesforce 側を切り替える。**旧 secret は猶予後に無効** |
"""

# このファイルは CLI 入口。`print` で結果を出すのが仕事なので
# ファイル全体で T201（print 検出）を許可する
# ruff: noqa: T201

import argparse
import sys
import webbrowser

from comken.exceptions import (
    ComkenError,
    CredentialNotFoundError,
    SalesforceAuthError,
    SalesforceSiteSelectionError,
)
from comken.toolbox.credentials import Credentials
from comken.toolbox.salesforce.auth.callback_server import (
    CallbackResult,
    is_localhost_callback,
    parse_redirect_url,
    wait_for_callback,
)
from comken.toolbox.salesforce.auth.oauth_refresh import AuthorizationRequest, RefreshTokenOAuth
from comken.toolbox.salesforce.auth.rotation import (
    ROTATION_COMPONENT,
    SalesforceCredentialRotator,
    _staged_credentials_of,
)
from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.sites import SITES, SolutionSandbox, site_for

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

    sites = subparsers.add_parser("sites", help="登録済みの組織を一覧表示する")
    sites.set_defaults(run=_run_sites)

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
    setup.add_argument("--site", default="", help="番号か組織名を指定して対話選択を省略する")
    setup.set_defaults(run=_run_setup)

    return parser


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--site", default="", help="番号か組織名で組織を指定する（--domain より簡単）"
    )
    parser.add_argument("--domain", default="", help="My Domain の URL（既定は組織クラスの値）")
    parser.add_argument(
        "--prefix", default="", help="DPAPI に登録したシステム名（既定は組織クラスの値）"
    )


def _open(args: argparse.Namespace) -> SalesforceBase:
    """確認対象の組織へつなぐ。

    優先順位: ``--site``（番号/組織名） > ``--domain``（URLからsite_for()で自動解決）
    > 省略時は ``SolutionSandbox``（安全側）。``--prefix`` はどの経路でも
    DPAPI のキー名だけを上書きする。
    """
    if args.site:
        site_class = _resolve_site(args.site)
        return site_class(prefix=args.prefix)
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

    if not args.yes and not _confirm("旧 secret は猶予後に使えなくなります。続けますか？"):
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


def _confirm(message: str) -> bool:
    """確認プロンプトを出し、``y`` であれば True を返す。``[y/N]:`` は関数側で付ける。"""
    answer = input(f"{message} [y/N]: ")
    return answer.strip().lower() == "y"


def _resolve_site(answer: str) -> type[SalesforceBase]:
    """番号または組織名（大文字小文字を区別しない）から組織クラスを引く。"""
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


def _select_site() -> type[SalesforceBase]:
    """SITES を番号付きで表示し、入力させてから ``_resolve_site()`` で解決する。"""
    _print_sites()
    answer = input("番号または組織名を入力してください: ").strip()
    return _resolve_site(answer)


def _print_sites() -> None:
    """SITES を番号・表示名つきで一覧表示する（sites サブコマンドと setup の両方で使う）。"""
    print("登録済みの組織:")
    for index, site_class in enumerate(SITES, start=1):
        print(f"  {index}. {site_class.__name__}（{site_class.display_name()}）")


def _run_sites(_args: argparse.Namespace) -> None:
    """登録済みの組織を、名前・DOMAIN_URL・CREDENTIAL_PREFIX つきで一覧表示する。"""
    _print_sites()
    print()
    for site_class in SITES:
        print(f"{site_class.__name__}（{site_class.display_name()}）")
        print(f"  DOMAIN_URL: {site_class.DOMAIN_URL}")
        print(f"  CREDENTIAL_PREFIX: {site_class.CREDENTIAL_PREFIX}")


def _run_setup(args: argparse.Namespace) -> None:
    """組織を選び、Refresh Token Flow の初回認可を対話的に行う。"""
    site_class = _resolve_site(args.site) if args.site else _select_site()
    prefix = site_class.CREDENTIAL_PREFIX

    print()
    print(f"接続先: {site_class.__name__}（{site_class.display_name()}）")
    print(f"  DOMAIN_URL: {site_class.DOMAIN_URL}")
    print(f"  CREDENTIAL_PREFIX: {prefix}")
    print(f"  CALLBACK_URL: {site_class.CALLBACK_URL}")
    if not _confirm("この接続先で初回認証を開始しますか？"):
        print("中止しました。")
        return

    try:
        credentials = Credentials(prefix)
        client_id = credentials.api_client_id
        client_secret = credentials.api_client_secret
    except CredentialNotFoundError:
        print()
        print(f"{prefix}.api_client_id / {prefix}.api_client_secret が未登録です。")
        print("先に次のコマンドで client_id / client_secret を登録してください:")
        print("  python -m comken cred gui")
        raise

    auth_request = RefreshTokenOAuth.authorization_url(
        client_id, site_class.CALLBACK_URL, site_class.DOMAIN_URL
    )
    code = _obtain_authorization_code(auth_request, site_class.CALLBACK_URL)

    RefreshTokenOAuth.exchange_code(
        client_id,
        client_secret,
        code,
        site_class.CALLBACK_URL,
        site_class.DOMAIN_URL,
        auth_request.code_verifier,
        prefix=prefix,
    )
    print()
    print(f"refresh_token を DPAPI に保存しました（{prefix}.api_refresh_token）。")
    site_number = SITES.index(site_class) + 1
    print(f"動作確認: python -m comken sf report --site {site_number} --report-id 00O...")


def _obtain_authorization_code(auth_request: AuthorizationRequest, redirect_uri: str) -> str:
    """認可コードを受け取る。

    redirect_uri が localhost ならブラウザを自動で開き、リダイレクトも自動で
    受け取る。自動受け取りに失敗した場合・localhost でない場合は、
    リダイレクトされた URL 全体を貼り付けさせて解析する（``code=`` の
    後ろだけを切り出させると、認可コードに含まれることが多い ``=`` 等の
    記号で貼り間違いが起きやすいため、URL 全体をそのまま受け取る）。
    """
    print()
    print("次の URL をブラウザで開き、Salesforce にログインして許可してください:")
    print(f"  {auth_request.url}")

    if is_localhost_callback(redirect_uri):
        print()
        print("ブラウザを自動で開きます。承認すると自動で受け取ります...")
        webbrowser.open(auth_request.url)
        try:
            callback = wait_for_callback(redirect_uri, auth_request.state)
        except (OSError, TimeoutError, SalesforceAuthError) as e:
            print(f"自動受け取りに失敗しました（{e}）。手動で貼り付けてください。")
        else:
            print("認可コードを自動で受け取りました。")
            return _code_of(callback, auth_request)

    print()
    print(f"許可すると {redirect_uri}?code=... へリダイレクトされます。")
    print("そのリダイレクト先の URL を、アドレスバーからそのまま貼り付けてください。")
    while True:
        redirected_url = input("URL: ").strip()
        try:
            callback = parse_redirect_url(redirected_url)
        except SalesforceAuthError as e:
            print(f"URL を読み取れませんでした（{e}）。もう一度貼り付けてください。")
            continue
        return _code_of(callback, auth_request)


def _code_of(callback: CallbackResult, auth_request: AuthorizationRequest) -> str:
    """CSRF検証（stateの一致）をしてから code を返す。"""
    if callback.state != auth_request.state:
        raise SalesforceAuthError(200, "state が一致しません（CSRF検証に失敗しました）")
    return callback.code


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
