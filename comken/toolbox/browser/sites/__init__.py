r"""comken/toolbox/browser/sites/__init__.py — ライブラリ公認のブラウザ対象サイト。

`SiteBase` を継承したサイトクラスのうち、**複数プロジェクトから共通で参照される
社内システム**をここに置く。プロジェクト側で個別に使うサイトは置かない
（プロジェクト側の `src/sites/` に置く。判断基準は
`docs/開発/ライブラリ開発規約.md` の「サイト／組織クラスを昇格させる基準」を参照）。
サンプルサイト（`sample/`）は書き方の見本であり、社内システムではない。

    from comken.toolbox.browser.sites import SITES    # 公認サイトの一覧
    from comken.toolbox.browser.sites import Kintai  # 個別 import も可

> [!warning] サイト名と URL は仮の値
> **このリポジトリは公開しているので、実際の社内システム名・URL を書かない。**
> 共有サーバーへ配置するときに、各ファイルの実クラス名・`NAME`・`BASE_URL` を
> 実際の値へ書き換える（`comken/toolbox/salesforce/sites/` の `Sandbox` と同じ扱い）。
> 書き換えた値は組織内の配布物に置き、**このリポジトリへ書き戻さないこと。**

昇格の手順:
  1. ライブラリ側へファイルを移す（`comken/toolbox/browser/sites/<サイト名>.py`）
  2. クラス内の `OWNER` を `"comken"` に変える（管理者が既に判断済みの印）
  3. この `SITES` タプルにクラスを追加する
  4. 利用側の import を `from comken.toolbox.browser.sites import <クラス名>` へ書き換える

**移すかどうかはライブラリ管理者が判断する。** プロジェクト側が勝手に
`comken` 配下へファイルを置いても、起動時に「comken 配下のクラスは OWNER = "comken"
にすること」と案内するだけで、自動的に `SITES` には入らない。
"""

from comken.toolbox.browser.sitebase import SiteBase
from comken.toolbox.browser.sites.ntt import NTTHigashi, NTTNishi
from comken.toolbox.browser.sites.sample import SampleSite

# ライブラリ公認サイトの一覧。最初に空で置いておき、昇格するサイトが出てきたら
# ここで追加していく。**プロジェクト側で同じ NAME のクラスを作ると、
# 起動時に `SiteAlreadyInLibraryError` で止まる。**
# SampleSite・NTTNishi・NTTHigashi は URL がダミーのままなので SITES には含めない
# （配置時に実際の値へ書き換えたら登録する）。
SITES: tuple[type[SiteBase], ...] = ()

__all__ = ["SITES", "SampleSite", "NTTNishi", "NTTHigashi"]
