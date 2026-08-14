"""comken/exceptions/credential.py — 認証情報の暗号化保存に関する例外。"""

from pathlib import Path

from .base import ComkenError


class CredentialError(ComkenError):
    """認証情報の保存・取得に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class InvalidCredentialNameError(CredentialError):
    """認証情報のキー名に使えない文字がある

    発生箇所: comken.toolbox.credentials の Credentials() / save_credential() / 取り込み

    対処:
        半角英数字とアンダースコアだけにする（漢字・スペース・記号は使えない）
    """

    def __init__(self, label: str, name: str) -> None:
        super().__init__(
            f"{label}に使えない文字が含まれています: {name or '（空）'}\n"
            "使えるのは半角英数字とアンダースコアだけです（例: site_a, site_a_client_secret）。\n"
            "漢字・スペース・記号は使えません。"
        )


class CredentialNotFoundError(CredentialError):
    """認証情報（パスワード・client_secret など）が登録されていない

    発生箇所: comken.toolbox.credentials の load_credential() / Credentials の属性アクセス

    対処:
        表示された登録済みキー名と見比べる。
        無ければ `python -m comken.toolbox.credentials import 認証情報.json` で取り込む
    """

    def __init__(self, name: str, registered: list[str]) -> None:
        known = "\n".join(f"  {item}" for item in registered)
        detail = (
            f"登録済みのキー名:\n{known}"
            if registered
            else "まだ1件も登録されていません。次のコマンドで取り込んでください。\n"
            "  python -m comken.toolbox.credentials import 認証情報.json"
        )
        super().__init__(f"認証情報が登録されていません: {name}\n{detail}")


class CredentialDecryptionError(CredentialError):
    """認証情報を復号できない

    DPAPI は「登録したときの Windows ユーザー × PC」でしか復号できない。
    別のアカウントで実行した・別の PC にファイルをコピーした場合がほとんど。

    発生箇所: comken.toolbox.credentials の読み書き全般

    対処:
        登録したときと**同じ Windows アカウント・同じ PC** で実行しているか確認する。
        タスクスケジューラの実行ユーザー違いが最も多い
    """

    def __init__(self, path: Path, detail: Exception) -> None:
        super().__init__(
            f"認証情報を復号できませんでした: {path}\n"
            f"（{detail}）\n"
            "次を順に確認してください。\n"
            "  1. 登録したときと同じ Windows アカウントで実行しているか\n"
            "     （タスクスケジューラの実行ユーザーが違う、が最も多い原因）\n"
            "  2. 登録したときと同じ PC か（別 PC にコピーしても読めません）\n"
            "  3. どちらも合っている場合はファイルが壊れている。\n"
            "     ファイルを削除して、もう一度取り込み直してください。"
        )


class CredentialStoreCorruptedError(CredentialError):
    """認証情報の中身が壊れている

    復号できない（別ユーザー・別 PC）のとは対処が違う。こちらは実行アカウントを
    直しても直らないので、ファイルを捨てて取り込み直すしかない。

    発生箇所: comken.toolbox.credentials の読み書き全般

    対処:
        実行アカウントの問題ではない。表示されたファイルを削除して、もう一度取り込み直す
    """

    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(
            f"認証情報の中身が壊れています: {path}\n"
            f"（{detail}）\n"
            "復号はできているので、実行アカウントの問題ではありません。\n"
            "このファイルを削除して、もう一度取り込み直してください。\n"
            "  python -m comken.toolbox.credentials import 認証情報.json"
        )


class CredentialImportError(CredentialError):
    """取り込む JSON が壊れている・形式が違う

    発生箇所: comken.toolbox.credentials の import_json()

    対処:
        表示された形式のとおりに書き直す。値は必ず `" "` で囲む
    """

    def __init__(self, path: Path, detail: str) -> None:
        super().__init__(
            f"認証情報の JSON を取り込めませんでした: {path}\n"
            f"{detail}\n"
            "次の形式で書いてください（システム名ごとに項目をまとめる）。\n"
            "{\n"
            '  "site_a": {"client_id": "...", "client_secret": "..."},\n'
            '  "site_b": {"client_id": "...", "client_secret": "..."}\n'
            "}"
        )
