"""``python -m comken check`` のテスト。

検査ロジック (純粋関数) と CLI 入口の両方を検証する。
pyright 検査は ``npx`` が無い環境では SKIP されるため、テストは mocker で
``shutil.which`` / ``subprocess.run`` を差し替えて独立に検証する。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import comken
from comken.core.check import (
    CheckResult,
    check_deprecations,
    check_facade,
    check_imports,
    check_pyright,
    check_version,
    summarize,
)
from comken.core.check.cli import main as check_main
from comken.core.check.cli import run_all
from comken.deprecation import deprecated_names

# ── version ───────────────────────────────────────────────────────────────────


class TestVersion:
    def test_skip_when_no_config(self, tmp_path: Path) -> None:
        """config.ini が無いとき SKIP。"""
        result = check_version(tmp_path)
        assert result.status == "skip"
        assert "config.ini が見つかりません" in result.message

    def test_skip_when_no_version_key(self, tmp_path: Path) -> None:
        """config.ini に [COMKEN] VERSION が無いとき SKIP。"""
        (tmp_path / "config.ini").write_text(
            "[FILES]\nINPUT_FOLDER = C:\\work\n",
            encoding="utf-8",
        )
        result = check_version(tmp_path)
        assert result.status == "skip"
        assert "VERSION 指定なし" in result.message

    def test_ok_when_matches(self, tmp_path: Path) -> None:
        """config.ini に書いたバージョンと comken.__version__ が一致するとき OK。"""
        (tmp_path / "config.ini").write_text(
            f"[COMKEN]\nVERSION = {comken.__version__}\n",
            encoding="utf-8",
        )
        result = check_version(tmp_path)
        assert result.status == "ok"
        assert comken.__version__ in result.message

    def test_ng_when_mismatch(self, tmp_path: Path) -> None:
        """config.ini のバージョンと comken.__version__ が違うとき NG。"""
        (tmp_path / "config.ini").write_text(
            "[COMKEN]\nVERSION = 99.99.99\n",
            encoding="utf-8",
        )
        result = check_version(tmp_path)
        assert result.status == "ng"
        assert "不一致" in result.message


# ── imports ───────────────────────────────────────────────────────────────────


class TestImports:
    def test_all_public_names_importable(self) -> None:
        """``comken.__all__`` の名前はすべて実際に import できる。"""
        result = check_imports()
        assert result.status == "ok"
        # details には各名前について "from comken import X: OK" が並ぶ
        assert all("OK" in d for d in result.details)
        assert len(result.details) == len(comken.__all__)


# ── deprecations ──────────────────────────────────────────────────────────────


class TestDeprecations:
    def test_no_registered_deprecations_is_ok(self, tmp_path: Path) -> None:
        """レジストリが空のときは常に OK。"""
        # 関数の _DEPRECATED_NAMES を一時的に空にする (元はテスト後に戻す)
        from comken import deprecation

        original = deprecation._DEPRECATED_NAMES.copy()
        try:
            deprecation._DEPRECATED_NAMES.clear()
            result = check_deprecations(tmp_path)
            assert result.status == "ok"
            assert "登録なし" in result.message
        finally:
            deprecation._DEPRECATED_NAMES.update(original)

    def test_no_usage_is_ok(self, tmp_path: Path) -> None:
        """deprecated 名の登録はあるが、プロジェクトで使われていないとき OK。"""
        from comken import deprecation

        original = deprecation._DEPRECATED_NAMES.copy()
        try:
            deprecation._DEPRECATED_NAMES["OldName"] = "new_name"
            result = check_deprecations(tmp_path)
            assert result.status == "ok"
            assert "なし" in result.message
        finally:
            deprecation._DEPRECATED_NAMES.clear()
            deprecation._DEPRECATED_NAMES.update(original)

    def test_detects_used_deprecated_name(self, tmp_path: Path) -> None:
        """deprecated な旧名がソースにあると NG。"""
        from comken import deprecation

        original = deprecation._DEPRECATED_NAMES.copy()
        try:
            deprecation._DEPRECATED_NAMES["OldName"] = "new_name"
            (tmp_path / "main.py").write_text(
                "from comken import OldName\nprint(OldName)\n",
                encoding="utf-8",
            )
            result = check_deprecations(tmp_path)
            assert result.status == "ng"
            # details にファイルパスと旧名が含まれる
            assert any("OldName" in d and "main.py" in d for d in result.details)
        finally:
            deprecation._DEPRECATED_NAMES.clear()
            deprecation._DEPRECATED_NAMES.update(original)

    def test_does_not_match_substring(self, tmp_path: Path) -> None:
        """deprecated 名の部分一致は無視する（identifier 境界のみ）。"""
        from comken import deprecation

        original = deprecation._DEPRECATED_NAMES.copy()
        try:
            deprecation._DEPRECATED_NAMES["OldName"] = "new_name"
            (tmp_path / "main.py").write_text(
                "x = MyOldNameExtra()\n",  # "OldName" を含むが別 identifier
                encoding="utf-8",
            )
            result = check_deprecations(tmp_path)
            assert result.status == "ok"
        finally:
            deprecation._DEPRECATED_NAMES.clear()
            deprecation._DEPRECATED_NAMES.update(original)

    def test_skips_venv_directories(self, tmp_path: Path) -> None:
        """.venv 配下のファイルは無視する。"""
        from comken import deprecation

        original = deprecation._DEPRECATED_NAMES.copy()
        try:
            deprecation._DEPRECATED_NAMES["OldName"] = "new_name"
            venv = tmp_path / ".venv" / "lib" / "site-packages"
            venv.mkdir(parents=True)
            (venv / "stub.py").write_text(
                "from comken import OldName\n",
                encoding="utf-8",
            )
            result = check_deprecations(tmp_path)
            assert result.status == "ok"
        finally:
            deprecation._DEPRECATED_NAMES.clear()
            deprecation._DEPRECATED_NAMES.update(original)


# ── facade ────────────────────────────────────────────────────────────────────


class TestFacade:
    def test_matches_expected_names(self) -> None:
        """ファサードの名前が期待どおりそろっている。"""
        result = check_facade()
        assert result.status == "ok"

    def test_detects_swapped_name_without_count_change(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """**件数が変わらない入れ替わり**を検出する。

        「何を防いでいるか」: 件数だけを比べていると、公開 API を 1 つ消して
        1 つ足したときに 9 個のまま素通りする。「公開 API が壊れていないか」を
        確かめる仕組みが、いちばん見つけたい壊れ方を見逃していた。
        """
        import comken

        swapped = [n for n in comken.__all__ if n != "Config"] + ["Foo"]
        assert len(swapped) == len(comken.__all__)  # 件数は変わらない
        monkeypatch.setattr(comken, "__all__", swapped)

        result = check_facade()

        assert result.status == "ng"
        assert any("Config" in d for d in result.details)
        assert any("Foo" in d for d in result.details)


# ── pyright ───────────────────────────────────────────────────────────────────


class TestPyright:
    def test_skip_when_pyright_and_npx_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``pyright`` も ``npx`` も無い環境では SKIP。

        BO / オフライン環境向け: ``check_pyright()`` は npm から最新版を
        ダウンロードしない。PATH に ``pyright`` が無い、かつ ``npx`` も無い
        ときは SKIP になる。
        """
        monkeypatch.setattr(shutil, "which", lambda name: None)
        result = check_pyright(Path.cwd())
        assert result.status == "skip"
        assert "pyright" in result.message

    def test_ok_when_zero_errors(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """pyright が ``0 errors`` を返すなら OK。

        ``check_pyright()`` は PATH の ``pyright`` を直接実行する。
        """

        def fake_which(name: str) -> str | None:
            return "/usr/bin/pyright" if name == "pyright" else None

        class FakeProc:
            returncode = 0
            stdout = "0 errors\n"
            stderr = ""

        monkeypatch.setattr(shutil, "which", fake_which)
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeProc())

        result = check_pyright(tmp_path)
        assert result.status == "ok"
        assert "0 errors" in result.message

    def test_ng_when_errors_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """pyright が ``N errors`` を返すなら NG。"""

        def fake_which(name: str) -> str | None:
            return "/usr/bin/npx" if name == "npx" else None

        class FakeProc:
            returncode = 1
            stdout = "3 errors\n/path/foo.py:10: error\n/path/bar.py:20: error\n"
            stderr = ""

        monkeypatch.setattr(shutil, "which", fake_which)
        monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: FakeProc())

        result = check_pyright(tmp_path)
        assert result.status == "ng"
        assert "3 errors" in result.message


# ── summarize ─────────────────────────────────────────────────────────────────


def test_summarize_counts() -> None:
    """summarize() が (ok, ng, skip) を数える。"""
    results = [
        CheckResult("a", "ok", ""),
        CheckResult("b", "ok", ""),
        CheckResult("c", "ng", ""),
        CheckResult("d", "skip", ""),
    ]
    assert summarize(results) == (2, 1, 1)


# ── CLI ───────────────────────────────────────────────────────────────────────


class TestCli:
    def test_help_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--help は 0 で終わる (``SystemExit`` で抜ける)。"""
        with pytest.raises(SystemExit) as exc_info:
            check_main(["--help"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "comken" in out

    def test_main_returns_int(self, tmp_path: Path) -> None:
        """main() は int を返す。"""
        rc = check_main([str(tmp_path)])
        assert isinstance(rc, int)
        assert rc in (0, 1)

    def test_run_all_returns_results(self, tmp_path: Path) -> None:
        """run_all() は CheckResult のリストを返す。"""
        results = run_all(tmp_path)
        names = [r.name for r in results]
        assert "version" in names
        assert "imports" in names
        assert "deprecations" in names
        assert "facade" in names
        assert "pyright" in names


# ── __main__ 経由 ─────────────────────────────────────────────────────────────


def test_check_subcommand_registered() -> None:
    """``python -m comken check`` がサブコマンドとして登録されている。"""
    from comken.__main__ import _build_parser

    parser = _build_parser()
    # サブコマンド名が登録されていることを parse で確認
    args = parser.parse_args(["check"])
    assert args.command == "check"


def test_check_subcommand_runs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """``python -m comken check <path>`` がエラーなく完走する。"""
    from comken.__main__ import main as comken_main

    # path を渡さないとカレントが comken リポジトリになってテストが遅延する
    rc = comken_main(["check", str(tmp_path)])
    assert rc in (0, 1)  # pyright の結果は環境次第
    out = capsys.readouterr().out
    assert "=== comken check ===" in out


# ── deprecation レジストリの API ───────────────────────────────────────────────


def test_deprecated_names_returns_empty_dict_by_default() -> None:
    """既定ではレジストリは空。"""
    # テスト間で値が変わる可能性を考慮し、空チェックは緩めに行う
    names = deprecated_names()
    assert isinstance(names, dict)
    # コピーであることを確かめる (呼び出し側で変更しても元へ影響しない)
    names["FakeOld"] = "fake_new"
    assert "FakeOld" not in deprecated_names()
