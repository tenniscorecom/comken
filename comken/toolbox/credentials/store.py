"""comken/toolbox/credentials/store.py — 認証情報の暗号化保存（Windows DPAPI）

client_id / client_secret・パスワード・トークンなど、config.ini に平文で書けない値を
Windows ログオンユーザーに紐付けて暗号化し、ユーザープロファイル内に保存する。

キー名1つに値1つを持つ単純な形式にしてある。
「ユーザー名とパスワードが必ずセット」という決め打ちをしないため、
client_id と client_secret だけ・トークンだけ、といった構成にも合わせられる。

仕組み:
    - 暗号化には Windows 標準の DPAPI を使う。暗号鍵を自分で管理する必要がなく、
      Windows がログオン中のアカウントに紐付けて暗号化・復号する
    - 保存先は %USERPROFILE%\\.rpa\\credentials.enc（ユーザーごとに別ファイル）
    - 同じ「ユーザー × PC」でないと復号できないため、ファイルを
      他人にコピーされても中身は読まれない

登録は JSON を取り込む形で行う（comken.toolbox.credentials.importer）:
    python -m comken cred import 認証情報.json

使い方（コード側）:
    from comken.toolbox.credentials import Credentials

    cred = Credentials("site_a")
    cred.client_id      # → site_a_client_id の値
    cred.client_secret  # → site_a_client_secret の値

    # 1件だけ取り出す場合
    from comken.toolbox.credentials import load_credential
    password = load_credential("oju_sys_password")
"""

import json
import re
import uuid
from pathlib import Path

import pywintypes
import win32crypt

from comken.core.files.ops import cleanup_stale_tmp
from comken.core.timer import measure
from comken.exceptions import (
    CredentialDecryptionError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)

# パッケージ名と関係なく、固定の保存先フォルダ名を使う。
# 旧パッケージ名（comken）で保存していたデータを引き継ぐため、
# パッケージリネームを契機に保存先を変えない。
CREDENTIALS_PATH = Path.home() / ".rpa" / "credentials.enc"

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
        # 初回の属性アクセスで復号結果を丸ごと持っておく。 詳しくは __getattr__ の
        # コメント参照（秘密情報の保持期間・save/delete 後の扱いもそこに書いた）。
        self._cache: dict[str, str] | None = None

    def __getattr__(self, item: str) -> str:
        # _ 始まりは Python 内部の属性探索（copy 等）なので通常の AttributeError にする
        if item.startswith("_"):
            raise AttributeError(item)
        data = self._decrypted()
        key = f"{self._prefix}_{item}"
        if key not in data:
            # 元の ``load_credential()`` と同じ例外型・同じメッセージにする。
            # 「登録済みのキー名」を添える仕様は ``load_credential`` 側にあるので
            # ここでも再現する（``CredentialNotFoundError(name, sorted(data))``）
            raise CredentialNotFoundError(key, sorted(data))
        return data[key]

    def _decrypted(self) -> dict[str, str]:
        """**復号結果を 1 度だけ呼んで保持する**内部キャッシュ。

        設計判断（コメントに書いた判断のサマリ）:

        - 1 件ずつ ``load_credential()`` を呼ぶと、 属性 N 個ぶん **N 回の
          DPAPI 復号 + JSON parse + ファイル読込**が走る。 リストを索引化
          する業務フロー（``for row in cred.df: cred.lookup[row]`` のような
          書き方）で特に効くため、 初回アクセス時に**ファイル全件を 1 度だけ**
          復号してインスタンスに保持する。

        - **秘密情報のメモリ保持期間が延びる**点について: 今までは
          ``load_credential()`` が返す時点で ``str`` のオブジェクトだけが
          ヒープに残っていた（呼び出し側の変数が参照する間）。 修正後は
          **同じ ``str`` が ``self._cache`` の中にも残る**。 これが問題になる
          のは、 プロセスが生きている間に:
              - 攻撃者がプロセスメモリをダンプできる（DPAPI の意味が既に無い）
              - 攻撃者がこの特定インスタンスを狙って参照を漁れる
          のいずれかであり、 業務プロセスではどちらも通常は無い。 むしろ
          ``load_credential()`` が **呼び出すたびにファイルを全部読む**ほうが、
          共有サーバー上で I/O を増やして業務影響を及ぼすリスクが高いため、
          **キャッシュを優先**する判断を取る。

        - **``save_credential`` / ``delete_credential`` で内容が変わったとき**:
          同じ ``Credentials`` インスタンスが古い値を返さないように、
          両関数とも ``_invalidate_instances_for(path)`` を呼び、 同じパスに
          紐付くインスタンスの ``_cache`` を ``None`` に戻す。 次の属性
          アクセスで再復号される。

          インスタンス単位のキャッシュにしているのは、 「同じプロセスで
          複数 Credentials を持ち、 一部の prefix の保存は他と独立」という
          ケースで **関係ない prefix まで巻き込んで破棄しない**ため。 それでも
          「同じパスの保存後に古い値が残る」事故は避けられる。
        """
        cached = self.__dict__.get("_cache")
        if cached is not None:
            return cached
        data = _load_all(self._path or CREDENTIALS_PATH)
        object.__setattr__(self, "_cache", data)
        _register_instance(self)
        return data


@measure
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


@measure
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
    # 保存後は同じパスを参照する ``Credentials`` インスタンスの復号キャッシュが
    # 古くなるので、 次回の属性アクセスで再復号されるよう ``_cache`` を捨てる
    # （詳細は ``Credentials._decrypted`` のコメント）
    _invalidate_instances_for(path)


@measure
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


@measure
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
    # 削除後はキャッシュが古くなるので破棄。 詳細は ``Credentials._decrypted``
    _invalidate_instances_for(path)


@measure
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
    cleanup_stale_tmp(path)  # 前回クラッシュ時の .tmp 残骸を掃除
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(raw, _FILE_DESCRIPTION, None, None, None, 0)
    # 同時に走っても衝突しないよう、一時ファイル名は毎回変える
    tmp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_bytes(encrypted)
        tmp_path.replace(path)  # 同じフォルダ内の置き換えなのでアトミックに入れ替わる
    finally:
        tmp_path.unlink(missing_ok=True)  # 途中で失敗したときに残骸を残さない


# ── ``Credentials`` のインスタンス単位キャッシュ用レジストリ ───────────────
# ``Credentials`` はファイル全件を ``_cache`` に持つようにしたため（設計理由は
# ``Credentials._decrypted`` のコメント参照）、同じパスを対象とする保存 / 削除が
# 起きたあとに**古い値を抱えたままのインスタンス**が残る事故が起きる。 そこで:
#
# 1. ``_decrypted()`` で読み込んだタイミングで ``_register_instance(self)`` を
#    呼んで ``_instances_by_path`` に「このパスを使ったインスタンス」を覚える
# 2. ``save_credentials`` / ``delete_credential`` のあとで
#    ``_invalidate_instances_for(path)`` を呼び、 同じパスに紐付くインスタンスの
#    ``_cache`` を ``None`` に戻す（次回アクセスで再復号される）
#
# インスタンスへの弱参照は使わずそのまま覚える（``Credentials`` の寿命 ≒ プロセス
# 寿命なのでリークしない）。 テスト時は ``_reset_instance_registry()`` で破棄する。
_instances_by_path: dict[str, list[Credentials]] = {}


def _register_instance(instance: "Credentials") -> None:
    """``Credentials._decrypted()`` から呼ばれ、 ``path`` ごとにインスタンスを覚える。

    既に登録済みのインスタンスは二重登録しない（GC で消えた弱参照は持たない）。
    """
    key = str(instance._path or CREDENTIALS_PATH)
    bucket = _instances_by_path.setdefault(key, [])
    # 「同じインスタンスを二重で持たない」だけ確認（弱参照の代替として十分）
    if instance not in bucket:
        bucket.append(instance)


def _invalidate_instances_for(path: Path) -> None:
    """指定パスを使う全 ``Credentials`` インスタンスのキャッシュを破棄する。

    ``save_credentials`` / ``delete_credential`` から呼ばれる。 該当の
    インスタンスが保持している復号結果（``_cache``）は古くなっているはずなので、
    ``None`` に戻して次回 ``__getattr__`` で再復号させる。
    """
    key = str(path)
    for instance in _instances_by_path.get(key, ()):
        if instance.__dict__.get("_cache") is not None:
            object.__setattr__(instance, "_cache", None)


def _reset_instance_registry() -> None:
    """**インスタンスレジストリを空にする**（テスト用）。

    テストでは複数の ``tmp_path`` を使い回すので、 前のテストで登録された
    インスタンスが残っていると、 保存系のテストで「別パスの Credentials が
    巻き添えで破棄される」事故が起きうる。 各テストの前後で破棄する想定。
    利用者向けの公開 API ではない。
    """
    _instances_by_path.clear()
