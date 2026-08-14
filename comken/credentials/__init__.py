"""comken/credentials/__init__.py — 認証情報の暗号化保存（Windows DPAPI）。

config.ini に平文で書けない値（client_secret・パスワード・トークン）を、
Windows ログオンユーザーに紐付けて暗号化して保管する。

    # 取り込み（初回だけ。平文 JSON を用意して1回実行する）
    python -m comken.credentials import 認証情報.json

    # 使う側
    from comken.credentials import Credentials

    cred = Credentials("site_a")
    cred.client_id      # → site_a_client_id の値
    cred.client_secret  # → site_a_client_secret の値

暗号化・復号は **同じ Windows ユーザー × 同じ PC** でしか成立しない。
タスクスケジューラの実行ユーザーが登録時と違うと復号できないので、
運用アカウントで取り込むこと（最も多い事故）。

    Credentials        システム名配下の値に属性でアクセスする
    load_credential    キー名を指定して1件取り出す
    save_credential    キー名を指定して1件保存する
    save_credentials   まとめて保存する（書き込みは1回）
    delete_credential  1件削除する
    list_names         登録済みのキー名一覧（値は返さない）
    import_json        平文 JSON を読み込んで取り込む
    CREDENTIALS_PATH   保存先のパス
"""

from __future__ import annotations

from .importer import import_json
from .store import (
    CREDENTIALS_PATH,
    Credentials,
    delete_credential,
    list_names,
    load_credential,
    save_credential,
    save_credentials,
)

__all__ = [
    "CREDENTIALS_PATH",
    "Credentials",
    "load_credential",
    "save_credential",
    "save_credentials",
    "delete_credential",
    "list_names",
    "import_json",
]
