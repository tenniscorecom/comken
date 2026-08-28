"""comken/toolbox/browser/sites/ntt/base.py — NTT西/NTT東 に共通の SiteBase。

※ URL はダミー。配置するときに実際の値へ書き換える（詳細は sites/__init__.py）。

**このフォルダだけ、docs/browser.md の「1サイト＝1フォルダで完結」を意図的に破る。**
NTT西・NTT東はログイン画面・共通操作がほぼ同一の姉妹サイトのため、Salesforce の
`comken.toolbox.salesforce.client.SalesforceBase`（1組織用の共通ロジックを1か所に
まとめ、組織ごとのクラスは差分だけを持つ）と同じ考え方を踏襲する。片方の実装を
直したら両方に効く代わりに、「1フォルダ消せば1サイト消える」保証は失われる
（サイトを1つ削除するときはこのフォルダの共通部分に他方への依存が残っていないか
確認すること）。
"""

from comken.toolbox.browser import BrowserOptions, SiteBase
from comken.toolbox.browser.sites.ntt.pages.login_page import LoginPage


class NTTBrowserOptions(BrowserOptions):
    """NTT西・NTT東で共通のブラウザオプション。

    デフォルト（BrowserOptions）から変更したいものだけ上書きする。
    サイトごとに変えたい項目が出てきたら、そのサイトのファイルで
    ``NTTBrowserOptions`` を継承したサブクラスを作って ``OPTIONS`` を差し替える。
    """


class NTTSiteBase(SiteBase):
    """NTT西・NTT東に共通のサイト操作（ログイン画面を開く、等）。

    NAME / BASE_URL はサブクラス（nishi.py / higashi.py）で必ず上書きする。
    """

    OPTIONS = NTTBrowserOptions
    # comken 配下のサイトクラスは、管理者が昇格を判断した印として OWNER = "comken" を書く
    OWNER = "comken"

    def go_login(self) -> LoginPage:
        """ログイン画面を開く。"""
        return self.to(LoginPage).go("/login")
