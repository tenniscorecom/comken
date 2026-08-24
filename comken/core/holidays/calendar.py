"""comken/core/holidays/calendar.py — 祝日カレンダー本体（facade から呼ばれる）。

データ形式は ``Holiday`` 1個に統一し、内閣府 CSV・管理表・テスト用 iterable など
入手経路（``HolidaySource``）を差し替え可能にする。判定ロジックはここに集約され、
``is_holiday`` / ``is_business_day`` / ``business_day_after`` / ``expires_after`` を提供する。

ネット系依存（requests）はこのモジュールには入らない。
内閣府からの取得は ``sources/cabinet_office.py`` 側に閉じ込めている。
"""

import datetime as _dt
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol, runtime_checkable

from comken.core.clock import month_end, month_start
from comken.exceptions import BusinessDayNotFoundError, HolidayCalendarFetchError

logger = logging.getLogger(__name__)

# 1ヶ月未満で切れる場合に警告する日数。30 日 ≒ 「切れた瞬間まで気付かない」を避ける閾値
EXPIRING_WARNING_DAYS = 30

# 「次の営業日」を探すときの日数上限。祝日データが壊れていたり、社内管理表に
# 会社休日が広範囲に登録されていたりすると無限ループになるため、必ず上限を切る。
BUSINESS_DAY_SEARCH_LIMIT = 400


@dataclass(frozen=True)
class Holiday:
    """祝日の1件。日付と名称だけを運ぶシンプルな箱。

    Attributes:
        date: 祝日の日付（時刻・タイムゾーンは持たない業務日付）。
        name: 祝日の日本語名称（例: "建国記念の日"）。
        approximate: ``True`` なら、計算式など内閣府発表と ±1 日前後する
            可能性がある値。``HolidayCalendar.is_holiday`` などで該当 Holiday
            を返したときに WARNING ログを出して、業務フローを止めずに気づける
            ようにする。デフォルトは ``False``（内閣府 CSV 由来または確実な
            計算結果）。
    """

    date: _dt.date
    name: str
    approximate: bool = False


@runtime_checkable
class HolidaySource(Protocol):
    """祝日を 1セット取り出せる仕組みの共通インタフェース。

    内閣府の ``CabinetOfficeCSVSource`` や ``ComputedHolidaySource`` / 会社の
    ``CompanyHolidaySource`` の両方がこれを実装するため、利用側は入手経路を
    意識せずに ``from_sources`` に渡せる。

    この Protocol はメソッドの型を ``Iterable[Holiday]`` に固定する。
    ``load()`` を呼んだその瞬間に取得が走る（キャッシュは実装側で持つ）のが
    一貫していて読みやすい。実装が iterable を返したい場合は
    中で ``list()`` してから返してもよい。
    """

    def load(self) -> Iterable[Holiday]:
        """祝日セットを取り出して ``Iterable[Holiday]`` で返す。"""
        ...


@runtime_checkable
class RefreshableHolidaySource(Protocol):
    """TTL を無視して強制再取得できる祝日 source（例: 内閣府の ``CabinetOfficeCSVSource``）。

    ``HolidayCalendar`` がターゲットが今年/来年のときに内閣府への
    再取得を試みるためのフック。短いタイムアウト（既定 0.5 秒）で実装する。
    必須ではなく、管理表など再取得が要らない source は実装しなくてよい。
    """

    def refresh(self) -> Iterable[Holiday]:
        """TTL を無視して強制再取得する。"""
        ...


class HolidayCalendar:
    """祝日を保持し、営業日判定を行うカレンダー本体。

    同じ日付に複数の祝日が登録された場合は**先勝ち**で採用する
    （内閣府 CSV と会社の年末年始休暇など、複数 source の重複は珍しくない）。
    名称が違う祝日が同じ日に重なっても黙って先を採用する。

    期限切れの警告（``EXPIRING_WARNING_DAYS`` を切った日）は **同じ日に
    1回だけ**出す。同じ日に ``is_business_day`` が何回呼ばれても
    ログが埋もれないため。
    """

    def __init__(self, holidays: Iterable[Holiday]) -> None:
        """``Holiday`` の iterable から ``{日付: Holiday}`` の索引を作る。

        Args:
            holidays: 祝日の iterable。同じ日付が複数含まれていたら先勝ちで採用。
        """
        self._holidays: dict[_dt.date, Holiday] = {}
        for holiday in holidays:
            existing = self._holidays.get(holiday.date)
            if existing is None:
                self._holidays[holiday.date] = holiday
        # 期限切れ警告を「同じ日に 1度だけ」出すためのキャッシュキー
        self._expiry_warned_on: _dt.date | None = None
        # 同じ年には 1 回だけ内閣府 refresh を試みるためのキャッシュキー
        self._refreshed_keys: set[int] = set()
        # ``refresh()`` メソッドを持つ source のリスト（``from_sources`` で設定）。
        # 単発利用（``HolidayCalendar([holidays])``）では空のまま。
        self._refreshable_sources: list[RefreshableHolidaySource] = []

    # ── ファクトリ ───────────────────────────────────────────────────────────

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        encoding: str = "cp932",
    ) -> "HolidayCalendar":
        """内閣府の ``syukujitsu.csv`` を直接読む最短ルート。

        Args:
            path: CSV のパス。CP932（Shift_JIS）固定。
            encoding: 文字コード。通常は ``cp932`` のままで良い。

        Returns:
            読み込み結果から作った ``HolidayCalendar``。
        """
        # 遅延 import を避けるため、ここで csv_source を import する。
        # csv_source は標準ライブラリのみで動く（requests 不要）
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        return cls(load_cabinet_office_csv(path, encoding=encoding))

    @classmethod
    def from_sources(cls, sources: Iterable[HolidaySource]) -> "HolidayCalendar":
        """複数の ``HolidaySource`` を合体させる（内閣府 + Computed + 会社休日 など）。

        **カスケード動作**: 前の source が ``HolidayCalendarFetchError``
        （内閣府の取得失敗・``requests`` 不在など）を投げたら次の source へ
        フォールバックする。**内閣府が取れない環境で Computed に切り替えたい**
        ケース（オフライン BO 環境・期限切れ）を想定。
        全部失敗したら最後の ``HolidayCalendarFetchError`` をそのまま送出。

        Args:
            sources: ``load()`` を持つ ``HolidaySource`` の iterable。
                同じ日付が複数ソースにあれば **最初のソースの Holiday** が優先される。

        Returns:
            全ソースを結合した ``HolidayCalendar``。

        Raises:
            HolidayCalendarFetchError: 全 source が ``HolidayCalendarFetchError``
                を投げた場合、最後のエラーをそのまま送出する。
        """
        merged: list[Holiday] = []
        last_error: HolidayCalendarFetchError | None = None
        sources_list = list(sources)
        for source in sources_list:
            try:
                merged.extend(source.load())
            except HolidayCalendarFetchError as error:
                logger.warning(
                    "HolidaySource %s の取得に失敗しました。次のソースへフォールバックします: %s",
                    type(source).__name__,
                    error,
                )
                last_error = error
                continue
        if not merged and last_error is not None:
            raise last_error
        # ``refresh()`` メソッドを持つ source を保持。``is_business_day`` が
        # 呼ばれたときに内閣府への強制再取得を指示するため。
        instance = cls(merged)
        instance._refreshable_sources = [
            s for s in sources_list if isinstance(s, RefreshableHolidaySource)
        ]
        return instance

    # ── 判定 ─────────────────────────────────────────────────────────────────

    def is_holiday(self, target: _dt.date) -> bool:
        """``target`` が祝日（または休日）なら ``True``。

        ターゲットが今年/来年なら、内閣府 source への強制再取得を試みる
        （今年中に 1 回だけ。失敗時はサイレント）。
        計算式由来の暫定値（``approximate=True``）を返すときは WARNING ログ。
        """
        self._maybe_refresh_for(target)
        holiday = self._holidays.get(target)
        if holiday is None:
            return False
        if holiday.approximate:
            logger.warning(
                "祝日 %s 「%s」 は計算式による暫定値です。実際とは ±1 日前後する可能性があります。",
                target.isoformat(),
                holiday.name,
            )
        return True

    def holidays_in(self, start: _dt.date, end: _dt.date) -> list[Holiday]:
        """``start <= 日付 <= end`` の範囲に入る祝日を、日付順に返す。

        Args:
            start: 範囲開始（含む）。
            end: 範囲終了（含む）。

        Returns:
            範囲内の ``Holiday`` を日付昇順で並べたリスト。
            該当が無ければ空リスト。
        """
        if start > end:
            return []
        return sorted(
            (holiday for date, holiday in self._holidays.items() if start <= date <= end),
            key=lambda h: h.date,
        )

    def _is_business_day(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> bool:
        """``target`` が営業日なら ``True``。

        ``skip_weekends=True``（既定）なら土曜・日曜も休業扱いにする。
        ``False`` を渡すと、土曜・日曜であっても祝日でなければ「営業日」と
        判定される（振替休日を平日扱いするシナリオ向け）。

        「収録済み最終日 <= target」のときは期限切れを WARNING ログで 1度だけ
        通知する。判定自体は通常どおり行う（誤って平日扱いにならないよう、
        **収録範囲外は祝日ではない側に倒す**）。
        """
        self._maybe_warn_expiring(target)
        if skip_weekends and target.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return False
        return not self.is_holiday(target)

    def _business_day_after(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` より後で最初の営業日（``_is_business_day`` が True になる日）を返す。

        ``target`` 自身は含まない（``target`` が営業日でも翌営業日を返す）。
        収録範囲外でも日付は進むが、祝日判定は「祝日ではない」と扱う。
        期限切れの警告は ``_business_day_after`` の入口で 1度だけ出す。

        Raises:
            BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
                営業日が見つからなかった（祝日データ欠落・社内休日広範囲など）。
        """
        self._maybe_warn_expiring(target)
        return _search_business_day(
            start=target + _dt.timedelta(days=1),
            step_days=1,
            calendar=self,
            skip_weekends=skip_weekends,
        )

    def _business_day_before(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` より前で最初の営業日を返す。

        ``target`` 自身は含まない（``target`` が営業日でも前営業日を返す）。

        Raises:
            BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
                営業日が見つからなかった。
        """
        return _search_business_day(
            start=target - _dt.timedelta(days=1),
            step_days=-1,
            calendar=self,
            skip_weekends=skip_weekends,
        )

    def _business_day_on_or_after(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` 以降で最初の営業日（``target`` を含む）を返す。

        ``target`` が営業日なら ``target`` をそのまま返す。
        営業日でなければ、``_business_day_after`` と同じ動きで翌日以降を探す。

        Raises:
            BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
                営業日が見つからなかった。
        """
        if self._is_business_day(target, skip_weekends=skip_weekends):
            return target
        return self._business_day_after(target, skip_weekends=skip_weekends)

    def _business_day_on_or_before(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` 以前で最初の営業日（``target`` を含む）を返す。

        ``target`` が営業日なら ``target`` をそのまま返す。
        営業日でなければ、``_business_day_before`` と同じ動きで前日以前を探す。

        Raises:
            BusinessDayNotFoundError: ``BUSINESS_DAY_SEARCH_LIMIT`` 日探索しても
                営業日が見つからなかった。
        """
        if self._is_business_day(target, skip_weekends=skip_weekends):
            return target
        return self._business_day_before(target, skip_weekends=skip_weekends)

    def _first_business_day_of_month(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` が属する月の最初の営業日を返す。

        Raises:
            BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
        """
        start = month_start(target)
        try:
            return self._business_day_on_or_after(start, skip_weekends=skip_weekends)
        except BusinessDayNotFoundError as error:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
            ) from error

    def _last_business_day_of_month(
        self,
        target: _dt.date,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` が属する月の最後の営業日を返す。

        月末が土日・祝日のときは直前の営業日に遡る（例: 8/31 が日曜なら 8/29 金）。

        Raises:
            BusinessDayNotFoundError: その月に営業日が 1日も無いとき。
        """
        end = month_end(target)
        try:
            return self._business_day_on_or_before(end, skip_weekends=skip_weekends)
        except BusinessDayNotFoundError as error:
            raise BusinessDayNotFoundError(
                f"{target.year} 年 {target.month} 月に営業日が見つかりません: {error}"
            ) from error

    def _nth_business_day_of_month(
        self,
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
                cursor = self._business_day_on_or_after(cursor, skip_weekends=skip_weekends)
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

    def _add_business_days(
        self,
        target: _dt.date,
        n: int,
        *,
        skip_weekends: bool = True,
    ) -> _dt.date:
        """``target`` から ``n`` 営業日後の日付を返す。

        ``n`` が負なら ``|n|`` 営業日**前**を返す。
        ``n == 0`` のときは ``target`` を**そのまま**返す（``target`` が営業日か
        どうかを問わない）。これは Excel の ``WORKDAY`` と同じ挙動で、
        「今日から N 営業日後」を組み立てるときに条件分岐を書かなくて済む。

        例: 2024/5/2（木、祝日前日）に ``_add_business_days(d, 1)`` を呼ぶと
        2024/5/7（火、5/3〜5/6 が祝日＋土日）を返す。

        Raises:
            BusinessDayNotFoundError: 探索が ``BUSINESS_DAY_SEARCH_LIMIT`` に達した。
        """
        if n == 0:
            return target
        # ``target`` を 0 営業日目と数え、``n`` 回「次の（前の）営業日」へ進める。
        # ``target`` が営業日のとき n=1 で翌日営業日、非営業日のときでも
        # ``_business_day_after`` が翌営業日にスナップするので結果は同じになる。
        cursor = target
        steps = n if n > 0 else -n
        for _ in range(steps):
            if n > 0:
                cursor = self._business_day_after(cursor, skip_weekends=skip_weekends)
            else:
                cursor = self._business_day_before(cursor, skip_weekends=skip_weekends)
        return cursor

    def expires_after(self, target: _dt.date) -> bool:
        """``target`` が収録済み最終日以降（＝「収録期限を過ぎた」）なら ``True``。

        「収録済み最終日 <= target」を期限切れとみなす。等号を含めるのは、
        「収録最終日ぴったり」を「期限の境目」として扱うため（最終日当日は
        収録済みの祝日として判定できるが、それ以降は収録外）。
        """
        last = self.last_known_date()
        if last is None:
            return True
        return target >= last

    def days_until_expiry(self, today: _dt.date) -> int:
        """``today`` から収録最終日までの日数。最終日を過ぎていれば負の値。

        Args:
            today: 「今日」とみなす日付。

        Returns:
            ``last_known - today`` の日数差。収録済み祝日が無いと ``-1``。
        """
        last = self.last_known_date()
        if last is None:
            return -1
        return (last - today).days

    def last_known_date(self) -> _dt.date | None:
        """収録済み祝日のうち最も新しい日付。無ければ ``None``。"""
        if not self._holidays:
            return None
        return max(self._holidays.keys())

    def holiday_names(self, target: _dt.date) -> Sequence[str]:
        """``target`` に登録された祝日名称のタプル（同日が複数あれば複数要素）。"""
        holiday = self._holidays.get(target)
        if holiday is None:
            return ()
        return (holiday.name,)

    def all_holidays(self) -> list[Holiday]:
        """保持している祝日を日付順に並べたリストを返す。"""
        return sorted(self._holidays.values(), key=lambda h: h.date)

    def _maybe_warn_expiring(self, today: _dt.date) -> None:
        """期限切れが近いとき、**同じ日付で 1度だけ** WARNING ログを出す。"""
        if self._expiry_warned_on == today:
            return
        remaining = self.days_until_expiry(today)
        if 0 <= remaining < EXPIRING_WARNING_DAYS:
            last = self.last_known_date()
            logger.warning(
                "祝日カレンダーの収録期限が近づいています: 残り %d 日（最終収録日: %s）。"
                "内閣府の祝日 CSV を更新するか、管理表に直近の祝日を追加してください。",
                remaining,
                last,
            )
            self._expiry_warned_on = today

    def _maybe_refresh_for(self, target: _dt.date) -> None:
        """ターゲットが今年/来年なら、今年中に 1 回だけ内閣府に refresh を試みる。

        キャッシュに ``target`` が無い or ``approximate=True`` (Computed の
        近似式由来) のときに、内閣府に強制再取得を試みる。**今年中に 1 回だけ**
        試す（複数回呼ばれるのを防ぐ）。失敗時はサイレント（既存のキャッシュ
        または Computed の近似式で判定する）。
        """
        if not self._refreshable_sources:
            return
        today_year = _dt.date.today().year  # noqa: DTZ011
        if target.year not in (today_year, today_year + 1):
            return
        if today_year in self._refreshed_keys:
            return  # 同じ年には 1 回だけ
        self._refreshed_keys.add(today_year)
        for source in self._refreshable_sources:
            try:
                fresh = source.refresh()
            except HolidayCalendarFetchError as error:
                logger.warning(
                    "HolidaySource %s への強制再取得に失敗しました: %s",
                    type(source).__name__,
                    error,
                )
                continue
            # 内閣府由来の値（``approximate=False``）は Computed の近似式を
            # 上書きする。逆は上書きしない（内閣府が取れない以上、Computed
            # の近似式しかなく、ユーザーに誤情報を与えないため）。
            for holiday in fresh:
                existing = self._holidays.get(holiday.date)
                if existing is not None and not existing.approximate:
                    continue  # 既に内閣府由来 → 上書きしない
                self._holidays[holiday.date] = holiday
            return  # 1 個目の source が成功したら終了


def is_business_day(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> bool:
    """``target`` が営業日なら ``True``。``calendar`` を省略できる簡易判定。

    ``calendar=None`` のときは**既定カレンダー**（``default_calendar()``）を使う。
    アプリ側で ``set_default_calendar()`` を呼んでおけば、利用者は
    ``HolidayCalendar`` を組み立てなくても「今日が営業日か」を判定できる。

    ``calendar`` をキーワード専用にして、呼び出し側がうっかり位置引数で
    日付とカレンダーを取り違える事故を防ぐ。
    """
    cal = calendar if calendar is not None else default_calendar()
    return cal._is_business_day(target, skip_weekends=skip_weekends)


def business_day_after(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より後で最初の営業日（``target`` 自身を含まない）。

    ``calendar=None`` のときは**既定カレンダー**を使う。
    """
    cal = calendar if calendar is not None else default_calendar()
    return cal._business_day_after(target, skip_weekends=skip_weekends)


def business_day_before(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` より前で最初の営業日（``target`` 自身を含まない）。

    ``calendar=None`` のときは**既定カレンダー**を使う。
    """
    cal = calendar if calendar is not None else default_calendar()
    return cal._business_day_before(target, skip_weekends=skip_weekends)


def business_day_on_or_after(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以降で最初の営業日（``target`` を含む）。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._business_day_on_or_after(target, skip_weekends=skip_weekends)


def business_day_on_or_before(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` 以前で最初の営業日（``target`` を含む）。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._business_day_on_or_before(target, skip_weekends=skip_weekends)


def first_business_day_of_month(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最初の営業日。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._first_business_day_of_month(target, skip_weekends=skip_weekends)


def last_business_day_of_month(
    target: _dt.date,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の最後の営業日。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._last_business_day_of_month(target, skip_weekends=skip_weekends)


def nth_business_day_of_month(
    target: _dt.date,
    n: int,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` が属する月の第 ``n`` 営業日（``n`` は 1 始まり）。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._nth_business_day_of_month(target, n, skip_weekends=skip_weekends)


def add_business_days(
    target: _dt.date,
    n: int,
    *,
    calendar: HolidayCalendar | None = None,
    skip_weekends: bool = True,
) -> _dt.date:
    """``target`` から ``n`` 営業日後の日付（``n`` が負なら前）。``calendar`` 省略可。"""
    cal = calendar if calendar is not None else default_calendar()
    return cal._add_business_days(target, n, skip_weekends=skip_weekends)


# ── 既定カレンダー ──────────────────────────────────────────────────────
# 「アプリ起動時に ``set_default_calendar`` を一度呼べば、利用者は何も意識
# せずに ``is_business_day(target)`` と書ける」ための遅延生成キャッシュ。
# ネットワークには出ない（``ComputedHolidaySource`` + 同梱 CSV + 会社休日 だけ）。

_DEFAULT_CALENDAR_PATH: Final[Path] = Path(__file__).parent / "data" / "syukujitsu.csv"
_default_calendar: HolidayCalendar | None = None


def default_calendar() -> HolidayCalendar:
    """既定カレンダーを取得する（**プロセス内で 1回だけ**遅延生成）。

    構成は 3 つだけ:
        1. ``ComputedHolidaySource``（純粋計算。土台）
        2. 同梱の ``syukujitsu.csv`` を ``load_cabinet_office_csv`` で読む
           （内閣府の実値。計算式の上書き用）
        3. ``CompanyHolidaySource``（会社独自の休業日。コード直書き）

    **ネットワークには一切出ない。** ``CabinetOfficeCSVSource`` は
    含めない（``comken.core`` は ``requests`` に依存できないし、業務 PC の
    通信制限下でも動く必要があるため）。
    """
    global _default_calendar
    if _default_calendar is None:
        # 遅延 import: csv_source / computed 側を ``import 時点`` で読まないため、
        # 既定カレンダーを必要とした瞬間にだけ取り込む。いずれも標準ライブラリ
        # のみで動くので ``requests`` はここを通っても入らない。
        from comken.core.holidays.sources.company import CompanyHolidaySource
        from comken.core.holidays.sources.computed import ComputedHolidaySource

        _default_calendar = HolidayCalendar.from_sources(
            [
                ComputedHolidaySource(),
                _BundledCabinetCSVSource(_DEFAULT_CALENDAR_PATH),
                CompanyHolidaySource(),
            ]
        )
    return _default_calendar


def set_default_calendar(calendar: HolidayCalendar | None) -> None:
    """既定カレンダーを差し替える（``None`` を渡すと既定の遅延生成に戻る）。

    会社独自の年末年始などを追加したいプロジェクトは、起動時に
    ``set_default_calendar(HolidayCalendar.from_sources([...]))`` を一度
    呼んでおけば、利用者は ``is_business_day(target)`` のような
    モジュール関数を直接呼べる。
    """
    global _default_calendar
    _default_calendar = calendar


class _BundledCabinetCSVSource:
    """同梱の ``syukujitsu.csv`` を読むための ``HolidaySource`` 実装。

    ``CabinetOfficeCSVSource`` は ``requests`` 依存・ネットワーク取得が前提
    なので既定カレンダーには使えない（``comken.core`` は ``requests`` を
    import できない）。代わりに同梱 CSV を直接読む最小実装を用意する。
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> list[Holiday]:
        """同梱の ``syukujitsu.csv`` を読み ``Holiday`` のリストを返す。"""
        from comken.core.holidays.csv_source import load_cabinet_office_csv

        return load_cabinet_office_csv(self._path)


# ── 内部ヘルパー ────────────────────────────────────────────────────────


def _search_business_day(
    *,
    start: _dt.date,
    step_days: int,
    calendar: HolidayCalendar,
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
        if calendar._is_business_day(cursor, skip_weekends=skip_weekends):
            return cursor
        cursor += _dt.timedelta(days=step_days)
    raise BusinessDayNotFoundError(
        f"{BUSINESS_DAY_SEARCH_LIMIT} 日探索しても営業日が見つかりません。"
        "祝日データに過不足がないか、社内休日が広範囲に登録されていないか確認してください。"
    )


__all__ = [
    "BUSINESS_DAY_SEARCH_LIMIT",
    "EXPIRING_WARNING_DAYS",
    "Holiday",
    "HolidayCalendar",
    "HolidaySource",
    "RefreshableHolidaySource",
    "_BundledCabinetCSVSource",
    "add_business_days",
    "business_day_after",
    "business_day_before",
    "business_day_on_or_after",
    "business_day_on_or_before",
    "default_calendar",
    "first_business_day_of_month",
    "is_business_day",
    "last_business_day_of_month",
    "nth_business_day_of_month",
    "set_default_calendar",
]
