"""comken/exceptions/holiday.py — 祝日判定ライブラリに関する例外。

内閣府の祝日 CSV の取得・読み取り・管理表のマージに関する失敗をまとめる。
「今日が営業日か」を判定する側は基本的に例外を上げない設計で、
ここに来るのは「祝日データの用意に失敗した」という業務運用の場面に限定する。
"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class HolidayCalendarError(ComkenError):
    """祝日カレンダーに関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class HolidayCalendarFetchError(HolidayCalendarError):
    """内閣府の祝日 CSV を取得できない

    オフライン環境・社内ネットワークの制約・内閣府サイトの保守などの理由で
    ダウンロードが失敗する。**ただしキャッシュが残っている場合は警告ログのみで動く**
    （cached フラグで運用側が検知できる）。

    発生箇所: comken.toolbox.holidays.sources.cabinet_office の CabinetOfficeCSVSource

    対処:
        ネットワーク接続と社内プロキシの設定を確認する。
        それでも直らない場合は、保存済みのキャッシュで当面動かすか、
        管理表（Excel）に会社休日を登録して代用する
    """

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"内閣府の祝日 CSV を取得できませんでした: {url}\n"
            f"{reason}\n"
            "ネットワーク接続と社内プロキシの設定を確認してください。"
        )


class HolidayCalendarSourceError(HolidayCalendarError):
    """祝日データの読み取りに失敗した

    内閣府の CSV 形式が変わった・社内管理表のシート名が違う・列が無い・
    文字化けしたなどの理由で、祝日を 1件も抽出できない場合に上げる。

    発生箇所: comken.toolbox.holidays の csv_source / sources/master_table

    対処:
        内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する
        管理表の場合: シート名と列名（"日付" / "名称"）を確認する
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"祝日データを読み取れませんでした: {source}\n{reason}")


class HolidayCalendarExpiredError(HolidayCalendarError):
    """祝日データの収録期間が今日の業務日付を超えている

    収録最終日 <= 今日になると「今日以降が祝日かどうか判定できない」ため、
    期限切れを専用例外で知らせる。

    発生箇所: comken.toolbox.holidays.calendar の HolidayCalendar

    対処:
        内閣府の祝日 CSV を更新する（自動取得の場合は次の実行で反映される）、
        または管理表に直近の祝日を追加する
    """

    def __init__(self, today: object, last_known: object) -> None:
        super().__init__(
            f"収録済みの祝日が今日の日付までカバーしていません。\n"
            f"今日: {today}\n"
            f"収録最終日: {last_known}\n"
            "内閣府の祝日 CSV を更新するか、管理表に祝日を追加してください。"
        )


class HolidayCalendarFormatError(HolidayCalendarSourceError):
    """内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした

    発生箇所: comken.toolbox.holidays.csv_source の load_cabinet_office_csv

    対処:
        内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)
    """

    def __init__(self, path: Path | str, detail: str) -> None:
        super().__init__(source=str(path), reason=detail)
