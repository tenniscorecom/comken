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

    発生箇所: comken.core.holidays の csv_source

    対処:
        内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"祝日データを読み取れませんでした: {source}\n{reason}")


class HolidayCalendarExpiredError(HolidayCalendarError):
    """祝日データの収録期間が今日の業務日付を超えている

    収録最終日 <= 今日になると「今日以降が祝日かどうか判定できない」ため、
    期限切れを専用例外で知らせる。

    発生箇所: comken.core.holidays.calendar の HolidayCalendar

    対処:
        内閣府の祝日 CSV を更新する（自動取得の場合は次の実行で反映される）
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

    発生箇所: comken.core.holidays.csv_source の load_cabinet_office_csv

    対処:
        内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)
    """

    def __init__(self, path: Path | str, detail: str) -> None:
        super().__init__(source=str(path), reason=detail)


class BusinessDayNotFoundError(HolidayCalendarError):
    """営業日が見つからなかった

    月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
    その月に営業日が 1 日も無いとき、祝日データ欠落などで 400 日探索しても
    次の営業日にたどり着けなかったときに送る。
    いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
    起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
    顕在化させる必要がある。

    発生箇所: comken.core.holidays.calendar の HolidayCalendar
        - nth_business_day_of_month（n が月の営業日数超え、または n < 1）
        - first_business_day_of_month / last_business_day_of_month
          （その月に営業日が 1 日も無い）
        - business_day_after / business_day_before /
          business_day_on_or_after / business_day_on_or_before
          （400 日の探索上限に達した）

    対処:
        n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
        確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
