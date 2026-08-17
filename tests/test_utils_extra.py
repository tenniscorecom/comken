"""
retry / Timer / zip ユーティリティのテスト。

実行方法:
    リポジトリのルートで python -m pytest tests/ -v
"""

import logging
import zipfile

import pytest

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

    def test_logs_name_and_seconds(self, caplog):
        """処理名と秒数が INFO ログに出ることを確認する。"""
        with caplog.at_level(logging.INFO), Timer("CSV読み込み"):
            pass

        assert "CSV読み込み" in caplog.text
        assert "秒" in caplog.text

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
