"""comken.core.calendar.build のテスト。

内閣府 CSV の解析（CP932・形式エラー・年の範囲など）と会社休日の展開
（年非依存・年つきの臨時休業・国民の祝日との重なり）を検証する。
また、生成ツールの ``build_rows()`` の結果が追跡している
``comken/core/calendar/data/company_calendar.csv`` と行単位で一致することを
確認する（同期テスト）。
"""

from __future__ import annotations

import datetime as _dt
import shutil
from pathlib import Path

import pytest

from comken.core.calendar import build
from comken.exceptions import CalendarFormatError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "holidays" / "syukujitsu_sample.csv"


@pytest.fixture
def temp_company_holidays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """テスト用に ``company_holidays.csv`` を一時ファイルへ差し替える。

    戻り値は ``(source_path, target_path)``。``source_path`` は既存の
    ``company_holidays.csv``、``target_path`` は差し替え先。テスト終了時に
    元のパスへ戻す monkeypatch を仕込む。
    """
    source = build.COMPANY_HOLIDAYS_CSV_PATH
    target = tmp_path / "company_holidays.csv"
    shutil.copyfile(source, target)
    monkeypatch.setattr(build, "COMPANY_HOLIDAYS_CSV_PATH", target)
    return source, target


# ── 内閣府 CSV ローダー（生成ツール経由） ─────────────────────────────────


class TestCabinetOfficeCsvLoader:
    """内閣府 CSV（CP932）の読み取り。"""

    def test_loads_real_format(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """fixture を CP932 で読んで ``(date, name)`` に変換できる。"""
        # ``SYUKUJITSU_CSV_PATH`` を fixture へ差し替えて検証する
        monkeypatch.setattr(build, "SYUKUJITSU_CSV_PATH", FIXTURE_PATH)

        holidays = build._load_national_holidays()

        assert holidays, "1件以上読み取れるべき"
        dates = {date_ for date_, _name in holidays}
        assert _dt.date(2024, 1, 1) in dates
        assert _dt.date(2025, 1, 1) in dates
        assert _dt.date(2026, 1, 1) in dates
        # 名称はそのまま入る
        assert (_dt.date(2024, 5, 3), "憲法記念日") in holidays
        # ヘッダー行は結果に含まれない
        assert all(name != "国民の祝日・休日名称" for _, name in holidays)

    def test_garbage_text_raises_format_error(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """内閣府 CSV として読めない（国民の祝日が 0 件）場合は ``CalendarFormatError``。"""
        bad = tmp_path / "bad.csv"
        bad.write_text(
            "国民の祝日・休日月日,国民の祝日・休日名称\nhello,world\nfoo,bar\n",
            encoding="cp932",
        )
        monkeypatch.setattr(build, "SYUKUJITSU_CSV_PATH", bad)

        with pytest.raises(
            CalendarFormatError,
            match="国民の祝日を 1 件も読み取れませんでした",
        ):
            build.build_rows()


# ── 会社休日の定義（company_holidays.csv） ─────────────────────────────────


class TestCompanyHolidaysCsv:
    """``company_holidays.csv`` を読み込んだ既定値の検証。"""

    def test_year_end_and_new_year_default_present(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """既定で年末年始休暇（12/29 - 1/3）が定義されている。"""
        _source, target = temp_company_holidays
        # 既定の内容を書き直す（test と独立して動く）
        target.write_bytes(
            (
                "﻿年,月,日,名称\r\n"
                ",12,29,年末年始休暇\r\n"
                ",12,30,年末年始休暇\r\n"
                ",12,31,年末年始休暇\r\n"
                ",1,1,年末年始休暇\r\n"
                ",1,2,年末年始休暇\r\n"
                ",1,3,年末年始休暇\r\n"
            ).encode()
        )

        yearly_rules, _extra_rules = build._load_company_rules()
        yearly = {(month, day): name for month, day, name in yearly_rules}
        assert yearly[(12, 29)] == "年末年始休暇"
        assert yearly[(12, 30)] == "年末年始休暇"
        assert yearly[(12, 31)] == "年末年始休暇"
        assert yearly[(1, 1)] == "年末年始休暇"
        assert yearly[(1, 2)] == "年末年始休暇"
        assert yearly[(1, 3)] == "年末年始休暇"

    def test_extra_holiday_named_company_holiday(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """年つき行（臨時休業）は「会社休業日」名称で反映される（名称空欄時）。"""
        _source, target = temp_company_holidays
        target.write_bytes(
            (
                "﻿年,月,日,名称\r\n"
                ",12,29,年末年始休暇\r\n"
                ",12,30,年末年始休暇\r\n"
                ",12,31,年末年始休暇\r\n"
                ",1,1,年末年始休暇\r\n"
                ",1,2,年末年始休暇\r\n"
                ",1,3,年末年始休暇\r\n"
                "2026,11,4,\r\n"  # 名称空欄 → 会社休業日
            ).encode()
        )

        rows = build.build_rows()
        # 国民の祝日と重なっていなければそのまま「会社休業日」
        assert (_dt.date(2026, 11, 4), "会社休業日") in rows
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
        rows = build.build_rows()
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
        rows = build.build_rows()
        names_for_jan1 = [name for date_, name in rows if date_ == _dt.date(2026, 1, 1)]
        assert names_for_jan1 == ["元日"]

    def test_extra_holiday_does_not_overwrite_national(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """年つきの行（臨時休業）が国民の祝日と同じ日でも国民の祝日が先勝ち。"""
        _source, target = temp_company_holidays
        target.write_bytes(
            (
                "﻿年,月,日,名称\r\n"
                ",12,29,年末年始休暇\r\n"
                ",12,30,年末年始休暇\r\n"
                ",12,31,年末年始休暇\r\n"
                ",1,1,年末年始休暇\r\n"
                ",1,2,年末年始休暇\r\n"
                ",1,3,年末年始休暇\r\n"
                "2026,5,4,\r\n"  # 名称空欄 → 会社休業日
            ).encode()
        )

        rows = build.build_rows()
        # 2026/5/4 は「みどりの日」（国民の祝日）が先勝ち
        names = [name for date_, name in rows if date_ == _dt.date(2026, 5, 4)]
        assert names == ["みどりの日"]

    def test_rows_are_sorted_by_date(self) -> None:
        """``build_rows()`` の結果が日付順。"""
        rows = build.build_rows()
        dates = [date_ for date_, _ in rows]
        assert dates == sorted(dates)

    def test_is_independent_of_today(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``build_rows()`` の結果が呼ぶ日に依存しない。

        ``comken.core.clock.today`` を別日付に差し替えても、結果が同じになる
        ことを確認する（内閣府 CSV 由来＋会社休日のルール判定で固定）。
        """
        from comken.core import clock as clock_module

        monkeypatch.setattr(clock_module, "today", lambda: _dt.date(2020, 1, 1))
        rows_a = build.build_rows()
        monkeypatch.setattr(clock_module, "today", lambda: _dt.date(2099, 1, 1))
        rows_b = build.build_rows()
        assert rows_a == rows_b


# ── company_holidays.csv の展開ルール ─────────────────────────────────────


class TestCompanyHolidaysExpansion:
    """「年空欄=毎年」「年つき=その年だけ」の展開ルール。"""

    def test_year_blank_row_expands_to_every_year(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """年空欄の行は内閣府 CSV の全年に展開される。"""
        _source, target = temp_company_holidays
        target.write_bytes(("﻿年,月,日,名称\r\n,7,30,夏季休暇\r\n").encode())

        rows = build.build_rows()
        summer = [date_ for date_, name in rows if name == "夏季休暇"]
        assert summer, "夏季休暇が1件も展開されていない"
        # 7/30 が内閣府 CSV 全年（国民の祝日と重ならない範囲）に現れる
        for year in (1955, 2000, 2026, 2027):
            assert _dt.date(year, 7, 30) in summer, f"{year} 年の 7/30 が展開されていません"

    def test_year_filled_row_only_for_that_year(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """年つきの行はその年だけ登録される。"""
        _source, target = temp_company_holidays
        target.write_bytes(
            (
                "﻿年,月,日,名称\r\n"
                ",12,29,年末年始休暇\r\n"
                ",12,30,年末年始休暇\r\n"
                ",12,31,年末年始休暇\r\n"
                ",1,1,年末年始休暇\r\n"
                ",1,2,年末年始休暇\r\n"
                ",1,3,年末年始休暇\r\n"
                "2026,12,28,臨時\r\n"
            ).encode()
        )

        rows = build.build_rows()
        # 2026/12/28 だけ追加されている
        assert (_dt.date(2026, 12, 28), "臨時") in rows
        # 2025/12/28 や 2027/12/28 は無い
        assert all(date_ != _dt.date(2025, 12, 28) for date_, _ in rows)
        assert all(date_ != _dt.date(2027, 12, 28) for date_, _ in rows)


# ── company_holidays.csv の書式不正 ─────────────────────────────────────


class TestCompanyHolidaysFormatError:
    """``company_holidays.csv`` の書式不正時に ``CalendarFormatError`` で止まる。"""

    def test_non_numeric_month_raises_format_error(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """月が数字でないと ``CalendarFormatError``（行番号入り）。"""
        _source, target = temp_company_holidays
        target.write_bytes(("﻿年,月,日,名称\r\n,abc,29,年末年始休暇\r\n").encode())

        with pytest.raises(CalendarFormatError) as excinfo:
            build.build_rows()
        # 行番号（=2 行目）と「月」が入る
        message = str(excinfo.value)
        assert "2 行目" in message
        assert "月" in message

    def test_invalid_date_raises_format_error(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """存在しない日付（2/30 など）で ``CalendarFormatError``。"""
        _source, target = temp_company_holidays
        target.write_bytes(("﻿年,月,日,名称\r\n2026,2,30,臨時\r\n").encode())

        with pytest.raises(CalendarFormatError) as excinfo:
            build.build_rows()
        message = str(excinfo.value)
        assert "2 行目" in message
        assert "2026年2月30日" in message

    def test_missing_month_or_day_raises_format_error(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """月日が空欄だと ``CalendarFormatError``。"""
        _source, target = temp_company_holidays
        target.write_bytes(("﻿年,月,日,名称\r\n,,29,年末年始休暇\r\n").encode())

        with pytest.raises(CalendarFormatError) as excinfo:
            build.build_rows()
        message = str(excinfo.value)
        assert "2 行目" in message
        assert "空欄" in message

    def test_wrong_header_raises_format_error(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """ヘッダが ``年,月,日,名称`` でないと ``CalendarFormatError``。"""
        _source, target = temp_company_holidays
        target.write_bytes(("﻿col1,col2,col3,col4\r\n,12,29,年末年始休暇\r\n").encode())

        with pytest.raises(CalendarFormatError) as excinfo:
            build.build_rows()
        message = str(excinfo.value)
        assert "見出し" in message

    def test_yearly_rule_with_nonexistent_date_raises_format_error(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """年が空欄（毎年）の行でも、2/30 のように存在しない日付は読み込みで止まる。

        防いでいるバグ: 読み込みを通り抜け、年ごとに展開する段階で素の ``ValueError`` になる。
        """
        _source, target = temp_company_holidays
        target.write_bytes(("\ufeff年,月,日,名称\r\n,2,30,臨時\r\n").encode())

        with pytest.raises(CalendarFormatError) as excinfo:
            build.build_rows()
        assert "2 行目" in str(excinfo.value)

    def test_yearly_leap_day_only_appears_in_leap_years(
        self, temp_company_holidays: tuple[Path, Path]
    ) -> None:
        """毎年の休みに 2/29 を書いても、閏年でない年は飛ばして止まらない。"""
        _source, target = temp_company_holidays
        target.write_bytes(("\ufeff年,月,日,名称\r\n,2,29,閏日休み\r\n").encode())

        rows = dict(build.build_rows())

        assert rows[_dt.date(2024, 2, 29)] == "閏日休み"
        assert [d for d, name in rows.items() if name == "閏日休み" and d.year == 2025] == []


# ── 同期テスト ────────────────────────────────────────────────────────


class TestCsvSynchronization:
    """生成物 ``data/company_calendar.csv`` との同期テスト。

    ``build_rows()`` の結果が ``comken/core/calendar/data/company_calendar.csv``
    （git 管理下）と行単位で一致していることを確認する。CSV のフォーマット
    変更・内閣府 CSV 更新・会社休日ルール変更後に
    ``python -m comken.core.calendar.build`` を再実行するのを忘れた場合に落ちる。
    """

    def test_build_rows_matches_bundled_company_calendar_csv(self) -> None:
        """``build_rows()`` の出力が ``data/company_calendar.csv`` と一致する。"""
        bundled = build.COMPANY_CALENDAR_CSV_PATH
        assert bundled.exists(), (
            "data/company_calendar.csv がまだ生成されていません。"
            " `python -m comken.core.calendar.build` を実行してください。"
        )

        with bundled.open(encoding="utf-8-sig", newline="") as file:
            import csv as _csv

            bundled_rows = list(_csv.reader(file))
        bundled_header, bundled_data = bundled_rows[0], bundled_rows[1:]
        assert bundled_header == ["date", "name"], (
            "data/company_calendar.csv のヘッダーが date, name ではありません。"
            " `python -m comken.core.calendar.build` を実行して"
            " company_calendar.csv を更新しコミットしてください。"
        )

        built = build.build_rows()
        assert len(bundled_data) == len(built), (
            "data/company_calendar.csv の行数が build_rows() と一致しません。"
            " `python -m comken.core.calendar.build` を実行して"
            " company_calendar.csv を更新しコミットしてください。"
        )
        for line_number, ((date_, name), bundled_row) in enumerate(
            zip(built, bundled_data, strict=True), start=2
        ):
            assert bundled_row == [date_.isoformat(), name], (
                f"{line_number} 行目が一致しません: bundled={bundled_row!r}, "
                f"build_rows={[date_.isoformat(), name]!r}。"
                " `python -m comken.core.calendar.build` を実行して"
                " company_calendar.csv を更新しコミットしてください。"
            )
