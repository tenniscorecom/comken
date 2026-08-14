r"""comken/services/salesforce_downloader/template.py — 管理表（Excel）の雛形を作る。

**列の定義は master.py の定数から組み立てる。** 雛形と読み取りで列名を別々に書くと、
片方だけ直したときに「管理表を編集したのに読まれない」という分かりにくい失敗になる。

雛形には記入例を2行入れておく。空の表を渡されるより、1行埋まっている方が
何をどう書くかが伝わる（**使う前に消す**ことを「記入方法」シートに書いてある）。
"""

from pathlib import Path

from ...toolbox.excel import ExcelWriter
from .master import (
    ENABLED_COLUMN,
    FOLDER_COLUMN,
    KEY_COLUMN,
    ON_DEMAND,
    SCHEDULE_COLUMN,
    SCHEDULED,
    SHEET_NAME,
    SUMMARY_COLUMN,
    URL_COLUMN,
)

# 管理表の列（この順で並べる）
COLUMNS = (
    KEY_COLUMN,
    SUMMARY_COLUMN,
    URL_COLUMN,
    SCHEDULE_COLUMN,
    FOLDER_COLUMN,
    ENABLED_COLUMN,
)

TABLE_NAME = "レポート管理表"
GUIDE_SHEET_NAME = "記入方法"

_DOMAIN = "https://example--sandbox.sandbox.my.salesforce.com/lightning/r/Report"
_EXAMPLE_URL = f"{_DOMAIN}/00O5g00000ABCDE/view"
# 2行目は別のレポートにする（同じ URL を並べると、check が重複として報告してしまう）
_EXAMPLE_URL_2 = f"{_DOMAIN}/00O5g00000FGHIJ/view"
_EXAMPLES = (
    [1001, "顧客一覧", _EXAMPLE_URL, SCHEDULED, r"\\server\案件集計\input", "有効"],
    [1002, "売上実績", _EXAMPLE_URL_2, ON_DEMAND, r"\\server\売上帳票\input", "有効"],
)

_GUIDE = (
    ["列", "何を書くか", "書き方の例"],
    [
        KEY_COLUMN,
        "社内で決める管理番号。Salesforce のレポート ID ではありません。"
        "参照先のレポートを差し替えても、この番号は変えません（プログラムがこの番号で引きます）",
        "1001",
    ],
    [
        SUMMARY_COLUMN,
        "人が読んで何のレポートか分かる説明。保存するファイル名にも使われます",
        "顧客一覧",
    ],
    [
        URL_COLUMN,
        "Salesforce でレポートを開いたときのアドレスを、そのまま貼り付けてください。"
        "レポート ID を抜き出す必要はありません（プログラムが取り出します）",
        _EXAMPLE_URL,
    ],
    [
        SCHEDULE_COLUMN,
        f"「{SCHEDULED}」は毎日決まった時刻にまとめて取ります。"
        f"「{ON_DEMAND}」は、使うプログラムから呼ばれたときだけ取ります",
        SCHEDULED,
    ],
    [
        FOLDER_COLUMN,
        "落としたファイルを置くフォルダ。**フォルダが無いとエラーになります**"
        "（打ち間違いに気づけるよう、勝手には作りません）",
        r"\\server\案件集計\input",
    ],
    [
        ENABLED_COLUMN,
        "使わなくなったら「無効」にしてください。**行は消さない**でください"
        "（過去の履歴と対応が取れなくなります）",
        "有効",
    ],
    [],
    ["注意", "1行目の見出しは変えないでください（プログラムが列名で読みます）", ""],
    ["", "管理番号（ID）が重複しているとエラーになります", ""],
    ["", "記入例の2行は、実際に使うときに消してください", ""],
)


def create_master_template(path: str | Path) -> Path:
    """管理表の雛形を作って、そのパスを返す。

    Args:
        path: 作成先（.xlsx）。

    Returns:
        作成したファイルのパス。
    """
    path = Path(path)
    with ExcelWriter.create(path, SHEET_NAME) as book:
        _write_master_sheet(book)
        _write_guide_sheet(book)
        book.save()
    return path


def _write_master_sheet(book: ExcelWriter) -> None:
    """管理表シート（見出し・記入例・テーブル）を書く。"""
    sheet = book.sheet(SHEET_NAME)
    sheet.write_row(1, list(COLUMNS))
    for offset, example in enumerate(_EXAMPLES):
        sheet.write_row(offset + 2, example)

    last_column = chr(ord("A") + len(COLUMNS) - 1)
    last_row = len(_EXAMPLES) + 1
    sheet.add_table(TABLE_NAME, f"A1:{last_column}{last_row}")
    sheet.auto_width()
    sheet.freeze_header()


def _write_guide_sheet(book: ExcelWriter) -> None:
    """記入方法シートを書く。非エンジニアが1枚で分かるようにする。"""
    sheet = book.add_sheet(GUIDE_SHEET_NAME)
    for row_number, row in enumerate(_GUIDE, start=1):
        if row:
            sheet.write_row(row_number, row)
    for column in ("A", "B", "C"):
        sheet.set_bold(1, column)
    sheet.auto_width(max_width=80)
    sheet.freeze_header()
