"""comken/core/utils/transfer.py — 転記で共有する補助関数。

`excel/sheet.py`（openpyxl 版）と `windows/handler.py`（COM 版）の両方から
利用される、転記の前処理だけを置く。

- `normalize_lookup_key()`: 照合キーの正規化（COM が float で返す差を吸収する）
- `mapping_columns()`: 列名によるキー列・転記先・転記元の検証

転記本体のロジック（COM の Range 一括書き込みや openpyxl のセル単位書き込み）は
呼び出し側の責務であり、ここには置かない。

NOTE: 公開 API ではない。利用者が直接呼ぶことは想定していない。
`excel` と `windows` の両方から依存される中立的な置き場所として存在している。
"""

from typing import Any

from ...exceptions import (
    TransferDestinationColumnNotFoundError,
    TransferKeyColumnNotFoundError,
    TransferSourceColumnNotFoundError,
)


def normalize_lookup_key(value: Any) -> str | None:
    """照合キーを正規化する。COM が整数セルを float で返す差を吸収する。

    - `None`、空文字、空白のみの文字列は `None` を返す（呼び出し側はその行を飛ばす）
    - 整数値の float（1000.0）は int（1000）を経由して文字列にする
    - 前後の空白を落とす

    NOTE: `utils/data.py._normalize()` は行の比較用で None を "" に揃える別物。
    こちらは照合キー用で、空なら None を返してその行を飛ばす役割を持つ。

    Args:
        value: Excel セルや CSV から取得した照合キー候補。

    Returns:
        正規化された照合キー。空だった場合は None（その行をスキップする合図）。
    """
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def mapping_columns(
    headers: tuple[Any, ...],
    key_column_name: str,
    lookup: dict[str, dict],
    mapping: dict[str, str],
) -> tuple[dict[str, int], dict[str, int]]:
    """列名の対応関係を検証し、照合列と転記先の列番号を返す。

    - `key_column_name` が見出しに無ければ `TransferKeyColumnNotFoundError`
    - 転記先の列名（`mapping.values()`）が見出しに無ければ
      `TransferDestinationColumnNotFoundError`
    - 転記元の列名（`mapping.keys()`）が `lookup` の全行に無ければ
      `TransferSourceColumnNotFoundError`

    列不足で途中まで書き換わったブックを残さないよう、書き込みを始める前に
    すべての整合性をまとめて検証する。

    Args:
        headers: 転記先シートのヘッダー行（タプル）。
        key_column_name: 照合に使う列の見出し名。
        lookup: `{キー: {列名: 値}}` の辞書（`CsvReader.index()` 等で作る）。
        mapping: `{転記元の列名: 転記先の列名}` の対応表。

    Returns:
        `({見出し名: 列番号}, {転記元列名: 転記先の列番号})` のタプル。

    Raises:
        TransferKeyColumnNotFoundError: キー列が見出しに無い場合。
        TransferDestinationColumnNotFoundError: 転記先列が見出しに無い場合。
        TransferSourceColumnNotFoundError: 転記元列が lookup の全行に無い場合。
    """
    header_names = [str(header) for header in headers if header is not None]
    header_columns = {
        str(header): column for column, header in enumerate(headers, start=1) if header is not None
    }
    if key_column_name not in header_columns:
        raise TransferKeyColumnNotFoundError(key_column_name, header_names)

    missing_destinations = [name for name in mapping.values() if name not in header_columns]
    if missing_destinations:
        raise TransferDestinationColumnNotFoundError(missing_destinations, header_names)

    lookup_rows = list(lookup.values())
    source_columns = set(lookup_rows[0]) if lookup_rows else set()
    for lookup_row in lookup_rows[1:]:
        source_columns.intersection_update(lookup_row)
    missing_sources = [name for name in mapping if name not in source_columns]
    if missing_sources:
        raise TransferSourceColumnNotFoundError(missing_sources, sorted(source_columns))

    destination_columns = {
        source: header_columns[destination] for source, destination in mapping.items()
    }
    return header_columns, destination_columns
