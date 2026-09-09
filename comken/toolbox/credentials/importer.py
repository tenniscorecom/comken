"""comken/toolbox/credentials/importer.py — 平文 JSON を暗号化ファイルへ取り込む

認証情報は平文で置けないが、対話式で1件ずつ入力させるのも配布時に手間がかかる。
そこで **一時的に置いた平文 JSON を読み、DPAPI で暗号化して取り込み、
平文はその場で消す** という流れにする。

    認証情報.json（平文・一時的に置く）
            ↓  python -m comken cred import 認証情報.json
    %USERPROFILE%\\.rpa\\system-id.enc（DPAPI 暗号化）
            ↓
    Credentials("site_a").client_id

JSON の形式（サイト名ごとに項目をまとめる）:

    {
      "site_a": {"client_id": "...", "client_secret": "..."},
      "site_b": {"client_id": "...", "client_secret": "..."}
    }

これがそのまま ``{サイト名: {項目名: 値}}`` の入れ子構造で保存される
（保存形式が JSON と一致するので、展開・再合成のやり取りは発生しない）。
同じ ``(サイト名, 項目名)`` が既にあれば上書きし、JSON に無いキーはそのまま残る
（組織ごとに JSON を分けて、何回かに分けて取り込める）。
"""

import json
import logging
from pathlib import Path

from comken.core.timer import measure
from comken.exceptions import CredentialImportError
from comken.toolbox.credentials.store import (
    CREDENTIAL_NAME_PATTERN,
    save_credentials,
)

logger = logging.getLogger(__name__)


@measure
def import_json(json_path: str | Path, path: Path | None = None) -> list[tuple[str, str]]:
    """平文 JSON を読み、暗号化ファイルへ取り込む。

    取り込みは「全部入るか、1つも入らないか」のどちらかになる。
    途中のキーが不正なら、1件も書き込まずに例外を送出する。

    Args:
        json_path: 読み込む平文 JSON のパス。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Returns:
        取り込んだ ``(サイト名, 項目名)`` のタプルのリスト（値は含まない）。
        ``list_names()`` と同じ並び順（サイト名→項目名でソート）。

    Raises:
        CredentialImportError: JSON が見つからない・壊れている・形式が違う場合
            （サイト名・項目名に使えない文字が含まれている場合を含む。
            ``_read_nested()`` が ``save_credentials()`` を呼ぶ前に検証するため、
            ``InvalidCredentialNameError`` はここでは送出されない）。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    json_path = Path(json_path)
    logger.debug("import_json 開始: json_path=%s, 暗号化先=%s", json_path, path or "既定")
    items = _read_nested(json_path)
    save_credentials(items, path)
    pairs = sorted((site, field) for site, fields in items.items() for field in fields)
    logger.debug(
        "import_json 完了: json_path=%s, 取り込み件数=%d, pairs=%s",
        json_path,
        len(pairs),
        pairs,
    )
    return pairs


def _read_nested(json_path: Path) -> dict[str, dict[str, str]]:
    """JSON を読み、検証した上で ``{サイト名: {項目名: 値}}`` の入れ子 dict として返す。

    検証は:
        - ファイルが読み取れること
        - JSON として解析でき、重複キーが無いこと
        - 最上位がオブジェクト（``{}``）であること
        - 各サイトの中身がオブジェクト（``{}``）であること
        - 各項目の値が文字列で空でないこと
        - サイト名・項目名が空でないこと、使える文字種であること
    """
    parsed = _read_json_object(json_path)
    if not parsed:
        logger.debug("_read_nested: 項目が1つもない: json_path=%s", json_path)
        raise CredentialImportError(json_path, "取り込む項目が1つもありません。")

    nested: dict[str, dict[str, str]] = {}
    for site, raw_fields in parsed.items():
        site_dict = _validate_and_collect_site(json_path, site, raw_fields)
        nested[site] = site_dict

    if not any(fields for fields in nested.values()):
        logger.debug("_read_nested: 1件も値が無い: json_path=%s", json_path)
        raise CredentialImportError(json_path, "取り込む項目が1つもありません。")
    logger.debug("_read_nested 成功: json_path=%s, サイト数=%d", json_path, len(nested))
    return nested


def _validate_and_collect_site(json_path: Path, site: str, raw_fields: object) -> dict[str, str]:
    """サイト名と その中身を検証し、 ``{項目名: 値}`` の dict を組み立てて返す。"""
    if not site:
        raise CredentialImportError(json_path, "サイト名が空です。")
    if not CREDENTIAL_NAME_PATTERN.fullmatch(site):
        raise CredentialImportError(
            json_path,
            f"サイト名に使えるのは半角英数字とアンダースコアだけです: {site}",
        )
    if not isinstance(raw_fields, dict):
        raise CredentialImportError(json_path, f"「{site}」の中が {{ }} で囲まれていません。")
    fields: dict[str, str] = {}
    for field, value in raw_fields.items():
        _validate_field(json_path, site, field, value)
        fields[field] = value
    return fields


def _validate_field(json_path: Path, site: str, field: str, value: object) -> None:
    """サイト配下の項目名と、 その値を検証する。"""
    if not field:
        raise CredentialImportError(json_path, f"「{site}」の中に項目名が空のエントリがあります。")
    if not CREDENTIAL_NAME_PATTERN.fullmatch(field):
        raise CredentialImportError(
            json_path,
            f"項目名に使えるのは半角英数字とアンダースコアだけです: {site}/{field}",
        )
    if not isinstance(value, str):
        raise CredentialImportError(
            json_path,
            f'「{site}」の「{field}」が文字列ではありません。値は必ず " " で囲んでください。',
        )
    if not value:
        raise CredentialImportError(json_path, f"「{site}」の「{field}」が空です。")


def _read_json_object(json_path: Path) -> dict[str, object]:
    """JSON を読み、重複キーを含まない最上位オブジェクトとして返す。"""
    try:
        raw = json_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.debug("_read_json_object: ファイル読み込み失敗: json_path=%s", json_path)
        raise CredentialImportError(json_path, f"ファイルを読めませんでした（{e}）。") from e
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as e:
        logger.debug("_read_json_object: JSON 解析失敗: json_path=%s, line=%d", json_path, e.lineno)
        raise CredentialImportError(
            json_path, f"JSON として読めませんでした（{e.lineno} 行目付近: {e.msg}）。"
        ) from e
    except _DuplicateKeyError as e:
        logger.debug("_read_json_object: 重複キー検出: json_path=%s, key=%s", json_path, e.key)
        raise CredentialImportError(json_path, f"「{e.key}」が2回書かれています。") from e

    if not isinstance(parsed, dict):
        logger.debug("_read_json_object: 最上位がオブジェクトでない: json_path=%s", json_path)
        raise CredentialImportError(json_path, "いちばん外側が { } になっていません。")
    logger.debug("_read_json_object 成功: json_path=%s, キー数=%d", json_path, len(parsed))
    return parsed


class _DuplicateKeyError(ValueError):
    """JSON の同じ階層に同じ名前が2回書かれていた（_read_nested の中だけで使う）。"""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """JSON の重複キーを弾く（既定の json.loads は後勝ちで黙って捨てるため）。"""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result
