"""comken/toolbox/browser/sites/salesforce/__init__.py — Salesforceのブラウザ経由ダウンロード。

comken.toolbox.salesforce（API版）の Reports and Dashboards REST API は2000行が
上限のため（詳しくは docs/機能/salesforce.md）、それを超えるレポートは画面のエクスポート
機能をブラウザ経由で叩いて取るしかない。ここはその手段を提供する。

``SalesforceReportBrowser`` は雛形（``BASE_URL`` がダミー）なので、実際の組織別の値
（URL・認証情報名）は ``Solution`` / ``SolutionSandbox`` が API 側の組織クラス
（``comken.toolbox.salesforce.sites``）の ``DOMAIN_URL`` / ``CREDENTIAL_PREFIX``
をそのまま使う（同じ URL を二重に書かない）。

    from comken.toolbox.browser.sites.salesforce import site_for

    site_class = site_for(report_url)
    with site_class() as sf:
        sf.login_with_credentials()  # prefix省略 → CREDENTIAL_PREFIX / MFA承認は人が行う
        for report_id, path in sf.export_reports(reports):
            print(report_id, path)

組織を増やすときは、このフォルダに ``SalesforceReportBrowser`` を継承したファイルを
1つ足す。**`BASE_URL` または `NAME` を空のままにしない**（空だと土台クラス扱いで
登録されない）。ファイル名が `_` で始まるものは無視される（雛形置き場）。

> [!note] クラス名は API 側と同名
> ``Solution`` / ``SolutionSandbox`` は API 側
> （``comken.toolbox.salesforce.sites.Solution`` /
> ``comken.toolbox.salesforce.sites.SolutionSandbox``）と**同名**。
> ``comken.toolbox.browser.sites.salesforce`` と ``comken.toolbox.salesforce.sites``
> のパッケージで区別する。``site_for`` は API 側と同名で、判定方法も同じ
>（URL のドメイン一致）。
"""

from __future__ import annotations

import sys

from comken.core.discovery import find_subclasses
from comken.exceptions import SalesforceError
from comken.toolbox.browser.sites.salesforce.base import SalesforceReportBrowser
from comken.toolbox.browser.sites.salesforce.solution import Solution
from comken.toolbox.browser.sites.salesforce.solution_sandbox import SolutionSandbox
from comken.toolbox.salesforce.hosts import host_of


def _site_not_found_error(url: str, known_domains: list[str]) -> SalesforceError:
    """``SalesforceError`` の「URL のドメインに対応する組織が登録されていない」文言。

    発生箇所: comken.toolbox.browser.sites.salesforce.site_for()
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
# ``find_subclasses`` で同フォルダの ``SalesforceReportBrowser`` サブクラスを
# 自動収集する（モジュール名昇順・決定的）。
# ``BASE_URL`` または ``NAME`` を空のままにすると土台クラス扱いで除外される。
SITES: tuple[type[SalesforceReportBrowser], ...] = find_subclasses(
    sys.modules[__name__],
    SalesforceReportBrowser,
    include=lambda cls: bool(cls.BASE_URL) or bool(cls.NAME),
)

__all__ = [
    "SalesforceReportBrowser",
    "Solution",
    "SolutionSandbox",
    "SITES",
    "site_for",
]


def _no_sandbox_error(site: type[SalesforceReportBrowser], url: str) -> SalesforceError:
    """``SalesforceError`` の「この組織に対応するサンドボックスが登録されていない」文言。

    発生箇所: comken.toolbox.browser.sites.salesforce.site_for(sandbox=True)
    """
    return SalesforceError(
        f"{site.__name__} に対応するサンドボックスが登録されていません: {url}\n"
        "対処: 組織クラスの ``SANDBOX_SITE`` にサンドボックスの組織クラスを指定してください"
        "（管理者へ連絡してください）。"
    )


def site_for(url: str, *, sandbox: bool = False) -> type[SalesforceReportBrowser]:
    """レポートのURLから、ブラウザ経由でつなぐ組織のクラスを返す。

        site_for("https://example.my.salesforce.com/lightning/...")
        # → Solution

    ブラウザのアドレスバーの URL（``○○.lightning.force.com``）も、同じ組織として読む。
    ``sandbox=True`` のときは、URL が指す本番の組織に対応するサンドボックスを返す
    （URL がもともとサンドボックスのものなら、そのまま返す）。API 側の
    ``comken.toolbox.salesforce.sites.site_for`` と同じ規則。

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
        if host and host_of(site.BASE_URL) == host:
            return _sandbox_of(site, url) if sandbox else site
    raise _site_not_found_error(url, [site.BASE_URL for site in SITES])


def _sandbox_of(site: type[SalesforceReportBrowser], url: str) -> type[SalesforceReportBrowser]:
    """``site`` に対応するサンドボックスを返す。``site`` 自身がサンドボックスならそのまま返す。"""
    if any(other.SANDBOX_SITE is site for other in SITES):
        return site
    if site.SANDBOX_SITE is None:
        raise _no_sandbox_error(site, url)
    return site.SANDBOX_SITE
