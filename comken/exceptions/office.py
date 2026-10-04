"""comken/exceptions/office.py — Excel / Access / Outlook / Windows 操作に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class ExcelError(ComkenError):
    """Excel に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class SheetNotFoundError(ExcelError):
    """指定した名前のシートがない

    発生箇所: Excel.sheet() / Excel.data_sheet()

    対処:
        Excel を開いて、下のシート名（タブ）が変わっていないか確認する。変えた場合は元に戻す
    """

    def __init__(self, name: str, sheets: list[str]) -> None:
        super().__init__(f"シートが見つかりません: {name}  存在するシート: {sheets}")


class ExcelApplicationNotAvailableError(ExcelError):
    """Excel を起動できない

    Excel が入っていない PC で、Excel 本体が要る操作をしようとした。
    次のときに要る。

    - 数式の計算結果を読む（計算結果がファイルに保存されていない場合）
    - マクロを実行する、パスワード付きで保存する

    **読み書きだけなら Excel は要らない**（openpyxl で動く）。

    発生箇所: comken.toolbox.windows の ExcelError

    対処:
        この PC に Excel が入っているか確認する。入れられない PC で動かすなら、
        数式ではなく値で書いてもらう（管理表なら、数式の結果を貼り付けてもらう）
    """

    def __init__(self, path: Path, error: Exception) -> None:
        super().__init__(
            f"Excel を起動できませんでした: {path}\n"
            f"（{error}）\n"
            "この PC に Excel が入っているか確認してください。\n"
            "数式の計算結果を読むときだけ Excel が必要です。"
            "数式をやめて値で書いてもらえば、Excel なしで動きます。"
        )


class AccessError(ComkenError):
    """Access に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class OutlookError(ComkenError):
    """Outlook 関連エラーの分類。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class WindowNotFoundError(ComkenError):
    """指定したウィンドウが見つからない

    発生箇所: ``WindowHandler.__init__``

    対処:
        対象ウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認する
    """

    def __init__(self, title: str) -> None:
        super().__init__(
            f"ウィンドウが見つかりません: {title}\n"
            "対象のウィンドウが開いているか、タイトル（完全一致）が想定どおりかを確認してください。"
        )
