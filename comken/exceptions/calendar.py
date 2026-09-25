"""comken/exceptions/calendar.py — 祝日カレンダーに関する例外。

会社用カレンダー CSV（``comken/core/calendar/data/company_calendar.csv``）
の読み取り失敗をまとめる。生成物なので壊れる場面は限定的だが、ファイルが
存在しない・ヘッダーが違う・日付が解釈できない、といった業務運用の場面に
備えて明示的に例外を定義する。
"""

from pathlib import Path

from comken.exceptions.base import ComkenError


class CalendarError(ComkenError):
    """祝日カレンダーに関するエラー

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class CalendarFormatError(CalendarError):
    """会社用カレンダーCSV 以外のファイルや壊れたファイルを読み込もうとした

    発生箇所: comken.core.calendar._calendar の _Calendar.load

    対処:
        ``python -m comken.core.calendar.build`` を実行して
        ``comken/core/calendar/data/company_calendar.csv`` を再生成する。
        内閣府の ``syukujitsu.csv`` 形式変更が原因の場合は
        ``comken.core.calendar.build`` 側の解析ロジックを直す
    """

    def __init__(self, path: Path | str, detail: str) -> None:
        super().__init__(f"会社用カレンダーCSV を読み取れませんでした: {path}\n{detail}")


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
        確認する、社内休日（会社用カレンダーCSV）が広範囲に登録されていないか確認する
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
