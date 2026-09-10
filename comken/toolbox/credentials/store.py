"""comken/toolbox/credentials/store.py — 認証情報の暗号化保存（Windows DPAPI）

client_id / client_secret・パスワード・トークンなど、config.ini に平文で書けない値を
Windows ログオンユーザーに紐付けて暗号化し、ユーザープロファイル内に保存する。

**保存形式は ``{サイト名: {項目名: 値}}`` の入れ子 JSON。**
フラットな ``"{site}_{field}"`` 文字列キーで保管していた時期があったが、
``last_rotation_date`` のように**項目名が3単語以上になる**とサイト名との
境界が文字列処理だけでは一意に決まらなかったため、（サイト名, 項目名）の
組のまま保管する形に変えた。復元時の曖昧さが構造的に消えるので、
「``solution_last_rotation_date`` を「``solution`` / ``last_rotation_date``」
として扱う」といった誤動作が起きなくなる。

仕組み:
    - 暗号化には Windows 標準の DPAPI を使う。暗号鍵を自分で管理する必要がなく、
      Windows がログオン中のアカウントに紐付けて暗号化・復号する
    - 保存先は %USERPROFILE%\\.rpa\\system-id.enc（ユーザーごとに別ファイル）
    - 同じ「ユーザー × PC」でないと復号できないため、ファイルを
      他人にコピーされても中身は読まれない

登録は JSON を取り込む形で行う（comken.toolbox.credentials.importer）:
    python -m comken cred import 認証情報.json

使い方（コード側）:
    from comken.toolbox.credentials import Credentials

    cred = Credentials("site_a")
    cred.client_id      # → load_credential("site_a", "client_id") と同じ
    cred.client_secret  # → load_credential("site_a", "client_secret") と同じ

    # 1件だけ取り出す場合
    from comken.toolbox.credentials import load_credential
    password = load_credential("oju_sys", "password")
"""

import json
import logging
import re
import weakref
from pathlib import Path

import pywintypes
import win32crypt

from comken.core.files.atomic import atomic_write
from comken.core.files.ops import cleanup_stale_tmp
from comken.core.timer import measure
from comken.exceptions import (
    CredentialDecryptionError,
    CredentialNotFoundError,
    CredentialStoreCorruptedError,
    InvalidCredentialNameError,
)

logger = logging.getLogger(__name__)

# パッケージ名と関係なく、固定の保存先フォルダ名を使う。
# ファイル名は社内の命名規則により system-id.enc に統一する（2026-09-02）。
CREDENTIALS_PATH = Path.home() / ".rpa" / "system-id.enc"

# サイト名・項目名に使える文字（半角英数字とアンダースコアのみ）
# 漢字・スペース・記号はコードや config.ini に書きにくいため弾く
CREDENTIAL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")

# CredentialNotFoundError の表示用に、サイト名と項目名を組み合わせる区切り。
# ファイル名や JSON キーに使うわけではないので、人が見て区切りが分かれば何でもよい。
# ``.`` を選んだのは「キー名全体」ではなく「サイト.項目」のスコープ感が伝わるため。
_DISPLAY_NAME_SEPARATOR = "."

# 復号失敗時に DPAPI が返す説明文字列（デバッグ用。動作には影響しない）
_FILE_DESCRIPTION = "comken credentials"


class Credentials:
    """サイト名配下の認証情報に、属性アクセスでまとめてアクセスする。

    入れ子の ``{サイト名: {項目名: 値}}`` から、指定されたサイト名の部分 dict を
    取り出し、項目名を属性アクセスで解決する。サイト名を config.ini から渡せば、
    本番用・テスト用アカウントの切り替えが config.ini の1行だけで済む
    （コード側に長いキー名の直書きが残らない）。

    使い方:
        cred = Credentials("site_a")
        cred.client_id      # → load_credential("site_a", "client_id") と同じ
        cred.client_secret  # → load_credential("site_a", "client_secret") と同じ

        # config.ini で本番・テストを切り替える場合
        # [CREDENTIALS]
        # SITE_A = site_a          ← site_a_test にすると全項目が切り替わる
        cred = Credentials(config.CREDENTIALS.SITE_A)

    Raises:
        InvalidCredentialNameError: サイト名に使えない文字が含まれている場合。
        CredentialNotFoundError: 属性に対応するキーが未登録の場合。
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """

    def __init__(self, site: str, path: Path | None = None) -> None:
        """
        Args:
            site: 認証情報のサイト名（例: "site_a", "site_a_test"）。
            path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。
        """
        if not CREDENTIAL_NAME_PATTERN.fullmatch(site):
            raise InvalidCredentialNameError("サイト名", site)
        self._site = site
        self._path = path
        # 初回の属性アクセスで復号結果を丸ごと持っておく。 詳しくは __getattr__ の
        # コメント参照（秘密情報の保持期間・save/delete 後の扱いもそこに書いた）。
        self._cache: dict[str, dict[str, str]] | None = None
        logger.debug("Credentials を生成: site=%s, path=%s", site, path or CREDENTIALS_PATH)

    def __getattr__(self, item: str) -> str:
        # _ 始まりは Python 内部の属性探索（copy 等）なので通常の AttributeError にする
        if item.startswith("_"):
            raise AttributeError(item)
        site_dict = self._site_dict()
        if item not in site_dict:
            # 元の ``load_credential()`` と同じ例外型・同じメッセージにする。
            # 「登録済みのキー名」を添える仕様は ``load_credential`` 側にあるので
            # ここでも再現する（``CredentialNotFoundError(name, registered)``）。
            # 名前は ``{サイト名}.{項目名}`` の形で表示する（フラットキーの再合成は
            # やめ、 入れ子の構造をそのまま見せる）。
            name = f"{self._site}{_DISPLAY_NAME_SEPARATOR}{item}"
            registered = sorted(
                f"{site}{_DISPLAY_NAME_SEPARATOR}{field}"
                for site, fields in self._decrypted().items()
                for field in fields
            )
            logger.debug(
                "Credentials の属性取得に失敗（未登録）: site=%s, field=%s",
                self._site,
                item,
            )
            raise CredentialNotFoundError(name, registered)
        logger.debug("Credentials の属性を取得: site=%s, field=%s", self._site, item)
        return site_dict[item]

    def save(self, field: str, value: str) -> None:
        """このインスタンスと同じ site（コンストラクタに渡したもの）へ1件保存する。

        site 名をもう一度書かせないための入口。 read（属性アクセス）と write を
        別々に site を書いて揃える設計だと、 typo や参照元の食い違い（config.ini
        経由の site 名と、 全く別の識別子を書き間違える等）で site がずれても
        気づけず、 別サイトとして保存されてしまう。 同じ Credentials インスタンスの
        read/write が必ず同じ site を指すよう、 こちらを使う。

            cred = Credentials(config.CREDENTIALS.AMS)
            new_password = prompt_new_password()
            change_password_page.submit_new_password(new_password)
            cred.save("password", new_password)   # cred と同じ site へ書く

        site 名をまだ Credentials として持っていない・呼び出しのたびに別の site へ
        書きたい場合（Salesforce の refresh_token 書き戻し等）は
        ``save_credential()`` を直接使う。

        保存後は、 同じ path を使う他の Credentials インスタンスの復号キャッシュも
        含めて自動で破棄される（``save_credential()`` 自体が行うため、 ここでは
        何もしない）。 次の属性アクセスで再復号される。
        """
        save_credential(self._site, field, value, self._path)

    def _site_dict(self) -> dict[str, str]:
        """このサイト名の項目 dict を返す。初回アクセスでファイル全体を復号して保持する。"""
        decrypted = self._decrypted()
        return decrypted.get(self._site, {})

    def _decrypted(self) -> dict[str, dict[str, str]]:
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
            logger.debug("復号キャッシュを使用: site=%s, 件数=%d", self._site, len(cached))
            return cached
        target_path = self._path or CREDENTIALS_PATH
        logger.debug("復号キャッシュ未確立のため復号を実行: path=%s", target_path)
        data = _load_all(target_path)
        object.__setattr__(self, "_cache", data)
        _register_instance(self)
        logger.debug("復号キャッシュを保持: site=%s, 件数=%d", self._site, len(data))
        return data


@measure
def save_credential(site: str, field: str, value: str, path: Path | None = None) -> None:
    """認証情報を1件、暗号化して保存する。同じ（サイト, 項目）は上書きされる。

    Args:
        site: サイト名（例: "site_a"）。半角英数字とアンダースコアのみ。
        field: 項目名（例: "client_secret"）。半角英数字とアンダースコアのみ。
        value: 保存する値（client_secret・パスワード・トークンなど）。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        InvalidCredentialNameError: サイト名・項目名に使えない文字が含まれている場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    save_credentials({site: {field: value}}, path)


@measure
def save_credentials(items: dict[str, dict[str, str]], path: Path | None = None) -> None:
    """認証情報をまとめて暗号化して保存する。同じ（サイト, 項目）は上書きされる。

    1件ずつ save_credential() を呼ぶと、件数ぶん復号と暗号化を繰り返し、
    途中で失敗すると一部だけ入った状態になる。まとめて渡せば書き込みは1回で、
    「全部入るか、1つも入らないか」のどちらかになる。

    Args:
        items: ``{サイト名: {項目名: 値}}`` の入れ子 dict（例:
            ``{"site_a": {"client_id": "..."}}``）。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        InvalidCredentialNameError: サイト名・項目名に使えない文字が含まれている場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
        TypeError: 値が文字列でない・入れ子の構造が壊れている場合（呼び出し側のバグ）。
    """
    for site, fields in items.items():
        if not CREDENTIAL_NAME_PATTERN.fullmatch(site):
            raise InvalidCredentialNameError("サイト名", site)
        if not isinstance(fields, dict):
            raise TypeError(
                f"認証情報の値はサイトごとの dict で渡してください: "
                f"{site} は {type(fields).__name__}"
            )
        for field, value in fields.items():
            if not CREDENTIAL_NAME_PATTERN.fullmatch(field):
                raise InvalidCredentialNameError("項目名", field)
            if not isinstance(value, str):
                raise TypeError(
                    f"認証情報の値は文字列で渡してください: "
                    f"{site}/{field} は {type(value).__name__}"
                )
    path = path or CREDENTIALS_PATH
    logger.debug("save_credentials 開始: path=%s, サイト数=%d", path, len(items))
    data = _load_all(path)
    for site, fields in items.items():
        data.setdefault(site, {}).update(fields)
    _save_all(data, path)
    logger.debug("save_credentials 完了: path=%s, 登録後総サイト数=%d", path, len(data))
    # 保存後は同じパスを参照する ``Credentials`` インスタンスの復号キャッシュが
    # 古くなるので、 次回の属性アクセスで再復号されるよう ``_cache`` を捨てる
    # （詳細は ``Credentials._decrypted`` のコメント）
    _invalidate_instances_for(path)


@measure
def load_credential(site: str, field: str, path: Path | None = None) -> str:
    """保存済みの認証情報を復号して返す。

    Args:
        site: 登録時に指定したサイト名。
        field: 登録時に指定した項目名。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Raises:
        InvalidCredentialNameError: サイト名・項目名に使えない文字が含まれている場合。
        CredentialNotFoundError: 指定した（サイト, 項目）が未登録の場合。
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """
    if not CREDENTIAL_NAME_PATTERN.fullmatch(site):
        raise InvalidCredentialNameError("サイト名", site)
    if not CREDENTIAL_NAME_PATTERN.fullmatch(field):
        raise InvalidCredentialNameError("項目名", field)
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    site_dict = data.get(site)
    name = f"{site}{_DISPLAY_NAME_SEPARATOR}{field}"
    if not site_dict or field not in site_dict:
        registered = sorted(
            f"{s}{_DISPLAY_NAME_SEPARATOR}{f}" for s, fields in data.items() for f in fields
        )
        logger.debug("load_credential: 未登録: site=%s, field=%s, path=%s", site, field, path)
        raise CredentialNotFoundError(name, registered)
    logger.debug("load_credential 成功: site=%s, field=%s, path=%s", site, field, path)
    return site_dict[field]


@measure
def delete_credential(site: str, field: str, path: Path | None = None) -> None:
    """登録済みの認証情報を1件削除する。

    Raises:
        InvalidCredentialNameError: サイト名・項目名に使えない文字が含まれている場合。
        CredentialNotFoundError: 指定した（サイト, 項目）が未登録の場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    if not CREDENTIAL_NAME_PATTERN.fullmatch(site):
        raise InvalidCredentialNameError("サイト名", site)
    if not CREDENTIAL_NAME_PATTERN.fullmatch(field):
        raise InvalidCredentialNameError("項目名", field)
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    site_dict = data.get(site)
    name = f"{site}{_DISPLAY_NAME_SEPARATOR}{field}"
    if not site_dict or field not in site_dict:
        registered = sorted(
            f"{s}{_DISPLAY_NAME_SEPARATOR}{f}" for s, fields in data.items() for f in fields
        )
        logger.debug("delete_credential: 未登録: site=%s, field=%s, path=%s", site, field, path)
        raise CredentialNotFoundError(name, registered)
    del site_dict[field]
    # サイトを空にしたら dict 自体も取り除く（``data[site] = {}`` の状態を残さない）
    if not site_dict:
        del data[site]
    _save_all(data, path)
    logger.debug(
        "delete_credential 完了: site=%s, field=%s, path=%s, 残サイト数=%d",
        site,
        field,
        path,
        len(data),
    )
    # 削除後はキャッシュが古くなるので破棄。 詳細は ``Credentials._decrypted``
    _invalidate_instances_for(path)


@measure
def list_names(path: Path | None = None) -> list[tuple[str, str]]:
    """登録済みの ``(サイト名, 項目名)`` のタプル一覧を返す（値そのものは返さない）。

    並び順は **サイト名 → 項目名** でソートする。同じサイト名の項目が固まって
    表示されるので、 ``cli list`` のようなグルーピング表示がタプル1要素目だけで済む。

    Raises:
        CredentialDecryptionError: 別のユーザー・PC で登録されていて復号できない場合。
    """
    path = path or CREDENTIALS_PATH
    data = _load_all(path)
    pairs = sorted((site, field) for site, fields in data.items() for field in fields)
    logger.debug("list_names: path=%s, 件数=%d", path, len(pairs))
    return pairs


def _load_all(path: Path) -> dict[str, dict[str, str]]:
    """暗号化ファイルを復号して ``{サイト名: {項目名: 値}}`` の dict を返す。未作成なら空 dict。

    「復号できない」と「復号はできたが中身が壊れている」は対処が違うので、
    別の例外に分ける（前者は実行アカウントの問題、後者は取り込み直し）。
    """
    if not path.exists():
        logger.debug("_load_all: ファイル未作成: path=%s", path)
        return {}
    encrypted = path.read_bytes()
    try:
        _, decrypted = win32crypt.CryptUnprotectData(encrypted, None, None, None, 0)
    except pywintypes.error as e:
        # 原因（別ユーザー・別 PC・暗号文の破損）を DPAPI は区別して返さないので、
        # 確認する順番を示した1つの例外にまとめる
        logger.debug("_load_all: DPAPI 復号に失敗: path=%s", path)
        raise CredentialDecryptionError(path, e) from e

    try:
        data = json.loads(decrypted.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        logger.debug("_load_all: JSON 解析に失敗: path=%s", path)
        raise CredentialStoreCorruptedError(path, str(e)) from e
    if (
        not isinstance(data, dict)
        or not all(isinstance(key, str) for key in data)
        or not all(
            isinstance(value, dict)
            and all(
                isinstance(field, str) and isinstance(item, str) for field, item in value.items()
            )
            for value in data.values()
        )
    ):
        logger.debug("_load_all: 復号済み JSON の形が不正: path=%s", path)
        raise CredentialStoreCorruptedError(path, "キーと値がすべて文字列の形になっていません。")
    return data


def _save_all(data: dict[str, dict[str, str]], path: Path) -> None:
    """入れ子 dict を暗号化してファイルに書き込む。

    一時ファイル経由でアトミックに置き換える（``atomic_write`` に統一）。
    書き込み中にクラッシュしても、暗号化ファイルが半端に壊れて全キーが読めなくなる
    ことはない（「全部入るか、1つも入らないか」の性質が保たれる）。

    ただし**書き手が1つであることが前提**。読んで足して書き戻す流れなので、
    2つのプロセスが同時に書くと後から書いたほうが勝ち、片方の追加が消える。
    取り込みは人が1回だけ実行する運用なので、ロックは持たせていない。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    cleanup_stale_tmp(path)  # 前回クラッシュ時の残骸を掃除
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    encrypted = win32crypt.CryptProtectData(raw, _FILE_DESCRIPTION, None, None, None, 0)
    # ``atomic_write`` は親フォルダを作らないので上の mkdir で存在を保証する。
    # 暗号化済み bytes をそのまま書く（アトミックに丸ごと置き換わる）。
    with atomic_write(path) as tmp_path:
        tmp_path.write_bytes(encrypted)
    logger.debug("_save_all: 暗号化して書き出し: path=%s, 件数=%d", path, len(data))


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
# 以前は ``list[Credentials]`` で強参照していたが、 ``Credentials`` の参照を
# すべて手放しても GC されず、 ``_cache`` に入った**復号済みの平文がプロセス
# 終了まで残る**問題があった。 ``weakref.WeakSet`` に変えると、 参照を持たない
# インスタンスは GC で自然に消え、 レジストリも膨らまない。
# ``Credentials`` は ``__getattr__`` を定義しているが ``__weakref__`` はクラスメンバ
# として普通に解決されるため weakref はそのまま使える（ ``__slots__`` は不要）。
_instances_by_path: dict[str, weakref.WeakSet["Credentials"]] = {}


def _register_instance(instance: "Credentials") -> None:
    """``Credentials._decrypted()`` から呼ばれ、 ``path`` ごとにインスタンスを覚える。

    ``WeakSet`` は同じインスタンスを ``add`` しても 1 つしか持たない（多重登録
    防止は WeakSet 自体が担保する）。 参照を手放したインスタンスは勝手に消える。
    """
    key = str(instance._path or CREDENTIALS_PATH)
    bucket = _instances_by_path.setdefault(key, weakref.WeakSet())
    bucket.add(instance)
    logger.debug(
        "_register_instance: path=%s 配下にインスタンスを登録（サイズ=%d）", key, len(bucket)
    )


def _invalidate_instances_for(path: Path) -> None:
    """指定パスを使う全 ``Credentials`` インスタンスのキャッシュを破棄する。

    ``save_credentials`` / ``delete_credential`` から呼ばれる。 該当の
    インスタンスが保持している復号結果（``_cache``）は古くなっているはずなので、
    ``None`` に戻して次回 ``__getattr__`` で再復号させる。

    ``WeakSet`` を直接イテレートすると「GC された瞬間に壊れる」競合が起きる
    ので、 スナップショット（ ``list(...)`` ）を取ってから走査する。
    """
    key = str(path)
    invalidated = 0
    for instance in list(_instances_by_path.get(key, ())):
        if instance.__dict__.get("_cache") is not None:
            object.__setattr__(instance, "_cache", None)
            invalidated += 1
    logger.debug("_invalidate_instances_for: path=%s のキャッシュを %d 件破棄", key, invalidated)
