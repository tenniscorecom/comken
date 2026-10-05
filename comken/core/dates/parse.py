"""comken/core/dates/parse.py — セルの値やファイル名から日付を読み取る。

parse_cell_date() は Excel・CSV のセル（date / datetime / 文字列）を date に
揃え、読めなければ None を返す。date_in_name() / dates_in_name() は
ファイル名の中の日付（20260729・2026-07-29・2026_07_29・2026.07.29）を読む。
"""

import datetime
import re

# 「日」列が文字列で入っていた場合に受け付ける書き方。
# Excel / CSV から読む業務シートでよくある表記をカバーする。
# 新しい書式を増やすときは**ここを変えても会社用カレンダーCSV の日付パーサ
# （``comken.core.dates.holidays._Holidays.load`` の日付解釈）には影響しない**。
# 祝日 CSV は配布フォーマットの制約で 2 形式に固定しており、 緩めた
# 場合に「内閣府以外のファイルを取り違えても気付かない」リスクがあるため
# 別口のままで揃えていない。
_DATE_TEXT_FORMATS: tuple[str, ...] = (
    "%Y/%m/%d",
    "%Y-%m-%d",
    "%Y年%m月%d日",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_cell_date(value: object) -> datetime.date | None:
    """セルの値を ``datetime.date`` に変換する。読めなければ `` ``None`` 。

    Excel から ``Table`` 行を読むとき、 日付列は

    - ``datetime.datetime`` オブジェクト（Excel の日付型セル）
    - ``datetime.date`` オブジェクト
    - 文字列（手入力・他システムからのエクスポート）

    のどれでも来うる。 それぞれを ``date`` に揃え、 **読めなかった値は
    ``None`` を返す**（例外にはしない）。 利用側は ``None`` を「対象外の行」
    として数えて ``WARNING`` に出す形に向いている（読み込みは止めずに、
    何件スキップしたかだけ報告する業務運用）。

    受け付ける書式は ``_DATE_TEXT_FORMATS`` に固定。 新しい書式を足すときは
    ここにタプル要素として追加する（会社用カレンダーCSV の日付解釈とは別口
    なので、 祝日 CSV の安全弁を緩めない）。
    """
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for date_format in _DATE_TEXT_FORMATS:
        try:
            return datetime.datetime.strptime(text, date_format).date()  # noqa: DTZ007  # 業務日付として naive で扱う
        except ValueError:
            continue
    return None


# ファイル名に含まれる日付らしい数字（20260729 / 2026-07-29 / 2026_07_29 / 2026.07.29）。
# 前後を数字で挟まれたものは日付とみなさない（社員番号・伝票番号の一部を拾わないため）
_DATE_IN_NAME = re.compile(r"(?<!\d)([0-9]{4})([-_.]?)([0-9]{2})\2([0-9]{2})(?!\d)")


def dates_in_name(name: str) -> list[datetime.date]:
    """ファイル名に含まれる日付を **すべて** 出現順で返す。無ければ空リスト。

    ``_DATE_IN_NAME`` 正規表現で日付らしい数字（``20260729`` / ``2026-07-29`` /
    ``2026_07_29`` / ``2026.07.29``）を抜き出し、``date`` に変換できたものだけを
    順番に並べる。``20261345`` のように数字は揃っていても日付として成立しないものは
    結果に含まない。
    """
    results: list[datetime.date] = []
    for match in _DATE_IN_NAME.finditer(name):
        year, _, month, day = match.groups()
        try:
            results.append(datetime.date(int(year), int(month), int(day)))
        except ValueError:
            continue  # 20261345 のように数字は揃っていても日付として成立しないもの
    return results


def date_in_name(name: str) -> datetime.date | None:
    """ファイル名に含まれる **最初の日付** を返す。日付が無ければ None。

    1つのファイル名に日付が複数あるときは、先に出てくる方を使う。
    ファイル名の日付とファイル内容の日付を突き合わせる業務で使うため公開している。
    すべての日付が要るときは ``dates_in_name`` を使う。
    """
    dates = dates_in_name(name)
    return dates[0] if dates else None
