"""comken/exceptions/dates.py — 日付・祝日まわりの例外。

祝日カレンダー（``HolidayError`` / ``WorkdayNotFoundError``）と、
日付書式（``DateFormatError``）をまとめる。
"""

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

    発生箇所: comken.core.dates._holidays
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


class DateFormatError(ComkenError):
    """日付書式の変換に失敗した

    ``parse_yyyymmdd()`` が、入力が 8 桁の数字列でない、または数字列でも
    存在しない日付（``"20260230"`` など）のときに送る。
    ``parse_cell_date()`` のように読めなかった値を ``None`` で返すのではなく、
    **明示的に変換を頼んだ呼び出し側へ失敗を返す**ための例外。

    対処:
        入力を見直す（区切り文字付き・全角・桁過不足は無効）。
        8 桁の数字列 ``YYYYMMDD`` に直す。
        値が ``None`` かもしれないときは ``parse_cell_date()`` を使う（こちらは
        読めなければ ``None`` を返す方針）。
    """
