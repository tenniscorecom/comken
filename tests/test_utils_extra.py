"""
retry / Timer / zip ユーティリティのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

import logging
import zipfile

import pytest

from comken.core import timer as timer_module
from comken.core.files import atomic_write, unzip, zip_files, zip_folder
from comken.core.retry import retry
from comken.core.timer import Timer


class TestRetry:
    """retry デコレータのテスト。"""

    def test_returns_value_on_first_success(self):
        """1回目で成功すれば、そのまま値を返すことを確認する。"""
        calls = []

        @retry(times=3, wait=0)
        def func():
            calls.append(1)
            return "ok"

        assert func() == "ok"
        assert len(calls) == 1

    def test_retries_until_success(self):
        """失敗しても times 回以内に成功すれば値を返すことを確認する。"""
        calls = []

        @retry(times=3, wait=0)
        def func():
            calls.append(1)
            if len(calls) < 3:
                raise ValueError("一時的な失敗")
            return "ok"

        assert func() == "ok"
        assert len(calls) == 3

    def test_raises_after_all_attempts_fail(self):
        """times 回すべて失敗したら最後の例外がそのまま出ることを確認する。"""
        calls = []

        @retry(times=3, wait=0)
        def func():
            calls.append(1)
            raise ValueError("毎回失敗")

        with pytest.raises(ValueError, match="毎回失敗"):
            func()
        assert len(calls) == 3

    def test_unlisted_exception_raises_immediately(self):
        """on に含まれない例外は即座に出る（リトライしない）ことを確認する。"""
        calls = []

        @retry(times=3, wait=0, on=(ValueError,))
        def func():
            calls.append(1)
            raise TypeError("対象外の例外")

        with pytest.raises(TypeError):
            func()
        assert len(calls) == 1

    def test_preserves_function_name(self):
        """functools.wraps により関数名が保たれることを確認する（ログ・デバッグ用）。"""

        @retry()
        def download_report():
            pass

        assert download_report.__name__ == "download_report"

    def test_passes_arguments(self):
        """引数・キーワード引数がそのまま渡ることを確認する。"""

        @retry(times=2, wait=0)
        def add(a, b=0):
            return a + b

        assert add(1, b=2) == 3


class TestTimer:
    """Timer（処理時間計測）のテスト。"""

    def test_with_block_measures_elapsed(self):
        """with を抜けた後に elapsed が設定されることを確認する。"""
        with Timer("テスト処理") as t:
            pass

        assert t.elapsed >= 0

    def test_logs_default_format(self, caplog, monkeypatch):
        """``time_format`` 既定（``None``）で ``"{total_seconds:.2f}秒"`` が出ることを確認する。"""
        # ``__enter__`` で 0.0、``__exit__`` で 3661.0 を返すようにして経過 3661 秒に固定する
        clock = iter([0.0, 3661.0])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with caplog.at_level(logging.INFO), Timer("CSV読み込み"):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["CSV読み込み: 3661.00秒"]

    def test_logs_keeps_subsecond_precision(self, caplog, monkeypatch):
        """経過 3.21 秒で既定ログが ``"処理: 3.21秒"`` になることを確認する。"""
        # 秒未満がそのまま残ることを示すため、3.21 秒に固定する
        clock = iter([0.0, 3.21])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with caplog.at_level(logging.INFO), Timer("処理"):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 3.21秒"]

    def test_logs_strftime_rounds_subsecond(self, caplog, monkeypatch):
        """``time_format="%H:%M:%S"`` で秒未満が四捨五入されて表示されることを確認する。

        3661.7 秒 → ``01:01:02``（``.7`` が ``02`` に丸められる）。
        整数秒に丸めてから ``datetime.time`` に詰めるので、``00:00:60`` の形に
        はならない（時・分・秒を別々に丸めない）。
        """
        clock = iter([0.0, 3661.7])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H:%M:%S"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 01:01:02"]

    def test_logs_strftime_rounds_59_6_up_to_next_minute(self, caplog, monkeypatch):
        """59.6 秒は ``00:01:00`` に丸められることを確認する（秒未満の四捨五入）。

        整数秒に丸めてから ``datetime.time`` に詰めるので、``%S`` は
        ``59`` 以下にしかならない（分への繰り上げで吸収する）。
        """
        clock = iter([0.0, 59.6])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H:%M:%S"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 00:01:00"]

    def test_logs_strftime_rounds_2_5_up_to_three(self, caplog, monkeypatch):
        """2.5 秒は ``00:00:03`` に丸められることを確認する（偶数丸めとの差）。

        ``round()`` 偶数丸めなら ``02`` になる値で、ここで実装が
        ``int(seconds + 0.5)`` であることを保証する。
        """
        clock = iter([0.0, 2.5])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H:%M:%S"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 00:00:03"]

    def test_logs_strftime_rounds_0_5_up_to_one(self, caplog, monkeypatch):
        """0.5 秒は ``00:00:01`` に丸められることを確認する（偶数丸めとの差）。

        ``round()`` 偶数丸めなら ``00`` になる値で、ここで実装が
        ``int(seconds + 0.5)`` であることを保証する。
        """
        clock = iter([0.0, 0.5])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H:%M:%S"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 00:00:01"]

    def test_logs_strftime_hours_wrap_around_24(self, caplog, monkeypatch):
        """24 時間を超えると ``%H`` が 0 に戻ることを確認する（``strftime`` と同じ挙動）。"""
        clock = iter([0.0, 90000.0])  # ちょうど 25 時間
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H:%M:%S"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 01:00:00"]

    def test_logs_strftime_other_directives_work(self, caplog, monkeypatch):
        """``%M`` / ``%S`` などの strftime 記号がそのまま動くことを確認する。

        3725 秒 = 1 時間 2 分 5 秒 → ``%M分%S秒`` で ``02分05秒``、
        ``%I:%M %p`` で ``01:02 AM``。 ``hh`` / ``mm`` / ``ss`` 独自記号は
        持たないので ``%M`` がそのまま「時を引いた残り」を表す形になる
        （``strftime`` の規約と同じ）。
        """
        clock = iter([0.0, 3725.0])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%M分%S秒"),
        ):
            pass
        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 02分05秒"]

    def test_logs_strftime_12_hour_with_am_pm(self, caplog, monkeypatch):
        """``%I`` / ``%p`` で 12 時間制＋AM/PM の表示になることを確認する（strftime の規約）。"""
        clock = iter([0.0, 3725.0])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%I:%M %p"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 01:02 AM"]

    def test_logs_strftime_double_percent(self, caplog, monkeypatch):
        """``%%`` で ``%`` を文字として出力できることを確認する（``strftime`` と同じ）。"""
        clock = iter([0.0, 3600.0])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer("処理", time_format="%H%%"),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["処理: 01%"]

    @pytest.mark.parametrize(
        ("seconds", "time_format", "expected"),
        [
            # 四捨五入と 24 時間ループの境界。
            (0, "%H:%M:%S", "00:00:00"),
            (59, "%H:%M:%S", "00:00:59"),
            (59.4, "%H:%M:%S", "00:00:59"),  # 秒未満は四捨五入（.4 は捨て）
            (59.6, "%H:%M:%S", "00:01:00"),  # .6 で分へ繰り上げ（%S 60 にはしない）
            (59.9, "%H:%M:%S", "00:01:00"),  # .9 で分へ繰り上げ
            (60, "%H:%M:%S", "00:01:00"),
            (3661, "%H:%M:%S", "01:01:01"),
            (3661.7, "%H:%M:%S", "01:01:02"),  # 秒未満を四捨五入
            (86400 + 90, "%H:%M:%S", "00:01:30"),  # 24:01:30 → 00:01:30（strftime と同じ）
            # 0.5 秒は 1 秒側に丸める（偶数丸めでは 0 になる値の代表）。
            (0.5, "%H:%M:%S", "00:00:01"),
            (2.5, "%H:%M:%S", "00:00:03"),  # round() 偶数丸めなら 00:00:02 になるところで 03
            (3599.5, "%H:%M:%S", "01:00:00"),  # round() 偶数丸めなら 00:59:59
            # strftime の他の記号（日本語や AM/PM）。
            (3725, "%M分%S秒", "02分05秒"),
            (3725, "%I:%M %p", "01:02 AM"),
            # %% で % を文字として出力。
            (3600, "%H%%", "01%"),
        ],
    )
    def test_format_elapsed_strftime(self, seconds, time_format, expected):
        """``_format_elapsed`` が ``strftime`` と同じ書き方で正しく整形することを確認する。

        整数秒に四捨五入してから ``datetime.time`` に詰めるので、``%S`` 部分が
        ``60`` になる値は出ない（分への繰り上げで吸収する）。 ``0.5`` と
        ``2.5`` と ``3599.5`` は偶数丸め（``round()``）と結果が分かれる値で、
        ここで実装が ``int(seconds + 0.5)`` であることを保証する。
        ``datetime.time`` の制約で 24 時間を超えると ``%H`` が 0 に戻る
        （``strftime`` と同じ）。
        """
        assert timer_module._format_elapsed(seconds, time_format) == expected

    def test_format_elapsed_default(self):
        """``time_format=None`` で小数2桁＋「秒」の形に整形されることを確認する。"""
        assert timer_module._format_elapsed(3.21, None) == "3.21秒"

    def test_format_elapsed_passes_through_strftime_errors(self):
        """``strftime`` が受け付けない書式は、その例外をそのまま通すことを確認する。

        例: ``%Q`` は ``strftime`` が認識しないディレクティブなので
        ``ValueError``。 独自に判断して握りつぶさない（呼び出し側がすぐ
        気づけるように）。
        """
        with pytest.raises(ValueError):
            timer_module._format_elapsed(3725, "%Q")

    @pytest.mark.parametrize(
        "bad_format",
        [
            # 旧 hh:mm:ss 形式。strftime だとそのまま "hh:mm:ss" が出るだけなので
            # ValueError にする。
            "hh:mm:ss",
            # ``%`` を1つも含まない単純な文字列。
            "abc",
            # 空文字。
            "",
        ],
    )
    def test_time_format_without_percent_raises(self, bad_format):
        """``%`` を1つも含まない ``time_format`` は ``ValueError`` にする。

        ``%%`` だけは ``%`` を含むので通る（``strftime`` の挙動と同じ）。
        旧 ``"hh:mm:ss"`` を指定しても何も起きない事故を防ぐ。
        """
        with pytest.raises(ValueError, match="%H:%M:%S"):
            Timer("処理", time_format=bad_format)

    def test_time_format_with_only_double_percent_is_allowed(self):
        """``%%`` だけを含む ``time_format`` はそのまま通す（``strftime`` と同じ）。"""
        # ``%%`` を含むので ``__init__`` の ValueError 検査には引っかからない。
        # ``%H`` などは無いが、書式自体には ``%`` が含まれるので許可する。
        Timer("処理", time_format="%%")

    def test_custom_message_in_with_block(self, caplog):
        """message を差し替えると with でその文言で出ることを確認する。"""
        with caplog.at_level(logging.INFO), Timer("CSV読み込み", message="{elapsed} [{name}]"):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["0.00秒 [CSV読み込み]"]

    def test_custom_message_in_decorator(self, caplog):
        """デコレータでも差し替えた文言で出ることを確認する（``__call__`` の引き継ぎ漏れ検出）。"""

        @Timer("売上集計", message="{elapsed} [{name}]")
        def aggregate():
            return 42

        with caplog.at_level(logging.INFO):
            assert aggregate() == 42

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["0.00秒 [売上集計]"]

    def test_custom_message_and_time_format_in_with_block(self, caplog, monkeypatch):
        """message と ``time_format`` を両方変えたとき、with でその形で出ることを確認する。"""
        clock = iter([0.0, 3725.0])  # 1h 2m 5s
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        with (
            caplog.at_level(logging.INFO),
            Timer(
                "CSV読み込み",
                message="{name} -> {elapsed}",
                time_format="%H時間%M分%S秒",
            ),
        ):
            pass

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["CSV読み込み -> 01時間02分05秒"]

    def test_custom_message_and_time_format_in_decorator(self, caplog, monkeypatch):
        """デコレータでも message と ``time_format`` の両方が引き継がれて出ることを確認する。

        ``__call__`` が ``time_format`` を内側 Timer に渡していないと、
        ここで ``time_format`` が無視されて既定の ``"0.00秒"`` が出る
        （引き継ぎ漏れの検出用）。
        """
        clock = iter([0.0, 3725.0])
        monkeypatch.setattr(timer_module.time, "perf_counter", lambda: next(clock))

        @Timer("売上集計", message="{name} -> {elapsed}", time_format="%H時間%M分%S秒")
        def aggregate():
            return 42

        with caplog.at_level(logging.INFO):
            assert aggregate() == 42

        messages = [record.getMessage() for record in caplog.records]
        assert messages == ["売上集計 -> 01時間02分05秒"]

    def test_decorator_measures_each_call(self, caplog):
        """デコレータ形式で使え、呼び出しごとにログが出ることを確認する。"""

        @Timer("集計処理")
        def aggregate():
            return 42

        with caplog.at_level(logging.INFO):
            assert aggregate() == 42
            aggregate()

        assert caplog.text.count("集計処理") == 2

    def test_decorator_preserves_function_name(self):
        """デコレータでも関数名が保たれることを確認する。"""

        @Timer("処理")
        def my_func():
            pass

        assert my_func.__name__ == "my_func"

    # ---- 実装側の挙動を間接的に保証するテスト ----

    def test_int_seconds_plus_half_matters_for_rounding(self):
        """``int(seconds + 0.5)`` の四捨五入（切り捨て／``round()`` と結果が違う値）を保証する。

        ここで期待値を変える（``int(seconds)`` にする／``round(seconds)`` にする）と
        落ちるので、検算用に独立したテストとして残している。 ``2.5`` は
        ``int(2.5) = 2`` / ``round(2.5) = 2`` / ``int(2.5 + 0.5) = 3`` の3つで
        結果が違う値で、実装が ``int(seconds + 0.5)`` であることを保証する
        代表値。 ``0.5`` と ``3599.5`` も追加で切り捨てと分を分引く。
        """
        # 0.5 は int(0.5) = 0 → 00:00:00、round(0.5) = 0 → 00:00:00、
        # int(0.5 + 0.5) = 1 → 00:00:01。int と round の両方で結果が違う。
        assert timer_module._format_elapsed(0.5, "%H:%M:%S") == "00:00:01"
        # 2.5 は int(2.5) = 2 → 00:00:02、round(2.5) = 2 → 00:00:02、
        # int(2.5 + 0.5) = 3 → 00:00:03。int と round の両方で結果が違う。
        assert timer_module._format_elapsed(2.5, "%H:%M:%S") == "00:00:03"
        # 3599.5 は int(3599.5) = 3599 → 00:59:59、round(3599.5) = 3600 → 01:00:00、
        # int(3599.5 + 0.5) = 3600 → 01:00:00。int でだけ結果が違う
        # （切り捨てへの退行を検知する）。
        assert timer_module._format_elapsed(3599.5, "%H:%M:%S") == "01:00:00"

    def test_value_error_check_matters_for_silent_pass_through(self):
        """``%`` を含む検査を外すと ``"hh:mm:ss"`` がそのまま通る事故を防ぐ。

        ``strftime`` は ``hh`` / ``mm`` / ``ss`` を何も置換しないので、
        検査を外すと ``"hh:mm:ss"`` がそのまま文字列として出てしまい、
        旧方式と書いて利用者が無意味な表示に気づけない。 ``Timer`` の
        ``__init__`` が ``ValueError`` で止めることで、書いた瞬間に
        直し方が案内される。
        """
        # 旧方式（``hh:mm:ss``）を書くと ValueError で止まる。
        with pytest.raises(ValueError, match="%H:%M:%S"):
            Timer("処理", time_format="hh:mm:ss")


class TestZipFolder:
    """zip_folder のテスト。"""

    def test_zips_folder_recursively(self, tmp_path):
        """サブフォルダも含めて圧縮されることを確認する。"""
        folder = tmp_path / "reports"
        (folder / "sub").mkdir(parents=True)
        (folder / "a.txt").write_text("A", encoding="utf-8")
        (folder / "sub" / "b.txt").write_text("B", encoding="utf-8")

        dst = zip_folder(folder)

        assert dst == tmp_path / "reports.zip"
        with zipfile.ZipFile(dst) as zf:
            assert sorted(zf.namelist()) == ["a.txt", "sub/b.txt"]

    def test_custom_destination(self, tmp_path):
        """出力先を指定でき、親フォルダも自動作成されることを確認する。"""
        folder = tmp_path / "reports"
        folder.mkdir()
        (folder / "a.txt").write_text("A", encoding="utf-8")

        dst = zip_folder(folder, tmp_path / "backup" / "2026" / "r.zip")

        assert dst.exists()

    def test_missing_folder_raises(self, tmp_path):
        """存在しないフォルダは FileNotFoundError になることを確認する。"""
        with pytest.raises(FileNotFoundError):
            zip_folder(tmp_path / "なし")

    def test_default_name_preserves_dots_in_folder_name(self, tmp_path):
        """出力先省略時はフォルダ名中のドットを残して .zip を付ける。"""
        folder = tmp_path / "売上 v1.2"
        folder.mkdir()

        assert zip_folder(folder) == tmp_path / "売上 v1.2.zip"


class TestZipFiles:
    """zip_files のテスト。"""

    def test_zips_selected_files_flat(self, tmp_path):
        """選んだファイルがフラットに入ることを確認する。"""
        a = tmp_path / "a.txt"
        b = tmp_path / "sub" / "b.txt"
        b.parent.mkdir()
        a.write_text("A", encoding="utf-8")
        b.write_text("B", encoding="utf-8")

        dst = zip_files([a, b], tmp_path / "out.zip")

        with zipfile.ZipFile(dst) as zf:
            assert sorted(zf.namelist()) == ["a.txt", "b.txt"]

    def test_missing_file_raises(self, tmp_path):
        """存在しないファイルが含まれると FileNotFoundError になることを確認する。"""
        with pytest.raises(FileNotFoundError):
            zip_files([tmp_path / "なし.txt"], tmp_path / "out.zip")

    def test_missing_file_does_not_break_existing_zip(self, tmp_path):
        """入力不足で失敗しても既存 zip の内容を維持する。"""
        dst = tmp_path / "out.zip"
        with zipfile.ZipFile(dst, "w") as zf:
            zf.writestr("existing.txt", "existing")

        with pytest.raises(FileNotFoundError):
            zip_files([tmp_path / "なし.txt"], dst)

        with zipfile.ZipFile(dst) as zf:
            assert zf.read("existing.txt").decode() == "existing"

    def test_duplicate_names_raise(self, tmp_path):
        """別フォルダにある大文字小文字違いの同名ファイルはエラーにする。"""
        first = tmp_path / "A" / "report.xlsx"
        second = tmp_path / "B" / "REPORT.xlsx"
        first.parent.mkdir()
        second.parent.mkdir()
        first.touch()
        second.touch()

        with pytest.raises(ValueError, match="同じ名前"):
            zip_files([first, second], tmp_path / "out.zip")


class TestUnzip:
    """unzip のテスト。"""

    def test_extracts_next_to_zip(self, tmp_path):
        """出力先省略時は zip の隣に同名フォルダで展開されることを確認する。"""
        folder = tmp_path / "data"
        folder.mkdir()
        (folder / "a.txt").write_text("中身", encoding="utf-8")
        src = zip_folder(folder)
        (folder / "a.txt").unlink()  # 元は消しても zip から復元できる

        dst = unzip(src, tmp_path / "展開先")

        assert (dst / "a.txt").read_text(encoding="utf-8") == "中身"

    def test_japanese_filenames_from_cp932_zip(self, tmp_path):
        """Windows 製 zip（cp932 ファイル名）が文字化けせず展開されることを確認する。

        zipfile は非 ASCII 名に自動で UTF-8 フラグを立てるため、
        内部メソッドを上書きして「cp932 バイト列 + UTF-8 フラグなし」という
        Windows エクスプローラーの「圧縮」が作る zip を再現する。
        """
        name_bytes = "売上レポート.txt".encode("cp932")

        class Cp932ZipInfo(zipfile.ZipInfo):
            def _encodeFilenameFlags(self):
                return name_bytes, 0  # UTF-8 フラグ（0x800）を立てない

        src = tmp_path / "win.zip"
        with zipfile.ZipFile(src, "w") as zf:
            zf.writestr(Cp932ZipInfo("dummy.txt"), "データ")

        dst = unzip(src, tmp_path / "out")

        assert (dst / "売上レポート.txt").exists()

    def test_utf8_zip_extracts_correctly(self, tmp_path):
        """UTF-8 の zip（Python 製など）もそのまま正しく展開されることを確認する。"""
        folder = tmp_path / "日本語フォルダ"
        folder.mkdir()
        (folder / "帳票.txt").write_text("OK", encoding="utf-8")
        src = zip_folder(folder)

        dst = unzip(src, tmp_path / "out")

        assert (dst / "帳票.txt").read_text(encoding="utf-8") == "OK"


class TestAtomicWrite:
    """atomic_write（一時ファイル経由の安全な書き込み）のテスト。

    「置き換え中にプロセスが落ちても中途半端にならない」前提を固める。
    書き終わるまで ``path`` は触らず、最後に ``os.replace`` で一括入れ替えする
    ことで、``path`` を読んでいる側が半端な状態を見ないようにする。
    """

    def test_replaces_path_after_block_succeeds(self, tmp_path):
        """ブロック内で書いた内容が、ブロック終了後に path へ反映される。"""
        target = tmp_path / "out" / "config.ini"
        target.parent.mkdir()

        with atomic_write(target) as tmp:
            tmp.write_text("new", encoding="utf-8")

        assert target.read_text(encoding="utf-8") == "new"

    def test_does_not_create_parent_folder(self, tmp_path):
        """**親フォルダは勝手に作らない。** 無ければそのまま失敗する。

        書き間違えたパスへ勝手にフォルダを作ると、**誰も見ない場所へ
        出力し続けても気づけない**（保存先を勝手に作らない、という
        Downloader の判断と同じ理由）。作る必要があるなら呼ぶ側が明示する。
        """
        target = tmp_path / "存在しない" / "out.ini"

        with pytest.raises(FileNotFoundError), atomic_write(target) as tmp:
            tmp.write_text("x", encoding="utf-8")

        assert not target.exists()
        assert not target.parent.exists(), "親フォルダを勝手に作っている"

    def test_overwrites_existing_target(self, tmp_path):
        """置き換え先に既存ファイルがあれば上書きする。"""
        target = tmp_path / "config.ini"
        target.write_text("old", encoding="utf-8")

        with atomic_write(target) as tmp:
            tmp.write_text("new", encoding="utf-8")

        assert target.read_text(encoding="utf-8") == "new"

    def test_leaves_target_untouched_when_block_raises(self, tmp_path):
        """ブロック内で例外が出ると、置き換え先はそのまま元の状態を保つ。"""
        target = tmp_path / "config.ini"
        target.write_text("before", encoding="utf-8")

        class _Boom(Exception):
            pass

        with pytest.raises(_Boom), atomic_write(target) as tmp:
            tmp.write_text("after", encoding="utf-8")
            raise _Boom

        assert target.read_text(encoding="utf-8") == "before"

    def test_does_not_leave_temp_file_when_block_raises(self, tmp_path):
        """ブロック内で例外が出ると、一時ファイルがフォルダに残らない。"""
        target = tmp_path / "config.ini"
        target.write_text("before", encoding="utf-8")

        class _Boom(Exception):
            pass

        with (
            pytest.raises(_Boom),
            atomic_write(target) as tmp,
        ):
            tmp.write_text("after", encoding="utf-8")
            raise _Boom

        # ~config.ini.<uuid>.tmp が残っていないこと
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("~config.ini.")]
        assert leftovers == []

    def test_does_not_leave_temp_file_when_replace_fails(self, tmp_path, monkeypatch):
        """``os.replace`` が失敗しても一時ファイルが残らない。"""
        target = tmp_path / "config.ini"
        target.write_text("before", encoding="utf-8")

        def fail_replace(_self, _other):
            raise OSError("replace failed")

        monkeypatch.setattr("pathlib.Path.replace", fail_replace)

        with (
            pytest.raises(OSError, match="replace failed"),
            atomic_write(target) as tmp,
        ):
            tmp.write_text("after", encoding="utf-8")

        assert target.read_text(encoding="utf-8") == "before"
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith("~config.ini.")]
        assert leftovers == []

    def test_temp_file_lives_in_target_folder(self, tmp_path):
        """一時ファイルは同じフォルダに作られる（``os.replace`` は同一ドライブ必須）。"""
        target = tmp_path / "out" / "config.ini"
        target.parent.mkdir()

        with atomic_write(target) as tmp:
            assert tmp.parent == target.parent
            tmp.write_text("x", encoding="utf-8")
