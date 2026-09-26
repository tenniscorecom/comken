"""tools/check_v2_migration.py のテスト。

``tools/`` 以下のスクリプトを import する流儀は ``tests/test_export_for_chat.py``
に合わせる（pyproject.toml の pytest pythonpath で tools/ が解決される）。
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

import check_v2_migration
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(tmp_path: Path, name: str, content: str) -> Path:
    """UTF-8 でファイルを作成し、パスを返す。"""
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _run_cli(tmp_path: Path, *extra_folders: Path) -> subprocess.CompletedProcess[str]:
    """CLI を subprocess で実行し、結果を返す（終了コード・標準出力）。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "check_v2_migration.py"),
            str(tmp_path),
            *extra_folders,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )


class TestDetectsRemovedNames:
    """v2.0.0 で消えた名前を正しく検出すること。"""

    def test_from_comken_constants(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "from comken.constants import Color\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[消えたモジュール] comken.constants" in result.stdout

    def test_from_comken_core_clock(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "from comken.core.clock import now\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[消えたモジュール] comken.core.clock" in result.stdout

    def test_browsers_public_name(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "b = Browsers()\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[消えた公開名] Browsers" in result.stdout

    def test_sheet_set_border(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", 'sheet.set_border("A1")\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[Sheet削除メソッド] set_border" in result.stdout

    def test_date_file_finder_dated(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", 'DateFileFinder(folder).dated("a.csv")\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[DateFileFinder削除メソッド] dated" in result.stdout

    def test_date_file_finder_prefix_with_class(self, tmp_path: Path) -> None:
        # ``DateFileFinder(...)`` を同じ行に含む ``.prefix(`` は検出する
        _write(tmp_path, "a.py", 'DateFileFinder(folder).prefix("a.csv")\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[DateFileFinder削除メソッド] prefix" in result.stdout

    def test_browser_site_name_conflict(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", 'NAME = "ams"\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[公認サイトNAME衝突] ams" in result.stdout

    def test_sheet_merge_cells_is_review_flag(self, tmp_path: Path) -> None:
        # openpyxl の worksheet にも ``merge_cells`` があるため「要確認」表示になる
        _write(tmp_path, "a.py", 'sheet.merge_cells("A1:B2")\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 1
        assert "[Sheet削除メソッド(要確認)] merge_cells" in result.stdout


class TestDoesNotDetectCurrentNames:
    """今の正しい書き方は誤検出しないこと。"""

    def test_current_color_import(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "from comken.toolbox.excel import Color\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 0
        assert "見つかりませんでした" in result.stdout

    def test_current_dates_now_import(self, tmp_path: Path) -> None:
        _write(tmp_path, "a.py", "from comken.core.dates import now\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 0

    def test_current_workday_call(self, tmp_path: Path) -> None:
        # 業務カレンダーは ``from comken.core.holidays import workday`` で今も使える
        _write(tmp_path, "a.py", "from comken.core.holidays import workday\n")
        _write(tmp_path, "b.py", "d2 = workday(d, 1)\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 0

    def test_date_name_builder_prefix_is_not_detected(self, tmp_path: Path) -> None:
        # ``DateNameBuilder(...).prefix()`` は今も有効なので誤検出しない
        _write(tmp_path, "a.py", 'DateNameBuilder("a.csv").prefix()\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 0
        assert "見つかりませんでした" in result.stdout

    def test_custom_site_name_is_not_flagged(self, tmp_path: Path) -> None:
        # プロジェクト固有の ``NAME`` は衝突しない
        _write(tmp_path, "a.py", 'NAME = "my_site"\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 0

    def test_mixed_clean_files_report_zero(self, tmp_path: Path) -> None:
        # 全部「今の正しい書き方」のファイルだけのフォルダは 0 件
        _write(tmp_path, "a.py", "from comken.core.dates import now\n")
        _write(tmp_path, "b.py", "from comken.toolbox.excel import Excel\n")
        _write(tmp_path, "c.py", "from comken.core.holidays import workday\n")
        _write(tmp_path, "d.py", 'DateNameBuilder("a.csv").prefix()\n')
        _write(tmp_path, "e.py", 'NAME = "project_site"\n')
        result = _run_cli(tmp_path)
        assert result.returncode == 0
        assert "見つかりませんでした" in result.stdout


class TestDirectoryExclusions:
    """走査対象の除外が効くこと。"""

    def test_comken_named_folder_is_skipped(self, tmp_path: Path) -> None:
        # ``comken/`` という名前のフォルダは飛ばす（ライブラリ側の実装を誤検出しないため）
        comken_subdir = tmp_path / "comken"
        comken_subdir.mkdir()
        _write(comken_subdir, "a.py", "from comken.constants import Color\n")
        result = _run_cli(tmp_path)
        assert result.returncode == 0
        assert "見つかりませんでした" in result.stdout


class TestIntegrityChecks:
    """埋め込み一覧が今の comken の公開名と衝突していないことを確認する。"""

    def test_removed_modules_are_not_importable_now(self) -> None:
        # 消えたモジュールは今 ``import`` できない（=一覧が正しいことの裏付け）
        for module_name in check_v2_migration.REMOVED_MODULES:
            with pytest.raises((ImportError, ModuleNotFoundError)):
                importlib.import_module(module_name)

    def test_removed_public_names_do_not_overlap_with_current_all(self) -> None:
        # 「消えた公開名」の埋め込み一覧に、今の comken の ``__all__`` の
        # いずれかが **1つも** 含まれていないことを確認する。一覧の取り違え検出。
        current_names: set[str] = set()
        for init_path in (REPO_ROOT / "comken").rglob("__init__.py"):
            tree_module = ".".join(init_path.relative_to(REPO_ROOT.parent).with_suffix("").parts)
            # rglob で取れるのは comken/X/Y/__init__.py。comken 以降だけ取り出す。
            parts = init_path.relative_to(REPO_ROOT).with_suffix("").parts
            tree_module = ".".join(("comken", *parts)).rstrip(".")
            try:
                module = importlib.import_module(tree_module)
            except Exception:
                continue
            for name in getattr(module, "__all__", ()):
                current_names.add(name)
        overlap = set(check_v2_migration.REMOVED_PUBLIC_NAMES) & current_names
        assert overlap == set(), (
            f"「消えた公開名」一覧に今の comken の公開名が混入しています: {sorted(overlap)}"
        )


class TestImplementationDamage:
    """実装を壊したときに期待どおり落ちることの確認。"""

    def test_word_boundary_makes_correct_writing_flagged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """単語境界（``\\b``）を外すと正しい書き方も誤検出される。

        ``_WORD_RE_TEMPLATE`` を ``r"{name}"`` に差し替えると、
        ``BrowsersPlus`` の中の ``Browsers`` まで拾ってしまう。
        """
        # 単語境界チェックを意図的に壊す: ``r"{name}"`` に置換すると
        # ``BrowsersPlus`` の中の ``Browsers`` まで拾ってしまう
        monkeypatch.setattr(
            check_v2_migration,
            "_WORD_RE_TEMPLATE",
            r"{name}",
        )
        # 「BrowsersPlus」のような単語を含む行を直接検査する
        hits = check_v2_migration._check_removed_public_names("BrowsersPlus = 1")
        # 単語境界が無いので ``BrowsersPlus`` の中の ``Browsers`` が拾われる
        names = [name for name, _ in hits]
        assert "Browsers" in names

    def test_word_boundary_keeps_clean_when_intact(self) -> None:
        """単語境界が効いているとき ``BrowsersPlus`` は誤検出しない。"""
        hits = check_v2_migration._check_removed_public_names("BrowsersPlus = 1")
        names = [name for name, _ in hits]
        assert "Browsers" not in names

    def test_date_file_finder_same_line_rule_prevents_false_positive(self, tmp_path: Path) -> None:
        """``DateFileFinder`` を含まない行の ``.prefix(`` は検出されない。"""
        _write(tmp_path, "a.py", 'DateNameBuilder("a.csv").prefix()\n')
        result = _run_cli(tmp_path)
        # ``DateNameBuilder(...).prefix()`` は今も有効
        assert result.returncode == 0
        assert "見つかりませんでした" in result.stdout

    def test_dropping_same_line_check_would_cause_false_positive(self) -> None:
        """「同じ行に ``DateFileFinder`` を含む」条件を消すと誤検出する。"""

        # 検出関数を「同じ行に ``DateFileFinder`` を含む」条件ナシで組み立てる
        def broken_check(line: str) -> list[tuple[str, str]]:
            hits: list[tuple[str, str]] = []
            if re.search(r"\.prefix\s*\(", line):
                hits.append(("prefix", "DateFileFinder削除メソッド"))
            return hits

        # ``DateNameBuilder(...).prefix()`` を「正しい」行として渡す
        hits = broken_check('DateNameBuilder("a.csv").prefix()')
        # 条件が消えたので ``DateNameBuilder`` の ``prefix()`` まで拾ってしまう
        assert hits  # 誤検出が起きる = 条件が壊れている証拠
        # 比較用に、元の実装では拾わないことも示す
        good_hits = check_v2_migration._check_date_file_finder_methods(
            'DateNameBuilder("a.csv").prefix()'
        )
        assert good_hits == []
