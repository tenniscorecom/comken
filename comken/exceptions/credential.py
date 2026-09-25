"""comken/exceptions/credential.py — 認証情報の暗号化保存に関する例外。"""

from comken.exceptions.base import ComkenError


class CredentialError(ComkenError):
    """認証情報の保存・取得に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class CredentialNotFoundError(CredentialError):
    """認証情報（パスワード・client_secret など）が登録されていない

    発生箇所: comken.toolbox.credentials の load_credential() / Credentials の属性アクセス

    対処:
        表示された登録済みキー名と見比べる。
        無ければ `python -m comken cred import 認証情報.json` で取り込む
    """

    def __init__(self, name: str, registered: list[str]) -> None:
        known = "\n".join(f"  {item}" for item in registered)
        detail = (
            f"登録済みのキー名:\n{known}"
            if registered
            else "まだ1件も登録されていません。次のコマンドで取り込んでください。\n"
            "  python -m comken cred import 認証情報.json"
        )
        super().__init__(f"認証情報が登録されていません: {name}\n{detail}")


class PasswordRejectedError(CredentialError):
    """サイト側が新しいパスワードを拒否した（記号が足りない・文字数が足りない等）

    サイト固有の画面クラス（例: ``ChangePasswordPage.submit_new_password()``）が、
    パスワード送信後にサイト側のエラー表示を検知した場合に送出する。
    ``comken.toolbox.credentials.change_password()`` はこの例外を受け取ると、
    理由を表示して新しいパスワードを CLI で受け付け直す
    （``max_attempts`` に達するまで自動で再試行する）。

    発生箇所: 利用プロジェクト側のパスワード変更画面クラス（サイト固有の実装）

    対処:
        表示されたエラー内容（サイト側の拒否理由）を確認し、要件を満たす
        パスワードを入力し直す
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"サイト側が新しいパスワードを拒否しました: {reason}")
