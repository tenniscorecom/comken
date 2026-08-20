"""comken/toolbox/salesforce/internal/__init__.py — 社内ライブラリ版 SiteBase Adapter (future)。

`Projects/comken-設計メモ_salesforce-wrap.md` のラップ後構造案でいう
"internal/" パッケージ。社内 Salesforce API ライブラリへ切り替えるときの
`InternalSiteBase` を入れる予定。

現状は空の枠だけ。`from comken.toolbox.salesforce import SiteBase` 経由では
`DirectSiteBase` が選ばれる (組織クラスの継承元が `DirectSiteBase` のため)。
"""
