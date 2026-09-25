"""comken.core.holidays.build のテスト。

内閣府 CSV の解析（CP932・形式エラー・年の範囲など）と会社休日の展開
（年非依存・COMPANY_HOLIDAYS_EXTRA・国民の祝日との重なり）を検証する。
また、生成ツールの ``build_rows()`` の結果が追跡している
``comken/core/holidays/data/company_calendar.csv`` と行単位で一致することを
確認する（同期テスト）。
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path

import pytest

from comken.core.holidays import build as build_holidays
from comken.exceptions import HolidayError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "holidays" / "syukujitsu_sample.csv"


# ── 内閣府 CSV ローダー（生成ツール経由） ─────────────────────────────────


class TestCabinetOfficeCsvLoader:
    """内閣府 CSV（CP932）の読み取り。"""

    def test_loads_real_format(self) -> None:
        """fixture を CP932 で読んで ``(date, name)`` に変換できる。"""
        # ``_load_national_holidays`` は固定パス参照のため、fixture を
        # ``SYUKUJITSU_CSV_PATH`` に一時的に差し替えて検証する
        original = build_holidays.SYUKUJITSU_CSV_PATH
        build_holidays.SYUKUJITSU_CSV_PATH = FIXTURE_PATH  # type: ignore[misc]
        try:
            holidays = build_holidays._load_national_holidays()
        finally:
            build_holidays.SYUKUJITSU_CSV_PATH = original  # type: ignore[misc]

        assert holidays, "1件以上読み取れるべき"
        dates = {date_ for date_, _name in holidays}
        assert _dt.date(2024, 1, 1) in dates
        assert _dt.date(2025, 1, 1) in dates
        assert _dt.date(2026, 1, 1) in dates
        # 名称はそのまま入る
        assert (_dt.date(2024, 5, 3), "憲法記念日") in holidays
        # ヘッダー行は結果に含まれない
        assert all(name != "国民の祝日・休日名称" for _, name in holidays)

    def test_garbage_text_raises_format_error(self, tmp_path: Path) -> None:
        """内閣府 CSV として読めない（国民の祝日が 0 件）場合は ``HolidayError``。"""
        original = build_holidays.SYUKUJITSU_CSV_PATH
        build_holidays.SYUKUJITSU_CSV_PATH = tmp_path / "bad.csv"  # type: ignore[misc]
        try:
            (tmp_path / "bad.csv").write_text(
                "国民の祝日・休日月日,国民の祝日・休日名称\nhello,world\nfoo,bar\n",
                encoding="cp932",
            )
            with pytest.raises(
                HolidayError,
                match="国民の祝日を 1 件も読み取れませんでした",
            ):
                build_holidays.build_rows()
        finally:
            build_holidays.SYUKUJITSU_CSV_PATH = original  # type: ignore[misc]


# ── 会社休日の定義 ────────────────────────────────────────────────────────


class TestCompanyHolidaysDefinition:
    """``COMPANY_HOLIDAYS`` / ``COMPANY_HOLIDAYS_EXTRA`` の既定値の検証。"""

    def test_year_end_and_new_year_default_present(self) -> None:
        """既定で年末年始休暇（12/29 - 1/3）が定義されている。"""
        assert "年末年始休暇" in build_holidays.COMPANY_HOLIDAYS
        month_days = build_holidays.COMPANY_HOLIDAYS["年末年始休暇"]
        assert (12, 29) in month_days
        assert (12, 30) in month_days
        assert (12, 31) in month_days
        assert (1, 1) in month_days
        assert (1, 2) in month_days
        assert (1, 3) in month_days

    def test_extra_holidays_named_company_holiday(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``COMPANY_HOLIDAYS_EXTRA`` に足した日付は「会社休業日」名称で反映される。"""
        monkeypatch.setattr(build_holidays, "COMPANY_HOLIDAYS_EXTRA", (_dt.date(2026, 11, 4),))
        rows = build_holidays.build_rows()
        # 国民の祝日と重なっていなければそのまま「会社休業日」
        assert (_dt.date(2026, 11, 4), build_holidays.EXTRA_HOLIDAY_NAME) in rows
        # 月日の会社休日ルールはそのまま
        assert (_dt.date(2026, 12, 29), "年末年始休暇") in rows


# ── build_rows() の合成ロジック ──────────────────────────────────────────


class TestBuildRows:
    """``build_rows()`` のマージロジック。"""

    def test_company_holiday_expanded_across_year_range(self) -> None:
        """会社休日（年単位の月日ルール）が内閣府 CSV の最初の年〜最後の年に展開される。

        会社休日は内閣府 CSV の年に合わせて展開される（過去・未来を問わず）。
        国民の祝日と重なる日（=1/1）は国民の祝日が先勝ちで、年末年始休暇とは
        ならない。
        """
        rows = build_holidays.build_rows()
        # 12/29, 12/30, 12/31 は内閣府 CSV の最初の年〜最後の年まで全て含まれる
        for year in (1955, 1960, 2000, 2026, 2027):
            for month, day in ((12, 29), (12, 30), (12, 31)):
                date_ = _dt.date(year, month, day)
                assert (date_, "年末年始休暇") in rows, (
                    f"{date_} が年末年始休暇として含まれていません"
                )
        # 1/2, 1/3 は内閣府 CSV の全年で年末年始休暇として含まれる
        # （1/1 は元日が国民の祝日として先勝ちするため別アサート）
        for year in (1955, 1960, 2000, 2026, 2027):
            for month, day in ((1, 2), (1, 3)):
                date_ = _dt.date(year, month, day)
                assert (date_, "年末年始休暇") in rows, (
                    f"{date_} が年末年始休暇として含まれていません"
                )

    def test_national_holiday_wins_over_company_holiday(self) -> None:
        """国民の祝日と会社休日が同じ日に重なった場合、国民の祝日が先勝ち。

        2026/1/1 は元日（国民の祝日）かつ年末年始休暇（会社休日）→ 国民の祝日
        側（``"元日"``）が採用され、``"年末年始休暇"`` は同じ日に現れない。
        """
        rows = build_holidays.build_rows()
        names_for_jan1 = [name for date_, name in rows if date_ == _dt.date(2026, 1, 1)]
        assert names_for_jan1 == ["元日"]

    def test_extra_holiday_does_not_overwrite_national(self) -> None:
        """``COMPANY_HOLIDAYS_EXTRA`` が国民の祝日と同じ日でも国民の祝日が先勝ち。"""
        original = build_holidays.COMPANY_HOLIDAYS_EXTRA
        build_holidays.COMPANY_HOLIDAYS_EXTRA = (_dt.date(2026, 5, 4),)  # type: ignore[misc]
        try:
            rows = build_holidays.build_rows()
            # 2026/5/4 は「みどりの日」（国民の祝日）が先勝ち
            names = [name for date_, name in rows if date_ == _dt.date(2026, 5, 4)]
            assert names == ["みどりの日"]
        finally:
            build_holidays.COMPANY_HOLIDAYS_EXTRA = original  # type: ignore[misc]

    def test_rows_are_sorted_by_date(self) -> None:
        """``build_rows()`` の結果が日付順。"""
        rows = build_holidays.build_rows()
        dates = [date_ for date_, _ in rows]
        assert dates == sorted(dates)

    def test_is_independent_of_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``build_rows()`` の結果が呼ぶ日に依存しない。

        ``comken.core.dates.today`` を別日付に差し替えても、結果が同じになる
        ことを確認する（内閣府 CSV 由来＋会社休日のルール判定で固定）。
        """
        from comken.core import dates as dates_module

        monkeypatch.setattr(dates_module, "today", lambda: _dt.date(2020, 1, 1))
        rows_a = build_holidays.build_rows()
        monkeypatch.setattr(dates_module, "today", lambda: _dt.date(2099, 1, 1))
        rows_b = build_holidays.build_rows()
        assert rows_a == rows_b


# ── 同期テスト ────────────────────────────────────────────────────────


class TestCsvSynchronization:
    """生成物 ``data/company_calendar.csv`` との同期テスト。

    ``build_rows()`` の結果が ``comken/core/holidays/data/company_calendar.csv``
    （git 管理下）と行単位で一致していることを確認する。CSV のフォーマット
    変更・内閣府 CSV 更新・会社休日ルール変更後に
    ``python -m comken.core.holidays.build`` を再実行するのを忘れた場合に落ちる。
    """

    def test_build_rows_matches_bundled_company_calendar_csv(self) -> None:
        """``build_rows()`` の出力が ``data/company_calendar.csv`` と一致する。"""
        bundled = build_holidays.COMPANY_HOLIDAYS_CSV_PATH
        assert bundled.exists(), (
            "data/company_calendar.csv がまだ生成されていません。"
            " `python -m comken.core.holidays.build` を実行してください。"
        )

        with bundled.open(encoding="utf-8-sig", newline="") as file:
            import csv as _csv

            bundled_rows = list(_csv.reader(file))
        bundled_header, bundled_data = bundled_rows[0], bundled_rows[1:]
        assert bundled_header == ["date", "name"], (
            "data/company_calendar.csv のヘッダーが date, name ではありません。"
            " `python -m comken.core.holidays.build` を実行して company_calendar.csv を"
            " 更新しコミットしてください。"
        )

        built = build_holidays.build_rows()
        assert len(bundled_data) == len(built), (
            "data/company_calendar.csv の行数が build_rows() と一致しません。"
            " `python -m comken.core.holidays.build` を実行して company_calendar.csv を"
            " 更新しコミットしてください。"
        )
        for line_number, ((date_, name), bundled_row) in enumerate(
            zip(built, bundled_data, strict=True), start=2
        ):
            assert bundled_row == [date_.isoformat(), name], (
                f"{line_number} 行目が一致しません: bundled={bundled_row!r}, "
                f"build_rows={[date_.isoformat(), name]!r}。"
                " `python -m comken.core.holidays.build` を実行して company_calendar.csv を"
                " 更新しコミットしてください。"
            )
