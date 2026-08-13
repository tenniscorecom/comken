"""comken/credentials/importer.py — 平文 JSON を暗号化ファイルへ取り込む

認証情報は平文で置けないが、対話式で1件ずつ入力させるのも配布時に手間がかかる。
そこで **一時的に置いた平文 JSON を読み、DPAPI で暗号化して取り込み、
平文はその場で消す** という流れにする。

    認証情報.json（平文・一時的に置く）
            ↓  python -m comken.credentials import 認証情報.json
    %USERPROFILE%\\.comken\\credentials.dat（DPAPI 暗号化）
            ↓
    Credentials("site_a").client_id

JSON の形式（システム名ごとに項目をまとめる）:

    {
      "site_a": {"client_id": "...", "client_secret": "..."},
      "site_b": {"client_id": "...", "client_secret": "..."}
    }

これが "site_a_client_id" のようなキー名に展開されて保存される。
同じキー名が既にあれば上書きし、JSON に無いキーはそのまま残る
（組織ごとに JSON を分けて、何回かに分けて取り込める）。
"""

from __future__ import annotations

import json
from pathlib import Path

from ..exceptions import CredentialImportError
from .store import save_credentials

_NAME_SEPARATOR = "_"
_FIELD_PART_COUNT = 2


def credential_name(system: str, field: str) -> str:
    """システム名と項目名を、保存に使う1つのキー名へまとめる。"""
    return f"{system}{_NAME_SEPARATOR}{field}"


def split_credential_name(name: str) -> tuple[str, str] | None:
    """保存キーをシステム名と項目名へ戻す。規則に合わなければ None を返す。

    項目名は importer の標準形（client_id / client_secret）の2語として扱い、
    それより左をすべてシステム名にする。
    """
    parts = name.rsplit(_NAME_SEPARATOR, _FIELD_PART_COUNT)
    if len(parts) != _FIELD_PART_COUNT + 1 or not all(parts):
        return None
    system, field_first, field_second = parts
    return system, f"{field_first}{_NAME_SEPARATOR}{field_second}"


def import_json(json_path: str | Path, path: Path | None = None) -> list[str]:
    """平文 JSON を読み、暗号化ファイルへ取り込む。

    取り込みは「全部入るか、1つも入らないか」のどちらかになる。
    途中のキーが不正なら、1件も書き込まずに例外を送出する。

    Args:
        json_path: 読み込む平文 JSON のパス。
        path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。

    Returns:
        取り込んだキー名のリスト（値は含まない）。

    Raises:
        CredentialImportError: JSON が見つからない・壊れている・形式が違う場合。
        InvalidCredentialNameError: 展開したキー名に使えない文字が含まれている場合。
        CredentialDecryptionError: 既存ファイルを復号できない場合。
    """
    json_path = Path(json_path)
    items = _flatten(json_path)
    save_credentials(items, path)
    return sorted(items)


def _flatten(json_path: Path) -> dict[str, str]:
    """JSON を読み、{"site_a": {"client_id": ...}} を {"site_a_client_id": ...} にする。"""
    parsed = _read_json_object(json_path)
    return _flatten_fields(json_path, parsed)


def _read_json_object(json_path: Path) -> dict[str, object]:
    """JSON を読み、重複キーを含まない最上位オブジェクトとして返す。"""
    try:
        raw = json_path.read_text(encoding="utf-8")
    except OSError as e:
        raise CredentialImportError(json_path, f"ファイルを読めませんでした（{e}）。") from e
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as e:
        raise CredentialImportError(
            json_path, f"JSON として読めませんでした（{e.lineno} 行目付近: {e.msg}）。"
        ) from e
    except _DuplicateKeyError as e:
        raise CredentialImportError(json_path, f"「{e.key}」が2回書かれています。") from e

    if not isinstance(parsed, dict):
        raise CredentialImportError(json_path, "いちばん外側が { } になっていません。")
    return parsed


def _flatten_fields(json_path: Path, parsed: dict[str, object]) -> dict[str, str]:
    """検証済みの最上位オブジェクトを、保存用の平らなキーへ展開する。"""
    items: dict[str, str] = {}
    for system, fields in parsed.items():
        if not isinstance(fields, dict):
            raise CredentialImportError(json_path, f"「{system}」の中が {{ }} で囲まれていません。")
        for field, value in fields.items():
            if not isinstance(value, str):
                raise CredentialImportError(
                    json_path,
                    f"「{system}」の「{field}」が文字列ではありません。"
                    '値は必ず " " で囲んでください。',
                )
            if not system or not field:
                raise CredentialImportError(json_path, "システム名・項目名に空の名前があります。")
            if not value:
                raise CredentialImportError(json_path, f"「{system}」の「{field}」が空です。")
            name = credential_name(system, field)
            # 「site_a + _client_id」と「site + _a_client_id」は同じキー名になる。
            # 黙って上書きすると別の認証情報が入れ替わるので、ここで止める
            if name in items:
                raise CredentialImportError(
                    json_path, f"組み合わせると同じキー名になる項目があります: {name}"
                )
            items[name] = value

    if not items:
        raise CredentialImportError(json_path, "取り込む項目が1つもありません。")
    return items


class _DuplicateKeyError(ValueError):
    """JSON の同じ階層に同じ名前が2回書かれていた（_flatten の中だけで使う）。"""

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
