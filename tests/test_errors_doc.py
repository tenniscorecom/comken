"""comken/tools/errors_doc.py（エラー対応ガイドの自動生成）を検証する。

docs/ERRORS.md は手書き部分（マーカーより上）と自動生成部分（下）が同じファイルにある。
作り直すたびに手書き部分が消えたり変わったりすると、利用者が書いた対処が失われる。
"""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from comken.tools import errors_doc
from comken.tools.errors_doc import ERRORS_GENERATED_MARKER, update_errors_doc

_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE_ERRORS = _ROOT / "comken" / "templates" / "新規プロジェクト" / "docs" / "ERRORS.md"

HANDWRITTEN = "# エラー対応ガイド\n\n## まず試すこと\n\n1. Excel を閉じる\n"
PROJECT_HEADING = f"## {errors_doc.PROJECT_ERRORS_HEADING}"
PROJECT_PACKAGE_NAME = "errors_doc_testproj"

# テスト用プロジェクトの例外。意味・発生箇所・対処をすべて書いた、ひな形どおりの形
PROJECT_ERRORS_SOURCE = '''
from comken.exceptions import ComkenError, ExcelError


class OrderFileMissingError(ComkenError):
    """受注ファイルが届いていない

    発生箇所: src.run.run()

    対処:
        受注システムから今日のファイルを出力し直す。
        出力できなければ管理者へ
    """


class OrderSheetBrokenError(ExcelError):
    """受注表の見出しが崩れている

    対処:
        受注表の1行目を元に戻す
    """
'''


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture
def project_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ModuleType]:
    """プロジェクトの src に見立てた一時パッケージ（例外の定義が1ファイル）。"""
    package_dir = tmp_path / "pkgroot" / PROJECT_PACKAGE_NAME
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "errors.py").write_text(PROJECT_ERRORS_SOURCE, encoding="utf-8")
    monkeypatch.syspath_prepend(str(package_dir.parent))
    yield importlib.import_module(PROJECT_PACKAGE_NAME)
    for name in [m for m in sys.modules if m.split(".")[0] == PROJECT_PACKAGE_NAME]:
        del sys.modules[name]


def test_keeps_handwritten_part_exactly(tmp_path: Path) -> None:
    """マーカーより上は1文字も変えず、下だけを作り直す。"""
    path = tmp_path / "docs" / "ERRORS.md"
    path.parent.mkdir()
    path.write_text(f"{HANDWRITTEN}\n{ERRORS_GENERATED_MARKER}\n\n古い表\n", encoding="utf-8")

    assert update_errors_doc(tmp_path) is True

    text = _read(path)
    handwritten, marker, generated = text.partition(ERRORS_GENERATED_MARKER)
    assert handwritten == HANDWRITTEN + "\n"
    assert marker
    assert "古い表" not in generated
    assert "| `SheetNotFoundError` |" in generated


def test_appends_marker_when_missing(tmp_path: Path) -> None:
    """マーカーが無いファイルは、手書き部分を残して末尾に空行・マーカー・表を足す。"""
    path = tmp_path / "docs" / "ERRORS.md"
    path.parent.mkdir()
    path.write_text(HANDWRITTEN, encoding="utf-8")

    assert update_errors_doc(tmp_path) is True

    text = _read(path)
    assert text.startswith(f"{HANDWRITTEN}\n{ERRORS_GENERATED_MARKER}\n\n## ")
    assert text.count(ERRORS_GENERATED_MARKER) == 1


def test_is_idempotent(tmp_path: Path) -> None:
    """2回目は何も変えず False を返す（内容が同じならファイルを書き直さない）。"""
    path = tmp_path / "docs" / "ERRORS.md"
    path.parent.mkdir()
    path.write_text(HANDWRITTEN, encoding="utf-8")
    update_errors_doc(tmp_path)
    first = path.read_bytes()

    assert update_errors_doc(tmp_path) is False
    assert path.read_bytes() == first


def test_creates_missing_file(tmp_path: Path) -> None:
    """ファイルもフォルダも無ければ作る。"""
    path = tmp_path / "docs" / "ERRORS.md"

    assert update_errors_doc(tmp_path) is True

    text = _read(path)
    assert text.startswith(f"{ERRORS_GENERATED_MARKER}\n\n## ")
    assert "| `ComkenError` |" in text


def test_project_errors_listed_before_comken_errors(
    tmp_path: Path, project_package: ModuleType
) -> None:
    """プロジェクトの例外が、意味と対処つきで comken の表の前に載る。"""
    path = tmp_path / "docs" / "ERRORS.md"
    path.parent.mkdir()
    path.write_text(HANDWRITTEN, encoding="utf-8")

    update_errors_doc(tmp_path, project_package=project_package)

    generated = _read(path).partition(ERRORS_GENERATED_MARKER)[2]
    project_part, excel_heading, _ = generated.partition("## Excel のエラー")
    assert excel_heading, "comken の表が出ていない"
    assert PROJECT_HEADING in project_part
    assert (
        "| `OrderFileMissingError` | 受注ファイルが届いていない | "
        "受注システムから今日のファイルを出力し直す。出力できなければ管理者へ |"
    ) in project_part
    # comken のカテゴリ例外を親にしたものも、プロジェクトで定義したものとして載る
    assert "| `OrderSheetBrokenError` | 受注表の見出しが崩れている | 受注表の1行目を元に戻す |" in (
        project_part
    )
    # import しただけの comken の例外は、プロジェクトの表に入れない
    assert "`ExcelError`" not in project_part
    assert "`ComkenError`" not in project_part


def test_project_section_absent_without_project_package(
    tmp_path: Path, project_package: ModuleType
) -> None:
    """project_package を渡さなければ、プロジェクトの節は出ない。"""
    path = tmp_path / "docs" / "ERRORS.md"

    update_errors_doc(tmp_path)

    text = _read(path)
    assert PROJECT_HEADING not in text
    assert "OrderFileMissingError" not in text


def test_project_section_absent_when_project_has_no_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """プロジェクトに例外が1つも無ければ、空の表を出さない（ひな形の初期状態）。"""
    package_dir = tmp_path / "pkgroot" / "errors_doc_emptyproj"
    package_dir.mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "run.py").write_text("def run() -> None:\n    pass\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(package_dir.parent))
    try:
        package = importlib.import_module("errors_doc_emptyproj")
        path = tmp_path / "docs" / "ERRORS.md"
        update_errors_doc(tmp_path, project_package=package)
    finally:
        for name in [m for m in sys.modules if m.split(".")[0] == "errors_doc_emptyproj"]:
            del sys.modules[name]

    assert PROJECT_HEADING not in _read(path)


def test_project_error_without_treatment_stops(tmp_path: Path, project_package: ModuleType) -> None:
    """対処の無い例外は表に空欄で載せず、止める（comken の例外と同じ扱い）。"""
    (Path(project_package.__file__ or "").parent / "broken.py").write_text(
        "from comken.exceptions import ComkenError\n\n\n"
        "class NoTreatmentError(ComkenError):\n"
        '    """対処を書き忘れた"""\n',
        encoding="utf-8",
    )
    # import 済みのパッケージに後からファイルを足したので、import の探索結果を作り直させる
    importlib.invalidate_caches()
    path = tmp_path / "docs" / "ERRORS.md"

    with pytest.raises(ValueError, match="NoTreatmentError"):
        update_errors_doc(tmp_path, project_package=project_package)
    assert not path.exists()


def test_template_errors_doc_is_up_to_date() -> None:
    """ひな形の docs/ERRORS.md の表が、今の comken の例外と一致している。

    古いまま配ると、新規プロジェクトが最初から古い説明を持つ。
    直すときは ``python tools/export_for_chat.py`` を実行する。
    """
    text = _read(_TEMPLATE_ERRORS)

    assert text.count(ERRORS_GENERATED_MARKER) == 1
    assert text == errors_doc._merged_errors_text(text)


def test_writes_only_docs_errors_md(tmp_path: Path) -> None:
    """置き場所は ``docs/ERRORS.md`` に固定で、プロジェクトのフォルダの直下などには作らない。"""
    update_errors_doc(tmp_path)

    created = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert created == ["docs/ERRORS.md"]
