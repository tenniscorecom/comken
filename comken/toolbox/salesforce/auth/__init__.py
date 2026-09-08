"""comken/toolbox/salesforce/auth/__init__.py — Salesforce の認証・認証情報管理。

以下をまとめている:

    oauth_refresh.py       RefreshTokenOAuth（Authorization Code + Refresh Token Flow、既定）
    rotation.py            SalesforceCredentialRotator（ECA 認証情報の定期ローテーション）

公開 API としての入口は変わらず `comken.toolbox.salesforce`
（`from comken.toolbox.salesforce import RefreshTokenOAuth` 等）。
このパッケージは内部の整理のためのフォルダ分けであり、直接 import する
入口としては使わない。
"""
