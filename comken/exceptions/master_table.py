"""comken/exceptions/master_table.py — Excel の表を設定として読むときの例外。

非エンジニアが編集する表なので、**どの行のどの列が、なぜ駄目なのか**を必ず示す。
"""

from pathlib import Path

from comken.exceptions.base import ComkenError


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
