"""comken/exceptions/tables.py — 表データ・列・型変換に関する例外。

WarnCoerce ヘルパーとテーブル／列／管理表／列検証の例外をまとめる。"""

import warnings
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from comken.exceptions.base import ComkenError


class TableError(ComkenError):
    """表データの読み書き・転記に関するエラー。具体的な状況はメッセージに出る

    発生箇所: Transfer

    対処:
        画面に表示された具体的なエラー内容を確認する
    """


class InvalidTableInputError(TableError):
    """Table API に対応しない入力が渡された。

    発生箇所: Table / CSV / ExcelTable

    対処:
        columns、rows、types の型と列名を確認する
    """


class TableColumnNotFoundError(TableError):
    """Table に指定された列が存在しない。

    発生箇所: Table

    対処:
        Table.columns を確認し、存在する列名を指定する
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(f"存在しない列です: {columns}")


class TableDuplicateKeyError(TableError):
    """Table の索引または比較に使うキーが重複している。

    発生箇所: Table.index() / compare_tables()

    対処:
        キー列の値を一意にしてから処理をやり直す
    """

    def __init__(self, columns: list[str], key: object) -> None:
        super().__init__(
            f"列「{','.join(columns)}」のキー「{key}」が重複しています。キーを一意にしてください。"
        )


class ColumnNotFoundError(ComkenError):
    """Excel・CSV・データ比較で列が見つからないエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class ExcelColumnNotFoundError(ColumnNotFoundError):
    """Excel の列見出しが見つからない

    非エンジニアが列名を変更したときに分かりやすいメッセージを出すために使う。

    発生箇所: 利用側プロジェクトの列検証処理（comken 本体のソースからは
              送出されない。利用者プロジェクトから送出する想定）

    使い方:
        from comken.exceptions import ExcelColumnNotFoundError

        REQUIRED_COLUMNS = ["日付", "担当者", "金額"]

        def validate_columns(rows: list[dict[str, str]], required: list[str]) -> None:
            missing = [column for column in required if column not in rows[0]]
            if missing:
                raise ExcelColumnNotFoundError(missing)

    対処:
        Excel の1行目を確認する
    """

    def __init__(self, columns: list[str]) -> None:
        super().__init__(
            "Excelのヘッダーが正しくありません。\n"
            f"見つからない列: {', '.join(columns)}\n"
            "Excelの1行目を確認してください。"
        )


class TransferSourceColumnNotFoundError(ColumnNotFoundError):
    """列名転記で、lookup の転記元列が見つからない

    comken 本体のソースからは送出されない。利用者プロジェクトから送出する想定。
    例外を定義して import するだけで使え、comken 内の利用は前提としない。
    ``ExcelColumnNotFoundError`` と同じ位置づけ。

    発生箇所: 利用側プロジェクトの転記元列検証処理

    対処:
        転記元データと config.ini のマッピング左側を確認する
    """

    def __init__(self, columns: list[str], existing: list[str]) -> None:
        super().__init__(
            f"転記元の列がlookupに見つかりません: {', '.join(columns)}\n"
            f"転記元に存在する列: {', '.join(existing)}\n"
            "CSVなどの転記元データと config.ini のマッピング左側を確認してください。"
        )


class InvalidColumnError(ComkenError):
    """列の指定が正しくない（打ち間違いなど）

    対処:
        列は番号（1, 2, …）か列記号（"A", "AA"）で指定する
    """

    def __init__(self, column: str) -> None:
        super().__init__(
            f"列の指定が正しくありません: {column!r}\n"
            '列番号（1始まり）または列記号で指定してください（例: 1, "A", "AA"）。'
        )


class MasterTableError(ComkenError):
    """Excel の管理表に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class MasterRowValueError(MasterTableError):
    """管理表の値が正しくない

    数字を書く列に文字が入っている、決まった書き方以外を書いた、空にできない列が空、など。

    発生箇所: comken.services.salesforce_downloader.report_master の load()

    対処:
        メッセージに出ている行と列を、管理表で確認して直す
    """

    def __init__(self, row_number: int, header: str, value: object, reason: str) -> None:
        super().__init__(
            f"管理表 {row_number} 行目の「{header}」が正しくありません: {value!r}\n{reason}"
        )


class MasterDuplicateValueError(MasterTableError):
    """一意であるべき列に、同じ値が2つ以上ある

    管理番号のように「1つに決まる」ことが前提の列で重複すると、
    どの行を指しているか決められない。

    発生箇所: comken.services.salesforce_downloader.report_master の load()

    対処:
        管理表を開いて、重複している値のどちらかを別の値に変える
    """

    def __init__(self, header: str, value: object, path: Path) -> None:
        super().__init__(
            f"管理表の「{header}」に同じ値が2つあります: {value!r}\n"
            f"{path}\n"
            "この列は1つに決まる必要があるため、どちらかを変えてください。"
        )


class _Warnings:
    """ライブラリが発行する UserWarning のメッセージ。"""

    COERCION = "{param} に {type_name}（{value!r}）が渡されました。{expected} に変換します。"


def _callable_ctor[T](t: type[T]) -> Callable[[Any], T]:
    """``type[T]`` を ``Callable[[Any], T]`` として読み替える内部ヘルパー。

    pyright は ``type[T]`` だけでは ``T`` のコンストラクタ引数を推論できないため、
    シグネチャ付きの callable として教えて呼び出し可能にする。実行時は ``t(value)`` と
    等価（``type`` のインスタンスは呼び出せる）。
    """
    return cast(Callable[[Any], T], t)


def _warn_coerce[T](value: Any, expected: type[T], param: str, stacklevel: int = 3) -> T:
    """型が違う場合に警告して変換する。"""
    if value is None:
        raise TypeError(f"{param} に None が渡されました。{expected.__name__} を渡してください。")
    if not isinstance(value, expected):
        warnings.warn(
            _Warnings.COERCION.format(
                param=param,
                type_name=type(value).__name__,
                value=value,
                expected=expected.__name__,
            ),
            UserWarning,
            stacklevel=stacklevel,
        )
    # expected は呼び出し側で ``str`` / ``int`` などの具体型を渡されるため、
    # 実行時は ``expected(value)`` で安全に変換できる。pyright は ``type[T]`` だけでは
    # ``T`` のコンストラクタ引数シグネチャを推論できないため、callable 型へ局所キャストして
    # シグネチャを教える（型レベルだけで Any には逃げない）
    return cast(T, _callable_ctor(expected)(value))
