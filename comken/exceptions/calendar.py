"""comken/exceptions/calendar.py — 祝日カレンダーに関する例外。

内閣府の祝日 CSV の読み取りに関する失敗をまとめる。
「今日が営業日か」を判定する側は基本的に例外を上げない設計で、
ここに来るのは「祝日データの用意に失敗した」という業務運用の場面に限定する。
"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class CalendarError(ComkenError):
    """祝日カレンダーに関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class CalendarSourceError(CalendarError):
    """祝日データの読み取りに失敗した

    内閣府の CSV 形式が変わったなどの理由で、祝日を 1件も抽出できない場合に上げる。

    発生箇所: comken.core.calendar の csv_source

    対処:
        内閣府の CSV の場合: 内閣府の仕様変更。管理者へ連絡する
    """

    def __init__(self, source: str, reason: str) -> None:
        super().__init__(f"祝日データを読み取れませんでした: {source}\n{reason}")


class CalendarFormatError(CalendarSourceError):
    """内閣府 CSV 以外のファイルや壊れたファイルを内閣府 CSV として読み込もうとした

    発生箇所: comken.core.calendar.csv_source の load_cabinet_office_csv

    対処:
        内閣府の syukujitsu.csv を直接取得し直す。文字コードは CP932 (Shift_JIS)
    """

    def __init__(self, path: Path | str, detail: str) -> None:
        super().__init__(source=str(path), reason=detail)


class BusinessDayNotFoundError(CalendarError):
    """営業日が見つからなかった

    月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
    その月に営業日が 1 日も無いとき、祝日データ欠落などで 30 日探索しても
    次の営業日にたどり着けなかったときに送る。
    いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
    起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
    顕在化させる必要がある。

    発生箇所: comken.core.calendar
        - nth_business_day_of_month（n が月の営業日数超え、または n < 1）
        - first_business_day_of_month / last_business_day_of_month
          （その月に営業日が 1 日も無い）
        - business_day_after / business_day_before /
          business_day_on_or_after / business_day_on_or_before
          （30 日の探索上限に達した）

    対処:
        n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
        確認する、社内管理表（会社休日）が広範囲に登録されていないか確認する
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
