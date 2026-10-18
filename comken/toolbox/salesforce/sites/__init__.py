"""comken/toolbox/salesforce/sites/__init__.py — 組織（サイト）ごとの Salesforce クライアント。

組織は My Domain の URL と認証情報が違うので、1組織につき1クラス・1インスタンスにする。
共通の操作（SOQL・CRUD・レポート・計測）は `SalesforceBase` が持っているので、
ここに書くのは**その組織でしか通じないもの**だけにする。

    from comken.toolbox.salesforce.sites import Solution

    with Solution() as sf:
        rows = sf.report.get("00O...")

URL と認証情報のシステム名はクラス定数なので、呼び出し側は何も渡さなくてよい。
本番とテストで登録を切り替えるときだけシステム名を渡す:

    with Solution(prefix=config.SALESFORCE.CREDENTIAL_PREFIX) as sf:
        ...

client_id / client_secret は DPAPI から読む（`comken.toolbox.credentials`）ので、
コードにも config.ini にも秘密の値は現れない。

組織を増やすときは、このフォルダに `SalesforceBase` を継承したファイルを1つ足す。
**`DOMAIN_URL` を空のままにしない**（空だと土台クラス扱いで登録されない）。
ファイル名が `_` で始まるものは無視される（雛形置き場）。

CLI は `SITES` の**番号**をユーザーに見せるので、順序は決定的
（モジュール名の昇順）。

> [!warning] 組織名と URL は仮の値
> **このリポジトリは公開しているので、実際の組織名・URL を書かない。**
> `Solution` の `DOMAIN_URL` はダミーで、共有サーバーへ配置するときに
> 実際の値へ書き換える（Salesforce は comken 自前の `comken/toolbox/salesforce/`
> を使うため、社内ライブラリ名は出てこない）。
> 書き換えるのは各ファイルの `DOMAIN_URL`・`CREDENTIAL_PREFIX`・`REPORT_*` と、
> 組織名を出すならクラス名。**実名をこのリポジトリへ書き戻さないこと。**
"""

from __future__ import annotations

import sys

from comken.core.discovery import find_subclasses
from comken.exceptions import SalesforceError
from comken.toolbox.salesforce.client import SalesforceBase
from comken.toolbox.salesforce.hosts import host_of
from comken.toolbox.salesforce.sites.solution import Solution
from comken.toolbox.salesforce.sites.solution_sandbox import SolutionSandbox


def _site_not_found_error(url: str, known_domains: list[str]) -> SalesforceError:
    """``SalesforceError`` の「URL のドメインに対応する組織が登録されていない」文言。

    発生箇所: comken.toolbox.salesforce.sites.site_for()
    """
    known = "\n".join(f"  {domain}" for domain in known_domains) or "  （登録なし）"
    return SalesforceError(
        f"この URL の組織が登録されていません: {url}\n"
        f"登録済みの組織:\n{known}\n"
        "レポートを開いたときのアドレスをそのまま貼ってください。\n"
        "新しい組織の場合は、組織クラスの追加が必要です（管理者へ連絡してください）。"
        "\n対処: URL のドメインを見直してください。新しい組織なら管理者へ連絡してください"
        "（組織クラスの追加が要る）。"
    )


# 登録済みの組織。URL からどの組織へつなぐかを引くのに使う。
# ``find_subclasses`` で同フォルダの ``SalesforceBase`` サブクラスを自動収集する
# （モジュール名昇順・決定的）。``DOMAIN_URL`` が空のクラスは土台扱いで除外される。
SITES: tuple[type[SalesforceBase], ...] = find_subclasses(
    sys.modules[__name__], SalesforceBase, include=lambda cls: bool(cls.DOMAIN_URL)
)

__all__ = ["SITES", "Solution", "SolutionSandbox", "site_for"]


def _no_sandbox_error(site: type[SalesforceBase], url: str) -> SalesforceError:
    """``SalesforceError`` の「この組織に対応するサンドボックスが登録されていない」文言。

    発生箇所: comken.toolbox.salesforce.sites.site_for(sandbox=True)
    """
    return SalesforceError(
        f"{site.display_name()} に対応するサンドボックスが登録されていません: {url}\n"
        "対処: 組織クラスの ``SANDBOX_SITE`` にサンドボックスの組織クラスを指定してください"
        "（管理者へ連絡してください）。"
    )


def site_for(url: str, *, sandbox: bool = False) -> type[SalesforceBase]:
    """レポートの URL から、つなぐ組織のクラスを返す。

    レポートの一覧表には**複数の組織の URL が混ざる**。どの組織のレポートかは
    URL のドメイン（My Domain）で決まるので、表に行を足すだけで新しい組織の
    レポートも取れるようにする。組織を人が選ぶ列を作ると、URL と食い違ったときに
    別組織へ問い合わせて「レポートが見つからない」という分かりにくい失敗になる。

        site_for("https://example.my.salesforce.com/lightning/...")
        # → Solution

    ブラウザのアドレスバーの URL（``○○.lightning.force.com``）も、同じ組織として読む。

    ``sandbox=True`` のときは、URL が指す**本番の組織に対応するサンドボックス**を返す
    （管理表は本番の URL だけを持ち、調査などでサンドボックスを見たいとき用）。
    レポート ID は URL から取るので、サンドボックスにも同じ ID のレポートがある前提。
    URL がもともとサンドボックスのものなら、そのまま返す。

        site_for("https://example.my.salesforce.com/lightning/...", sandbox=True)
        # → SolutionSandbox

    Args:
        url: レポートを開いたときのアドレス。**ドメインを含む URL であること**
            （レポート ID だけでは、どの組織のものか決められない）。
        sandbox: ``True`` なら、対応するサンドボックスの組織クラスを返す。

    Raises:
        SalesforceError: 登録済みのどの組織にも当てはまらない場合。
            ``sandbox=True`` で、対応するサンドボックスが登録されていない場合。
    """
    host = host_of(url)
    for site in SITES:
        if host and host_of(site.DOMAIN_URL) == host:
            return _sandbox_of(site, url) if sandbox else site
    raise _site_not_found_error(url, [site.DOMAIN_URL for site in SITES])


def _sandbox_of(site: type[SalesforceBase], url: str) -> type[SalesforceBase]:
    """``site`` に対応するサンドボックスを返す。``site`` 自身がサンドボックスならそのまま返す。"""
    if any(other.SANDBOX_SITE is site for other in SITES):
        return site
    if site.SANDBOX_SITE is None:
        raise _no_sandbox_error(site, url)
    return site.SANDBOX_SITE
