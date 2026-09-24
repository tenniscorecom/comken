"""comken/core/calendar/_calendar.py — カレンダー本体（実装詳細）。

モジュール名は ``_calendar.py`` にしておき、``comken.core.calendar``
（パッケージ本体）と ``calendar`` （クラス名）が被らないようにしている。

実行時は ``comken/core/calendar/data/company_calendar.csv`` を**読むだけ**で
国民の祝日＋会社休日を判定する。会社休日のルール判定・内閣府 CSV の解析・
計算ソース・``approximate``・``Holiday`` 値オブジェクトは持たない。
**実行時は内閣府 CSV も会社休日のルールも知らない。** 生成ツール
（``tools/build_calendar.py``）だけがそれらを持ち、生成物である
``company_calendar.csv`` に焼き込む。

ネット系依存（requests）はこのモジュールには入らない。
"""

from __future__ import annotations

import csv
import datetime as _dt
import logging
from pathlib import Path
from typing import Final

from comken.core.clock import month_end, month_start, today
from comken.exceptions import BusinessDayNotFoundError, CalendarFormatError

logger = logging.getLogger(__name__)

# 1ヶ月未満で切れる場合に警告する日数。30 日 ≒ 「切れた瞬間まで気付かない」を避ける閾値
EXPIRING_WARNING_DAYS = 30

# 「次の営業日」を探すときの日数上限。祝日データが壊れていたり、社内管理表に
# 会社休日が広範囲に登録されていたりすると無限ループになるため、必ず上限を切る。
BUSINESS_DAY_SEARCH_LIMIT = 30


# 生成された「会社用カレンダー CSV」のパス。git 管理下の正本。
# Python 実行時と VBA 側の両方が同じファイルを読む
# （comken は共有サーバーへ直接参照で配布されるため）。
CALENDAR_CSV_PATH: Final[Path] = Path(__file__).parent / "data" / "company_calendar.csv"

# ── テスト用差し替え口 ────────────────────────────────────────────────────
# 既定カレンダーを遅延生成する代わりに、テストから ``_Calendar`` を直接差し込める
# ようにする。``None`` を渡すと次の呼び出しで ``CALENDAR_CSV_PATH`` から
# 遅延生成される（=既定カレンダー）。
_singleton: _Calendar | None = None


def _set_calendar_for_test(calendar: _Calendar | None) -> None:
    """テストで既定カレンダーを差し替えるための **非公開** 入口。

    通常は使わない。テストが個別の ``_Calendar`` を組み立てて
    ``is_business_day`` などの公開関数の挙動を確かめたいときに使う。
    ``None`` を渡すと遅延生成に戻る（次の ``_resolve_singleton()`` で
    ``CALENDAR_CSV_PATH`` から読み直す）。
    """
    global _singleton
    _singleton = calendar


def _resolve_singleton() -> _Calendar:
    """プロセスで遅延生成された ``_Calendar`` を返す（差し替えがあれば優先）。"""
    global _singleton
    if _singleton is None:
        _singleton = _Calendar.load(CALENDAR_CSV_PATH)
    return _singleton


# ── 公開関数 ────────────────────────────────────────────────────────────


def warn_if_calendar_expiring_soon() -> None:
    """既定の会社用カレンダーの収録期限が近ければ、起動時に警告する。

    「収録最終日」（=``company_calendar.csv`` の最後の行）が今日から
    ``EXPIRING_WARNING_DAYS`` 未満で WARNING ログを 1 度だけ出す。
    同じ日に複数回呼んでも警告は 1 日 1 回だけ（``_maybe_warn_expiring``
    の重複防止をそのまま使う）。年 1 回の内閣府 CSV 更新が必要な時期を
    検知するのが目的。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(today())


def is_holiday(target: _dt.date) -> bool:
    """``target`` が国民の祝日または会社休日に当たれば ``True``。

    ``company_calendar.csv`` の収録範囲（内閣府 CSV の最初の年〜最後の年）
    外の日付は国民の祝日も会社休日も付かない（常に ``False``）。範囲を延ばす
    には内閣府 CSV を入れ替えて ``python tools\\build_calendar.py`` で
    再生成する。
    """
    return _resolve_singleton().is_holiday(target)


def holiday_name(target: _dt.date) -> str | None:
    """``target`` の祝日・会社休日名称を返す。祝日でも会社休日でもなければ
    ``None``。
    """
    return _resolve_singleton().holiday_name(target)


def is_business_day(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> bool:
    """``target`` が営業日なら ``True``。

    ``company_calendar.csv`` の判定で国民の祝日＋会社休日に当たれば休業。
    ``skip_weekends=True``（既定）なら土曜・日曜も休業扱いにする。
    ``False`` を渡すと、土曜・日曜であっても祝日でなければ「営業日」と
    判定される（振替休日を平日扱いするシナリオ向け）。

    「収録済み最終日 <= target」のときは期限切れを WARNING ログで 1度だけ
    通知する。判定自体は通常どおり行う（誤って平日扱いにならないよう、
    **収録範囲外は祝日ではない側に倒す**）。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(target)
    if skip_weekends and target.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
        return False
    return not cal.is_holiday(target)


def business_day_after(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より後で最初の営業日（``target`` 自身を含まない）。

    ``target`` が営業日でも翌営業日を返す。収録範囲外でも日付は進むが、
    祝日判定は「祝日ではない」と扱う。期限切れの警告は入口で 1度だけ出す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった（祝日データ欠落・社内休日広範囲など）。
    """
    cal = _resolve_singleton()
    cal._maybe_warn_expiring(target)
    return _search_business_day(
        start=target + _dt.timedelta(days=1),
        step_days=1,
        skip_weekends=skip_weekends,
    )


def business_day_before(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より前で最初の営業日（``target`` 自身を含まない）。

    ``target`` が営業日でも前営業日を返す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    return _search_business_day(
        start=target - _dt.timedelta(days=1),
        step_days=-1,
        skip_weekends=skip_weekends,
    )


def business_day_on_or_after(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以降で最初の営業日（``target`` を含む）。

    ``target`` が営業日なら ``target`` をそのまま返す。
    営業日でなければ、``business_day_after`` と同じ動きで翌日以降を探す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    if is_business_day(target, skip_weekends=skip_weekends):
        return target
    return business_day_after(target, skip_weekends=skip_weekends)


def business_day_on_or_before(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以前で最初の営業日（``target`` を含む）。

    ``target`` が営業日なら ``target`` をそのまま返す。
    営業日でなければ、``business_day_before`` と同じ動きで前日以前を探す。

    Raises:
        BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
            営業日が見つからなかった。
    """
    if is_business_day(target, skip_weekends=skip_weekends):
        return target
    return business_day_before(target, skip_weekends=skip_weekends)


def first_business_day_of_month(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最初の営業日。

    Raises:
        BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
    """
    start = month_start(target)
    try:
        return business_day_on_or_after(start, skip_weekends=skip_weekends)
    except BusinessDayNotFoundError as error:
        raise BusinessDayNotFoundError(
            f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
        ) from error


def last_business_day_of_month(
    target: _dt.date,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最後の営業日。

    月末が土日・祝日のときは直前の営業日に遡る（例: 8/31 が日曜なら 8/29 金）。

    Raises:
        BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
    """
    end = month_end(target)
    try:
        return business_day_on_or_before(end, skip_weekends=skip_weekends)
    except BusinessDayNotFoundError as error:
        raise BusinessDayNotFoundError(
            f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
        ) from error


def nth_business_day_of_month(
    target: _dt.date,
    n: int,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の第 ``n`` 営業日を返す（``n`` は 1 始まり）。

    月の初日から数えて ``n`` 番目の営業日。
    その月の営業日数を超える ``n`` を渡すと ``BusinessDayNotFoundError``。

    Raises:
        BusinessDayNotFoundError: ``n`` が 1 未満、またはその月の営業日数を超える。
    """
    if n < 1:
        raise BusinessDayNotFoundError(
            f"第 n 営業日の n は 1 以上で指定してください（指定値: {n}）"
        )
    start = month_start(target)
    end = month_end(target)
    cursor = start
    for _ in range(n):
        try:
            cursor = business_day_on_or_after(cursor, skip_weekends=skip_weekends)
        except BusinessDayNotFoundError as error:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に {n} 営業日は存在しません: {error}"
            ) from error
        if cursor > end:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に {n} 営業日は存在しません"
                f"（最終営業日: {end}）"
            )
        cursor = cursor + _dt.timedelta(days=1)
    # ループを抜けた時点で ``cursor`` は「n 番目の翌営業日」を指している。
    # ひとつ戻して返す。
    return cursor - _dt.timedelta(days=1)


def add_business_days(
    target: _dt.date,
    n: int,
    *,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。

    ``n == 0`` のときは ``target`` を**そのまま**返す（``target`` が営業日か
    どうかを問わない）。これは Excel の ``WORKDAY`` と同じ挙動で、
    「今日から N 営業日後」を組み立てるときに条件分岐を書かなくて済む。

    例: 2024/5/2（木、祝日前日）に ``add_business_days(d, 1)`` を呼ぶと
    2024/5/7（火、5/3〜5/6 が祝日＋土日）を返す。

    Raises:
        BusinessDayNotFoundError: 探索が ``BUSINESS_DAY_SEARCH_LIMIT`` に達した。
    """
    if n == 0:
        return target
    # ``target`` を 0 営業日目と数え、``n`` 回「次の（前の）営業日」へ進める。
    # ``target`` が営業日のとき n=1 で翌日営業日、非営業日のときでも
    # ``business_day_after`` が翌営業日にスナップするので結果は同じになる。
    cursor = target
    steps = n if n > 0 else -n
    for _ in range(steps):
        if n > 0:
            cursor = business_day_after(cursor, skip_weekends=skip_weekends)
        else:
            cursor = business_day_before(cursor, skip_weekends=skip_weekends)
    return cursor


# ── 内部実装 ────────────────────────────────────────────────────────────


class _Calendar:
    """``company_calendar.csv`` を読み込んで保持するカレンダー本体。

    国民の祝日と会社休日を区別せず、``{日付: 名称}`` の単純な辞書に保持する
    （生成ツールが「国民の祝日が先勝ち」で1行に焼き込んでいるため、実行時に
    優先順位の判定は不要）。
    """

    def __init__(self, holidays: dict[_dt.date, str]) -> None:
        self._holidays = holidays
        # 期限切れ警告を「同じ日に 1度だけ」出すためのキャッシュキー
        self._expiry_warned_on: _dt.date | None = None

    @classmethod
    def load_default(cls) -> _Calendar:
        """``CALENDAR_CSV_PATH``（``company_calendar.csv``）を読んで返す。"""
        return cls.load(CALENDAR_CSV_PATH)

    @classmethod
    def load(cls, path: str | Path) -> _Calendar:
        """``company_calendar.csv`` 形式のファイルを読み ``_Calendar`` を返す。

        列は ``date`` / ``name`` の 2 列のみ。文字コードは UTF-8 BOM 付き
        （Excel・VBA 双方で文字化けしないため）。ヘッダーが違ったり日付が
        解釈できない行があれば ``CalendarFormatError`` を上げる。
        """
        file_path = Path(path)
        if not file_path.exists():
            raise CalendarFormatError(
                file_path,
                "ファイルが存在しません。"
                "tools/build_calendar.py を実行して company_calendar.csv を生成してください。",
            )
        # 文字コードは UTF-8 BOM 付き（書き出し側 fix）。CP932 で読もうとすると
        # 日本語が化けるので、明示的に utf-8-sig を渡す
        with file_path.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.reader(file)
            try:
                header = next(reader)
            except StopIteration:
                raise CalendarFormatError(
                    file_path, "ヘッダー行がありません（date, name が必要です）。"
                ) from None
            if [h.strip() for h in header] != ["date", "name"]:
                raise CalendarFormatError(
                    file_path,
                    f"ヘッダーが date, name ではありません: {header!r}",
                )
            holidays: dict[_dt.date, str] = {}
            for line_number, row in enumerate(reader, start=2):
                if not row or (len(row) == 1 and not row[0]):
                    continue
                if len(row) < 2:
                    raise CalendarFormatError(
                        file_path,
                        f"{line_number} 行目の列数が不足しています: {row!r}",
                    )
                date_text = row[0].strip()
                name = row[1].strip()
                if not name:
                    # 空の名前は「国民の祝日が先勝ちで選ばれた会社休日側」が
                    # 生成段階で消えているため、ここでは警告のみ
                    logger.warning("company_calendar.csv の空名称をスキップ: %s", date_text)
                    continue
                try:
                    parsed = _dt.datetime.strptime(  # noqa: DTZ007  # 業務日付として naive で扱う
                        date_text, "%Y-%m-%d"
                    ).date()
                except ValueError as error:
                    raise CalendarFormatError(
                        file_path,
                        f"{line_number} 行目の日付を解釈できません: {date_text!r}",
                    ) from error
                holidays[parsed] = name
        if not holidays:
            raise CalendarFormatError(
                file_path,
                "日付として解釈できる行が 1件もありませんでした。"
                "tools/build_calendar.py を再実行してください。",
            )
        return cls(holidays)

    def is_holiday(self, target: _dt.date) -> bool:
        """``target`` が ``company_calendar.csv`` に登録されていれば ``True``。"""
        return target in self._holidays

    def holiday_name(self, target: _dt.date) -> str | None:
        """``target`` の祝日・会社休日名称を返す。無ければ ``None``。"""
        return self._holidays.get(target)

    def last_known_date(self) -> _dt.date | None:
        """収録済みのうち最も新しい日付。無ければ ``None``。"""
        if not self._holidays:
            return None
        return max(self._holidays)

    def days_until_expiry(self, today: _dt.date) -> int:
        """``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

        収録済み祝日が無いと ``-1``。
        """
        last = self.last_known_date()
        if last is None:
            return -1
        return (last - today).days

    def expires_after(self, target: _dt.date) -> bool:
        """``target`` が収録済み最終日以降なら ``True``。"""
        last = self.last_known_date()
        if last is None:
            return True
        return target >= last

    def _maybe_warn_expiring(self, today: _dt.date) -> None:
        """期限切れが近いとき、**同じ日付で 1度だけ** WARNING ログを出す。"""
        if self._expiry_warned_on == today:
            return
        remaining = self.days_until_expiry(today)
        if 0 <= remaining < EXPIRING_WARNING_DAYS:
            last = self.last_known_date()
            logger.warning(
                "会社用カレンダーの収録期限が近づいています: 残り %d 日"
                "（最終収録日: %s）。"
                "内閣府の syukujitsu.csv をダウンロードして"
                "tools/calendar_data/syukujitsu.csv を上書きし、"
                "python tools\\build_calendar.py を実行して"
                "comken/core/calendar/data/company_calendar.csv を更新し、"
                "コミット・タグ打ちして配布してください"
                "（docs/calendar.md の「年1回の更新手順」参照）。",
                remaining,
                last,
            )
            self._expiry_warned_on = today


def _search_business_day(
    *,
    start: _dt.date,
    step_days: int,
    skip_weekends: bool,
) -> _dt.date:
    """``start`` から ``step_days`` 日ずつ進め（または戻し）て最初の営業日を探す。

    ``BUSINESS_DAY_SEARCH_LIMIT`` を超えると ``BusinessDayNotFoundError``
    を上げる（祝日データが壊れている／社内休日が広範囲なときの無限ループ防止）。
    """
    if step_days == 0:
        raise ValueError("step_days には 0 以外の値を渡してください")
    cursor = start
    for _ in range(BUSINESS_DAY_SEARCH_LIMIT):
        if is_business_day(cursor, skip_weekends=skip_weekends):
            return cursor
        cursor += _dt.timedelta(days=step_days)
    raise BusinessDayNotFoundError(
        f"{BUSINESS_DAY_SEARCH_LIMIT} 日探索しても営業日が見つかりません。"
        "祝日データに過不足がないか、社内休日が広範囲に登録されていないか確認してください。"
    )
