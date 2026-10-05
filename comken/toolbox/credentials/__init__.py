"""comken/toolbox/credentials/__init__.py — 認証情報の暗号化保存（Windows DPAPI）。

config.ini に平文で書けない値（client_secret・パスワード・トークン）を、
Windows ログオンユーザーに紐付けて暗号化して保管する。

    # 登録（初回だけ。1台なら画面から、何台にも配るなら平文 JSON を用意して取り込む）
    python -m comken cred gui
    python -m comken cred import 認証情報.json

    # 使う側
    from comken.toolbox.credentials import Credentials

    cred = Credentials("site_a")
    cred.client_id      # → site_a 配下の client_id の値
    cred.client_secret  # → site_a 配下の client_secret の値

暗号化・復号は **同じ Windows ユーザー × 同じ PC** でしか成立しない。
タスクスケジューラの実行ユーザーが登録時と違うと復号できないので、
運用アカウントで取り込むこと（最も多い事故）。

    Credentials        サイト名配下の値に属性でアクセスする（cred.field = 値 と
                       cred.save() で更新もできる）
    load_credential    (サイト名, 項目名) を指定して1件取り出す
    save_credential    (サイト名, 項目名) を指定して1件保存する
    save_credentials   まとめて保存する（書き込みは1回）— **内部用**。1件ずつ書く
                       ときは ``save_credential`` を使う
    delete_credential  1件削除する — **内部用**。CLI/ツールの用途
    list_names         登録済みの (サイト名, 項目名) の一覧（値は返さない）— **内部用**
    import_json        平文 JSON を読み込んで取り込む — **内部用**。``python -m comken cred import``
                       の CLI 入口から呼ばれる
    prompt_new_password  新しいパスワードをCLIから2回入力させ、Credentials へ保存する
                        — **内部用**。CLI/ツールの用途
    change_password    prompt_new_password に加え、サイト側への送信・拒否時の
                       自動再試行までを行う（PasswordRejectedError を使う）
                       — **内部用**
    CREDENTIALS_PATH   保存先のパス — **内部用**
"""

from comken.toolbox.credentials.store import Credentials, load_credential, save_credential

__all__ = [
    "Credentials",
    "load_credential",
    "save_credential",
]
