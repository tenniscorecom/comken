"""comken/exceptions/holidays.py — 祝日カレンダーに関する例外。

旧 calendar.py を改名したもの。会社用カレンダー CSV の読み取り失敗をまとめる。"""

from comken.exceptions.base import ComkenError


class HolidayError(ComkenError):
    """祝日カレンダーに関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class WorkdayNotFoundError(HolidayError):
    """営業日が見つからなかった

    月の途中で「指定した月の営業日数を超える n 番目」を求めたとき、
    その月に営業日が 1 日も無いとき、祝日データ欠落などで 30 日探索しても
    次の営業日にたどり着けなかったときに送る。
    いずれも「カレンダー側がおかしい」または「指定値が暦と合わない」場合に
    起き、業務ロジック側のミスではないので、呼び出し側で握り潰さずユーザーに
    顕在化させる必要がある。

    発生箇所: comken.core.holidays
        - nth_workday（n が月の営業日数超え、または n < 1）
        - first_workday / last_workday（その月に営業日が 1 日も無い）
        - workday / workday_on_or_after / workday_on_or_before
          （30 日の探索上限に達した）

    対処:
        n をその月の営業日数以下に直す、対象月の祝日に過不足がないか
        確認する、社内休日（会社用カレンダーCSV）が広範囲に登録されていないか確認する
    """

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
