r"""comken/toolbox/master_table.py — Excel の表を設定として読む。

**非エンジニアが Excel で編集する一覧**を、型付きの行として読み込む。
「どのレポートを取るか」「どのファイルをコピーするか」のように**行が増えていく設定**は、
config.ini より表のほうが扱いやすい（並べ替え・フィルタ・コピーができる）。

使い方は、1行につき1列を宣言するだけ。

    from dataclasses import dataclass
    from pathlib import Path

    from comken.toolbox.master_table import MasterRow, column


    @dataclass(frozen=True)
    class Report(MasterRow):
        \"\"\"レポート管理表の1行。\"\"\"

        SHEET_NAME = "管理表"
        PATH = Path(r"\\server\share\レポート管理表.xlsx")

        key: int = column("ID", unique=True, help="社内で決める管理番号")
        summary: str = column("概要", help="人が読んで分かる説明")
        folder: Path = column("保存先", help="落としたファイルを置くフォルダ")
        enabled: bool = column("有効", default=True, help="使わなくなったら「無効」")

    Report.create_template(path)   # 記入例と「記入方法」シート付きの雛形を作る
    for report in Report.load():   # 読む（型変換・検証込み）
        print(report.summary, report.folder)

**Python の名前は英語、Excel の見出しは日本語**にできる。`column()` の第1引数が
Excel の見出しで、スペースを含む見出し（`Salesforce URL`）も扱える。

型は注釈から決まる（`int` / `str` / `bool` / `Path`）。**列の定義はここ1か所**なので、
読み込む型と Excel の見出しがズレることがない。
"""

import dataclasses
from collections.abc import Iterator
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, ClassVar, Self

from ..exceptions import (
    MasterColumnNotFoundError,
    MasterDuplicateValueError,
    MasterRowValueError,
    MasterSheetNotDefinedError,
)
from .excel import ExcelReader, ExcelWriter

# フィールドの metadata に入れるときのキー
_SPEC_KEY = "comken_master_column"

# 「有効」列などで真として扱う値（小文字で比較する）
_TRUE_WORDS = ("有効", "○", "o", "yes", "true", "1", "on")

# 見出し行を除いた1行目が Excel の何行目か（見出しが1行目のため）
_FIRST_DATA_ROW = 2


@dataclass(frozen=True)
class ColumnSpec:
    """1つの列の決まりごと。

    Attributes:
        header: Excel の見出し（そのまま1行目に書かれる）。
        unique: True なら、同じ値が2つ以上あるとエラーにする。
        choices: 書ける値を限る場合の一覧。
        help: 「記入方法」シートとエラーメッセージに使う説明。
    """

    header: str
    unique: bool = False
    choices: tuple[str, ...] | None = None
    help: str = ""


def column(
    header: str,
    *,
    unique: bool = False,
    choices: tuple[str, ...] | None = None,
    default: Any = dataclasses.MISSING,
    help: str = "",  # 「記入方法」シートに出る説明。help 以外の名前だと意味が伝わらない
) -> Any:
    """列を1つ宣言する（dataclass のフィールドに使う）。

    Args:
        header: **Excel の見出し**。Python の名前と違ってよく、スペースも使える。
        unique: 同じ値が2つ以上あればエラーにする（管理番号など）。
        choices: 書ける値を限る（`("定期", "個別")` など）。
        default: 空欄のときの値。省略すると**空欄はエラー**になる。
        help: 何を書く列かの説明。「記入方法」シートとエラーメッセージに出る。
    """
    spec = ColumnSpec(header=header, unique=unique, choices=choices, help=help)
    metadata = {_SPEC_KEY: spec}
    if default is dataclasses.MISSING:
        return field(metadata=metadata)
    return field(default=default, metadata=metadata)


class MasterRow:
    """Excel の表の1行。dataclass と一緒に継承して使う。

    クラス変数:
        SHEET_NAME: 読み書きするシート名。
        PATH: 既定のファイル。指定すると `load()` を引数なしで呼べる。
    """

    SHEET_NAME: ClassVar[str] = "管理表"
    PATH: ClassVar[Path | None] = None

    # ── 読む ────────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str | Path | None = None) -> list[Self]:
        """表を読んで、行のリストを返す。

        Args:
            path: Excel のパス。省略時はクラス変数 `PATH`。

        Returns:
            宣言した順のまま、1行ずつのインスタンス。

        Raises:
            MasterSheetNotDefinedError: path も PATH も無い場合。
            MasterColumnNotFoundError: 宣言した見出しが表に無い場合。
            MasterRowValueError: 値が型・選択肢に合わない場合。
            MasterDuplicateValueError: unique の列に同じ値がある場合。
        """
        source = Path(path) if path is not None else cls.PATH
        if source is None:
            raise MasterSheetNotDefinedError(cls.__name__)

        with ExcelReader(source) as book:
            raw_rows = book.read_rows_as_dicts(cls.SHEET_NAME)

        rows: list[Self] = []
        seen: dict[str, set] = {}
        for offset, raw in enumerate(raw_rows):
            if _is_blank(raw):
                continue  # 表の下に残った空行は読み飛ばす
            row_number = offset + _FIRST_DATA_ROW
            _require_headers(cls, raw, source)
            rows.append(cls._build(raw, row_number, seen, source))
        return rows

    @classmethod
    def _build(cls, raw: dict, row_number: int, seen: dict[str, set], source: Path) -> Self:
        """1行ぶんの生の値を、型付きのインスタンスにする。"""
        values = {}
        for name, spec, value_type in cls._columns():
            value = _convert(raw.get(spec.header), value_type, spec, row_number, cls)
            if value is _EMPTY:
                default = _default_of(cls, name)
                if default is dataclasses.MISSING:
                    raise MasterRowValueError(row_number, spec.header, "", "空のままにできません。")
                value = default
            if spec.unique:
                if value in seen.setdefault(name, set()):
                    raise MasterDuplicateValueError(spec.header, value, source)
                seen[name].add(value)
            values[name] = value
        return cls(**values)

    # ── 雛形を作る ───────────────────────────────────────────────────────────
    @classmethod
    def create_template(cls, path: str | Path, examples: list[dict] | None = None) -> Path:
        """記入例と「記入方法」シートが入った雛形を作る。

        **空の表を渡されるより、1行埋まっているほうが何をどう書くか伝わる**ので、
        記入例を入れておく（使う前に消す案内も「記入方法」に書く）。

        Args:
            path: 作成先（.xlsx）。
            examples: 記入例。{Python の名前: 値} の形で渡す。
        """
        path = Path(path)
        headers = [spec.header for _, spec, _ in cls._columns()]
        rows = [
            [_to_cell(example.get(name, "")) for name, _, _ in cls._columns()]
            for example in (examples or [])
        ]

        with ExcelWriter.create(path, cls.SHEET_NAME) as book:
            sheet = book.sheet(cls.SHEET_NAME)
            sheet.write_row(1, headers)
            for offset, row in enumerate(rows):
                sheet.write_row(offset + _FIRST_DATA_ROW, row)
            if headers:
                last_column = _column_letter(len(headers))
                sheet.add_table(_table_name(cls), f"A1:{last_column}{len(rows) + 1}")
            sheet.auto_width()
            sheet.freeze_header()

            cls._write_guide(book)
            book.save()
        return path

    @classmethod
    def _write_guide(cls, book: ExcelWriter) -> None:
        """「記入方法」シートを書く。非エンジニアが1枚で分かるようにする。"""
        sheet = book.add_sheet("記入方法")
        sheet.write_row(1, ["列", "何を書くか", "書けない場合"])
        for row_number, (name, spec, value_type) in enumerate(cls._columns(), start=2):
            required = _default_of(cls, name) is dataclasses.MISSING
            note = "空欄にできません" if required else "空欄にできます"
            if spec.choices:
                note = f"「{'」か「'.join(spec.choices)}」と書いてください"
            elif value_type is bool:
                note = "「有効」か「無効」と書いてください"
            sheet.write_row(row_number, [spec.header, spec.help, note])

        last = len(cls._columns()) + 3
        sheet.write_row(last, ["注意", "1行目の見出しは変えないでください（列名で読みます）", ""])
        sheet.write_row(last + 1, ["", "記入例の行は、実際に使うときに消してください", ""])
        for letter in ("A", "B", "C"):
            sheet.set_bold(1, letter)
        sheet.auto_width(max_width=80)
        sheet.freeze_header()

    # ── 列の情報 ─────────────────────────────────────────────────────────────
    @classmethod
    def _columns(cls) -> list[tuple[str, ColumnSpec, type]]:
        """(Python の名前, 列の決まり, 型) を宣言順で返す。

        `column()` を使っていないフィールドは、**名前をそのまま見出しにする**
        （見出しと同じ名前が使えるなら、宣言は型注釈だけで済む）。
        """
        found = []
        for item in fields(cls):
            spec = item.metadata.get(_SPEC_KEY) or ColumnSpec(header=item.name)
            found.append((item.name, spec, item.type))
        return found

    def __init_subclass__(cls, **kwargs) -> None:
        # dataclass を付け忘れると fields() が空になり、原因の分からない失敗になる。
        # 継承した時点では判定できないので、ここでは何もせず load() 側で確かめる
        super().__init_subclass__(**kwargs)


class _Empty:
    """空欄を表す番兵（None も空文字も「書かれた値」と区別したいため）。"""


_EMPTY = _Empty()


def _is_blank(raw: dict) -> bool:
    """すべての列が空の行か。"""
    return all(value in (None, "") for value in raw.values())


def _require_headers(cls: type[MasterRow], raw: dict, source: Path) -> None:
    """宣言した見出しが表にあるか確かめる。"""
    for _, spec, _ in cls._columns():
        if spec.header not in raw:
            raise MasterColumnNotFoundError(spec.header, sorted(raw), source, cls.SHEET_NAME)


def _default_of(cls: type[MasterRow], name: str) -> Any:
    """そのフィールドの既定値（無ければ MISSING）。"""
    for item in fields(cls):
        if item.name == name:
            return item.default
    return dataclasses.MISSING


def _convert(value: Any, value_type: Any, spec: ColumnSpec, row: int, cls: type) -> Any:
    """セルの値を、宣言した型へ変換する。空欄なら _EMPTY を返す。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return _EMPTY

    text = str(value).strip()
    if spec.choices and text not in spec.choices:
        raise MasterRowValueError(
            row, spec.header, value, f"「{'」か「'.join(spec.choices)}」と書いてください。"
        )

    if value_type is bool or value_type == "bool":
        return _to_bool(value, text)
    if value_type is int or value_type == "int":
        return _to_int(value, text, spec, row)
    if value_type is Path or value_type == "Path":
        return Path(text)
    return text


def _to_bool(value: Any, text: str) -> bool:
    if isinstance(value, bool):
        return value
    return text.lower() in _TRUE_WORDS


def _to_int(value: Any, text: str, spec: ColumnSpec, row: int) -> int:
    if isinstance(value, bool):
        raise MasterRowValueError(row, spec.header, value, "数字を入れてください。")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)  # Excel は数値を小数で返すことがある
    if not text.isdigit():
        raise MasterRowValueError(row, spec.header, value, "数字だけで書いてください（例: 1001）。")
    return int(text)


def _to_cell(value: Any) -> Any:
    """記入例をセルに書ける形にする。"""
    if isinstance(value, bool):
        return "有効" if value else "無効"
    if isinstance(value, Path):
        return str(value)
    return value


def _column_letter(index: int) -> str:
    """1 -> A, 27 -> AA。"""
    letters = ""
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def _table_name(cls: type) -> str:
    """Excel のテーブル名（英数字とアンダースコアだけにする）。"""
    name = "".join(char if char.isalnum() or char == "_" else "_" for char in cls.__name__)
    return name if name[:1].isalpha() else f"T_{name}"


def iter_columns(cls: type[MasterRow]) -> Iterator[tuple[str, ColumnSpec, type]]:
    """宣言された列を順に返す（雛形やドキュメントを作るとき用）。"""
    yield from cls._columns()
