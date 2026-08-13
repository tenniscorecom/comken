"""
credentials/store.py — 認証情報の暗号化保存（Windows DPAPI）

client_id / client_secret・パスワード・トークンなど、config.ini に平文で書けない値を
Windows ログオンユーザーに紐付けて暗号化し、ユーザープロファイル内に保存する。

キー名1つに値1つを持つ単純な形式にしてある。
「ユーザー名とパスワードが必ずセット」という決め打ちをしないため、
client_id と client_secret だけ・トークンだけ、といった構成にも合わせられる。

仕組み:
    - 暗号化には Windows 標準の DPAPI を使う。暗号鍵を自分で管理する必要がなく、
      Windows がログオン中のアカウントに紐付けて暗号化・復号する
    - 保存先は %USERPROFILE%\\.comken\\credentials.dat（ユーザーごとに別ファイル）
    - 同じ「ユーザー × PC」でないと復号できないため、ファイルを
      他人にコピーされても中身は読まれない

登録は JSON を取り込む形で行う（comken.credentials.importer）:
    python -m comken.credentials import 認証情報.json

使い方（コード側）:
    from comken.credentials import Credentials

    cred = Credentials("site_a")
    cred.client_id      # → site_a_client_id の値
    cred.client_secret  # → site_a_client_secret の値

    # 1件だけ取り出す場合
    from comken.credentials import load_credential
    password = load_credential("oju_sys_password")
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

import pywintypes
import win32crypt

from ..exceptions import (
    CredentialDecryptionError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)
from ..utils.files.ops import _cleanup_stale_tmp

# 保存先フォルダ名はパッケージ名に自動追従する（パッケージ名を変更しても書き換え不要）
_PACKAGE_NAME = __package__.split(".")[0]

CREDENTIALS_PATH = Path.home() / f".{_PACKAGE_NAME}" / "credentials.dat"

# キー名に使える文字（半角英数字とアンダースコアのみ）
# 漢字・スペース・記号はコードや config.ini に書きにくいため弾く
CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

# 復号失敗時に DPAPI が返す説明文字列（デバッグ用。動作には影響しない）
_FILE_DESCRIPTION = "comken credentials"


class Credentials:
    """システム名配下の認証情報に、属性アクセスでまとめてアクセスする。

    キー名「システム名_項目名」のシステム名部分だけを指定し、項目名は属性で取り出す。
    システム名を config.ini から渡せば、本番用・テスト用アカウントの切り替えが
    config.ini の1行だけで済む（コード側にキー名の直書きが残らない）。

    使い方:
        cred = Credentials("site_a")
        cred.client_id      # → load_credential("site_a_client_id") と同じ
        cred.client_secret  # → load_credential("site_a_client_secret") と同じ

        # config.ini で本番・テストを切り替える場合
        # [CREDENTIALS]
        # SITE_A = site_a          ← site_a_test にすると全項目が切り替わる
        cred = Credentials(config.CREDENTIALS.SITE_A)

    Raises:
        InvalidCredentialNameError: システム名に使えない文字が含まれている場合。
        CredentialNotFoundError: 属性に対応するキーが未登録の場合。
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """

    def __init__(self, prefix: str, path: Path | None = None) -> None:
        """
        Args:
            prefix: キー名のシステム名部分（例: "site_a", "site_a_test"）。
            path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。
        """
        if not CREDENTIAL_NAME_PATTERN.fullmatch(prefix):
            raise InvalidCredentialNameError("システム名", prefix)
        self._prefix = prefix
        self._path = path

    def __getattr__(self, item: str) -> str:
        # _ 始まりは Python 内部の属性探索（copy 等）なので通常の AttributeError にする
        if item.startswith("_"):
            raise AttributeError(item)
        return load_credential(f"{self._prefix}_{item}", self._path)


def save_credential(name: str, value: str, path: Path | None = None) -> None:
    """認証情報を1件、暗号化して保存する。同じキー名は上書きされる。

    Args:
        name: キー名（例: "site_a_client_secret"）。取得時のキーになる。
            半角英数字とアンダースコアのみ使用できる。
        value: 保存する値（client_secret・パスワード・トークンなど）。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        InvalidCredentialNameError: キー名に使えない文字が含まれている場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    save_credentials({name: value}, path)


def save_credentials(items: dict[str, str], path: Path | None = None) -> None:
    """認証情報をまとめて暗号化して保存する。同じキー名は上書きされる。

    1件ずつ save_credential() を呼ぶと、件数ぶん復号と暗号化を繰り返し、
    途中で失敗すると一部だけ入った状態になる。まとめて渡せば書き込みは1回で、
    「全部入るか、1つも入らないか」のどちらかになる。

    Args:
        items: キー名と値の対応（例: {"site_a_client_id": "..."}）。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        InvalidCredentialNameError: キー名に使えない文字が含まれている場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
        TypeError: 値が文字列でない場合（呼び出し側のバグ）。
    """
    for name, value in items.items():
        if not CREDENTIAL_NAME_PATTERN.fullmatch(name):
            raise InvalidCredentialNameError("キー名", name)
        if not isinstance(value, str):
            raise TypeError(
                f"認証情報の値は文字列で渡してください: {name} は {type(value).__name__}"
            )
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    data.update(items)
    _save_all(data, path)


def load_credential(name: str, path: Path | None = None) -> str:
    """保存済みの認証情報を復号して返す。

    Args:
        name: 登録時に指定したキー名。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        CredentialNotFoundError: キー名が未登録の場合。
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    if name not in data:
        raise CredentialNotFoundError(name, sorted(data))
    return data[name]


def delete_credential(name: str, path: Path | None = None) -> None:
    """登録済みの認証情報を1件削除する。

    Raises:
        CredentialNotFoundError: キー名が未登録の場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    if name not in data:
        raise CredentialNotFoundError(name, sorted(data))
    del data[name]
    _save_all(data, path)


def list_names(path: Path | None = None) -> list[str]:
    """登録済みのキー名一覧を返す（値そのものは返さない）。

    Raises:
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """
    path = path or CREDENTIALS_PATH
    return sorted(_load_all(path))


def _load_all(path: Path) -> dict[str, str]:
    """暗号化ファイルを復号して全キーの辞書を返す。未作成なら空辞書。

    「復号できない」と「復号はできたが中身が壊れている」は対処が違うので、
    別の例外に分ける（前者は実行アカウントの問題、後者は取り込み直し）。
    """
    if not path.exists():
        return {}
    encrypted = path.read_bytes()
    try:
        _, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    except pywintypes.error as e:
        # 原因（別ユーザー・別 PC・暗号文の破損）を DPAPI は区別して返さないので、
        # 確認する順番を示した1つの例外にまとめる
        raise CredentialDecryptionError(path, e) from e

    try:
        data = json.loads(decrypted.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CredentialStoreCorruptedError(path, str(e)) from e
    if not isinstance(data, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in data.items()
    ):
        raise CredentialStoreCorruptedError(path, "キーと値がすべて文字列の形になっていません。")
    return data


def _save_all(data: dict[str, str], path: Path) -> None:
    """全キーの辞書を暗号化してファイルに書き込む。

    一時ファイル経由でアトミックに置き換える。書き込み中にクラッシュしても、
    暗号化ファイルが半端に壊れて全キーが読めなくなることはない。

    ただし**書き手が1つであることが前提**。読んで足して書き戻す流れなので、
    2つのプロセスが同時に書くと後から書いたほうが勝ち、片方の追加が消える。
    取り込みは人が1回だけ実行する運用なので、ロックは持たせていない。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    _cleanup_stale_tmp(path)  # 前回クラッシュ時の .tmp 残骸を掃除
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(raw, _FILE_DESCRIPTION, None, None, None, 0)
    # 同時に走っても衝突しないよう、一時ファイル名は毎回変える
    tmp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(encrypted)
        tmp_path.replace(path)  # 同じフォルダ内の置き換えなのでアトミックに入れ替わる
    finally:
        tmp_path.unlink(missing_ok=True)  # 途中で失敗したときに残骸を残さない
