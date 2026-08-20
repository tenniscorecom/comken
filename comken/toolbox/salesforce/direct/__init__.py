r"""comken/toolbox/salesforce/direct/__init__.py — Salesforce direct パッケージ

社内ライブラリ化されていない現時点で comken が **直接** Salesforce API を叩く
実装をここに集約する。`comken.toolbox.salesforce` 直下の `client.py` /
`oauth_credentials.py` / `oauth_refresh.py` / `rotation.py` / `metrics.py` /
`report.py` / `cli.py` を移設済み (2026-08-19)。

公式の社内 Salesforce API ライブラリへ切り替える必要が生じた場合は
``Projects/comken-設計メモ_salesforce-wrap.md`` を参照。
"""
