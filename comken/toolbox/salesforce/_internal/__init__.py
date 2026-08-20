"""comken/toolbox/salesforce/_internal/__init__.py — 社内ライブラリ版 SiteBase Adapter (future)。

`Projects/comken-設計メモ_salesforce-wrap.md` のラップ後構造案でいう
"internal" 層。**利用者からは見えないよう private 接頭辞 (`_`) を
付けた**。将来 `InternalSiteBase` を実装するときも、ここに置く。

現状は空の枠だけ。`from comken.toolbox.salesforce import SiteBase` 経由では
`DirectSiteBase` が選ばれる (組織クラスの継承元が `DirectSiteBase` のため)。
"""
