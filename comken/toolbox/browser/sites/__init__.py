"""comken/toolbox/browser/sites/__init__.py — ライブラリ公認のブラウザ対象サイト。

`SiteBase` を継承したサイトクラスのうち、**複数プロジェクトから共通で参照される
社内システム**をここに置く。プロジェクト側で個別に使うサイトは置かない
（プロジェクト側の `src/sites/` に置く。判断基準は
`docs/CONVENTIONS.md` の「サイト／組織クラスを昇格させる基準」を参照）。
書き方の見本は `ntt/` を参照（NTT西・NTT東 の 2 サイトを 1 フォルダで束ねる
例外形。姉妹サイトを持たない単独サイト用の 1 サイト＝1 フォルダ形の解説は
`docs/機能/browser.md` を正本とする）。

    from comken.toolbox.browser.sites import SITES    # 公認サイトの一覧
    from comken.toolbox.browser.sites import Kintai  # 個別 import も可

> [!warning] サイト名と URL は仮の値
> **このリポジトリは公開しているので、実際の社内システム名・URL を書かない。**
> 共有サーバーへ配置するときに、各ファイルの実クラス名・`NAME`・`BASE_URL` を
> 実際の値へ書き換える（`comken/toolbox/salesforce/sites/` の `Solution` と同じ扱い）。
> 書き換えた値は組織内の配布物に置き、**このリポジトリへ書き戻さないこと。**

**登録は自動**: ファイルを置けば `find_subclasses()` が拾って `SITES` へ加える。
**`NAME` を空のままにしない**（空だと土台クラス扱いで登録されない）。
ファイル・フォルダ名が `_` で始まるものは無視される（雛形置き場）。
クラスは**同じ `NAME` で 1 つだけ**にすること — `SiteBase._check_not_in_library()`
がプロジェクト側との衝突を起動時に `BrowserError` で止める。
"""

from __future__ import annotations

import sys

from comken.core.discovery import find_subclasses
from comken.toolbox.browser.sitebase import SiteBase
from comken.toolbox.browser.sites.ntt import NTTEast, NTTWest
from comken.toolbox.browser.sites.salesforce.base import SalesforceReportBrowser

# ライブラリ公認サイトの一覧。``find_subclasses`` で配下のサブパッケージから
# ``SiteBase`` サブクラスを自動収集する（モジュール名昇順・決定的）。
# ``NAME`` が空のクラス（NTTSiteBase などの土台）と、``SalesforceReportBrowser``
# （NAME を持つが組織ごとのクラスの土台で、公認サイトではない）は除外される。
# プロジェクト側で同じ ``NAME`` のクラスを定義すると、起動時に
# ``SiteBase._check_not_in_library()`` が ``BrowserError`` で止める。
SITES: tuple[type[SiteBase], ...] = find_subclasses(
    sys.modules[__name__],
    SiteBase,
    include=lambda cls: bool(cls.NAME) and cls is not SalesforceReportBrowser,
)

__all__ = ["SITES", "NTTWest", "NTTEast"]
