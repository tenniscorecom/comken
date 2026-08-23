"""雛形（comken/templates/新規プロジェクト/）と create() の出力を検証する。

背景: 雛形の中身を実際に生成して読んだところ、実態と違う説明が複数見つかった。
       雛形を検証するテストが1つも無かったため、テストの新設で再発を防ぐ。

検証は2段で行う:

- **雛形を直接** — 生成前から間違っているもの（コピー手作業の案内や
  セクション名のズレ、相対 import）を捕まえる
- **tmp_path に create() した結果** — 生成後の姿で見えるズレ
  （`（プロジェクト名）` の置換漏れ、`PYTHON_LIBRARY` の片方置換漏れ）を捕まえる

「雛形のファイルを直接読むだけでは、置換後の姿を見逃す」ため、create() の
出力に対する検証も必ず行う。
"""

import configparser
import os
import re
import subprocess
import sys
from functools import partial
from pathlib import Path

import pytest

from comken.tools import new_project as new_project_mod

_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = _ROOT / "comken" / "templates" / "新規プロジェクト"


# ── helpers ──────────────────────────────────────────────────────────────────


def _read(path: Path, encoding: str = "utf-8") -> str:
    return path.read_text(encoding=encoding)


def _generated(tmp_path: Path, project_name: str = "売上集計") -> Path:
    """テンプレートを tmp_path に展開する（create() の呼び出し）。

    python_library には **comken パッケージの親**（＝ PYTHONPATH へ入れる場所）を渡す。
    create() の既定値と同じで、生成物の注入ロジックを本番と同じ経路で動かす。
    """
    return new_project_mod.create(project_name, tmp_path, _ROOT)


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    """create() で展開したプロジェクトフォルダ。"""
    return _generated(tmp_path)


# ── 1. 生成物の Python が構文を通る ──────────────────────────────────────────


def test_generated_python_files_compile(generated: Path) -> None:
    """main.py と src/**/*.py が構文エラーなくコンパイルできること。

    「何を防いでいるか」: テンプレートの書き換え時に構文が壊れていたら、
    プロジェクトを作った瞬間に ImportError や SyntaxError で詰まる。
    初手で捕まえる。`sites/<サイト名>/pages/` 配下まで再帰的に見るので、
    フォルダを分けても検査がすり抜けない。
    """
    py_files = [generated / "main.py", *sorted((generated / "src").rglob("*.py"))]
    assert py_files, "検査対象の .py が見つからない（src/ が空？）"
    for path in py_files:
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as e:
            pytest.fail(f"{path.relative_to(generated)} に構文エラー: {e}")


# ── 2. 生成物が ruff を通る ──────────────────────────────────────────────────


def test_generated_project_passes_ruff(generated: Path) -> None:
    """生成物のディレクトリで ruff check / ruff format --check が通ること。

    「何を防いでいるか」: 雛形のフォーマットが崩れていると、生成直後のプロジェクトで
    既に CI が落ちる。生成前のテンプレ時点で直しておく。

    ruff が無い環境では skip（社内 BO 環境のように pip が使えない場所でも
    テスト自体は動かしたい）。
    """
    for args in (["check", "."], ["format", "--check", "."]):
        cmd = [sys.executable, "-m", "ruff", *args]
        try:
            result = subprocess.run(
                cmd,
                cwd=generated,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError:
            pytest.skip("ruff がインストールされていない")
        if result.returncode == 0:
            continue
        pytest.fail(
            f"`{' '.join(cmd)}` が失敗（cwd={generated}）:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ── 4. docs/仕様書.md の設定表に書いた [SECTION] + KEY が example に実在する ─


def test_spec_doc_config_table_keys_exist_in_config_example(generated: Path) -> None:
    """`docs/仕様書.md` の「4. 設定（config.ini）」表の `[SECTION] KEY` が
    `config.ini.example` に実在する。

    「何を防いでいるか」: 仕様書側が `[REPORT]` で example 側が `[FILES]`、のような
    ズレを捕まえる。読み手は仕様書を見て example のキーを調べるので、両者が
    食い違うと example を直せない。
    """
    spec_text = _read(generated / "docs" / "仕様書.md")
    example_text = _read(generated / "config.ini.example")

    in_table = False
    pairs: list[tuple[str, str]] = []
    for line in spec_text.splitlines():
        if line.startswith("## 4. 設定"):
            in_table = True
            continue
        if in_table and line.startswith("## "):
            in_table = False
        if not in_table:
            continue
        # `| `[FILES]` | `OUTPUT_FOLDER` | ...` の形を読む
        m = re.match(r"\|\s*`\[([A-Z_]+)]`\s*\|\s*`?([A-Z_][A-Z0-9_]*)`?\s*\|", line)
        if m:
            pairs.append((m.group(1), m.group(2)))

    assert pairs, "docs/仕様書.md の設定表から [SECTION].KEY を読めなかった"

    parser = configparser.ConfigParser()
    parser.read_string(example_text)
    for section, key in pairs:
        assert parser.has_section(section), (
            f"仕様書の設定表は [{section}] を挙げているが、"
            f"config.ini.example に [{section}] セクションが無い"
        )
        assert parser.has_option(section, key), (
            f"仕様書の設定表は [{section}] {key} を挙げているが、"
            f"config.ini.example の [{section}] に {key} が無い"
        )


# ── 5. 「config.ini.example をコピーして名前を変える」式の案内が無い ─────────


_FORBIDDEN_COPIES = ("コピー", "複製", "名前を変")


def _markdown_paragraphs(text: str) -> list[str]:
    """Markdown / ini を「段落」に分ける。空行で区切る単純実装で十分。"""
    return [p for p in text.split("\n\n") if p.strip()]


def test_no_manual_copy_instructions_for_config_ini() -> None:
    """「example をコピーして名前を `config.ini` に変える」式の案内が雛形に無いこと。

    「何を防いでいるか」: 実際には `実行.bat`（または `python main.py`）を1度動かせば
    自動で作られる（`ConfigCreatedFromExampleError` で止まる）。Windows は拡張子を隠すので
    「コピーして名前を変える」を非エンジニアがやると `config.ini.example - コピー`
    ができて詰まる。**自動で作られるので手コピーは不要**、と README が案内している。

    検査の目印は `config.ini.example` ではなく **`config.ini`** にする。
    ファイル自身は「**このファイル**を config.ini にコピーして」のように
    自分の名前を書かずに済ませるので、`config.ini.example` を目印にすると
    そのファイルだけ検査をすり抜ける（2026-08-18 に、すり抜けを実測した）。
    """
    candidates = []
    for path in TEMPLATE_DIR.rglob("*"):
        if not path.is_file():
            continue
        # 関連するのは Markdown と ini/example
        if path.suffix.lower() not in {".md", ".ini"} and path.name != "config.ini.example":
            continue
        candidates.append(path)

    offenders: list[tuple[Path, str, str]] = []
    for path in candidates:
        text = _read(path)
        for paragraph in _markdown_paragraphs(text):
            if "config.ini" not in paragraph:
                continue
            for phrase in _FORBIDDEN_COPIES:
                if phrase in paragraph:
                    offenders.append((path, phrase, paragraph.splitlines()[0][:60]))
                    break
    assert not offenders, (
        f"雛形に「config.ini を手でコピーして作る」式の案内が残っている: {offenders}"
    )


# ── 6. 生成物に `（プロジェクト名）` が残らない ───────────────────────────────


_TEXT_SUFFIXES = {".md", ".py", ".bat", ".ini", ".toml", ".txt", ".json"}


def test_generated_project_has_no_project_name_placeholder(generated: Path) -> None:
    """create() の出力に `（プロジェクト名）` のプレースホルダが残らないこと。

    「何を防いでいるか」: 置換漏れがあると、リポジトリ名と雛形文の区別がつかなく
    なる。README で案内している手順（main.py の `run` に処理を書く、等）が
    そのまま動く形を維持する。
    """
    leftovers: list[tuple[Path, int]] = []
    for path in generated.rglob("*"):
        if not path.is_file():
            continue
        # 生成物のキャッシュ類は無視
        if "__pycache__" in path.parts or ".ruff_cache" in path.parts:
            continue
        if path.suffix.lower() not in _TEXT_SUFFIXES and path.name != "config.ini.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        count = text.count("（プロジェクト名）")
        if count:
            leftovers.append((path, count))
    assert not leftovers, f"（プロジェクト名）が残っている: {leftovers}"


# ── 7. 生成物の Markdown の相対リンクが全部解決する ───────────────────────────


_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\((?!https?://|#)([^)]+)\)")


def test_generated_markdown_relative_links_resolve(generated: Path) -> None:
    """生成物の Markdown 内リンク（http(s) とページ内 anchor を除く）が全て実在する。

    「何を防いでいるか」: `docs/使い方.md` から `ERRORS.md` へリンクしていて、
    ファイルが無いと業務側の人をエラー対応ページへ飛ばせずに困らせる。
    """
    missing: list[tuple[Path, str]] = []
    for path in sorted(generated.rglob("*.md")):
        if "__pycache__" in path.parts:
            continue
        text = _read(path)
        for raw in _LINK_RE.findall(text):
            target = raw.strip("<>").split("#", 1)[0]
            if not target:
                continue
            linked = (path.parent / target).resolve()
            if not linked.exists():
                missing.append((path, raw))
    assert not missing, f"Markdown の相対リンクが解決しない: {missing}"


# ── 8. src/ 内に相対 import が無い ───────────────────────────────────────────


def test_no_relative_imports_in_generated_src(generated: Path) -> None:
    """src/ 内の Python ファイルに `from .` / `from ..` で始まる相対 import が無いこと。

    「何を防いでいるか」: 相対 import があると「プロジェクトのフォルダを動かした
    ら import が壊れる」「pytest のルートを変えただけで動かなくなる」事故が
    起きる。テンプレート側は絶対にやらない（プロジェクト直下を sys.path に
    入れる運用に合わせ、絶対 import に統一する）。
    """
    offenders: list[tuple[Path, int, str]] = []
    for path in (generated / "src").rglob("*.py"):
        for i, line in enumerate(_read(path).splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("from .") or stripped.startswith("from .."):
                offenders.append((path, i, line.strip()))
    assert not offenders, f"src/ 内に相対 import: {offenders}"


# ── 8.5 雛形に src/sites/ を含めない（2026-08-20 Phase 5 の最小化） ────────────


def test_template_has_no_src_sites_directory(generated: Path) -> None:
    """雛形に ``src/sites/`` が含まれていないこと。

    「何を防いでいるか」: 2026-08-20 の Phase 5 で雛形最小化のため
    ``src/sites/example/`` 配下のサンプルを削除した。ブラウザ操作を使うか
    どうかはプロジェクトごとに違うので、雛形には入れず、必要になった時点で
    ``docs/browser.md`` を参照してプロジェクト側で追加する運用にした。
    ここに ``src/sites/`` が復活する回帰をここで防ぐ。

    ブラウザ操作の見本（書き方・最小形）はライブラリ側の
    ``comken/toolbox/browser/sites/sample/`` に残っているので、雛形側で持つ
    必要はない。
    """
    sites_dir = generated / "src" / "sites"
    assert not sites_dir.exists(), (
        f"雛形に {sites_dir.relative_to(generated)} が残っている"
        "（Phase 5 で雛形最小化のため削除済み。再度入れたい場合は docs/browser.md "
        "を参照し、ブラウザ操作を使うプロジェクト側で個別に追加すること）"
    )


# ── 9. .vscode/settings.json と 実行.bat が同じ comken の場所を指す ─────────────


def test_vscode_settings_and_bat_point_to_same_python_library(generated: Path) -> None:
    """`.vscode/settings.json` と 2 つの bat が同じ comken の場所を指すこと。

    「何を防いでいるか」: 片方だけ古い場所を指していると「実行は通るのに補完だけ
    効かない」状態になり、原因が見つけにくい。create() の注入ロジックをここで
    固定する（settings.json はスラッシュ区切り、bat はバックスラッシュ区切り — 置換漏れが
    片方だけ起きやすいので、両者を読み比べる検査を入れる）。
    """
    settings_text = _read(generated / ".vscode" / "settings.json")
    bat_text = _read(generated / "実行.bat", encoding="cp932")

    sm = re.search(r'"python\.analysis\.extraPaths":\s*\["([^"]+)"\]', settings_text)
    assert sm, "settings.json に python.analysis.extraPaths が見つからない"
    settings_path = sm.group(1).replace("/", "\\")

    bm = re.search(r'set\s+"PYTHON_LIBRARY=([^"]+)"', bat_text)
    assert bm, "実行.bat に PYTHON_LIBRARY の設定が見つからない"
    bat_path = bm.group(1)

    assert settings_path == bat_path, (
        f"settings.json は {settings_path!r} を指すのに、"
        f"実行.bat は {bat_path!r} を指している（片方の置換漏れ）"
    )


def test_python_library_is_importable(generated: Path) -> None:
    """`PYTHON_LIBRARY` が **import comken できる場所**（パッケージの親）を指すこと。

    「何を防いでいるか」: 2026-08-18 に、パッケージ自身
    （`...\\comken\\comken`）を指していた。PYTHONPATH へ入れても
    `import comken` は通らず、生成した bat は `%PYTHON_LIBRARY%\\comken\\__init__.py`
    の実在を確かめるので **必ず「comken が見つかりません」で止まる**状態だった。

    上の「両者が一致するか」だけでは、**両方が同じ誤った値**のとき通ってしまう。
    パスの中身まで見る必要がある。
    """
    bat_text = _read(generated / "実行.bat", encoding="cp932")
    bm = re.search(r'set\s+"PYTHON_LIBRARY=([^"]+)"', bat_text)
    assert bm, "実行.bat に PYTHON_LIBRARY の設定が見つからない"

    marker = Path(bm.group(1)) / "comken" / "__init__.py"
    assert marker.is_file(), (
        f"PYTHON_LIBRARY が import できない場所を指している: {bm.group(1)}\n"
        f"（{marker} が無い。comken パッケージ自身ではなく、その親を指すこと）"
    )


# ── 10. 雛形に \\\\server\\share のプレースホルダが残っている ─────────────────


_PLACEHOLDER_SERVER = "\\\\server\\share"


def test_template_still_has_placeholder_server_path() -> None:
    """雛形の bat / settings.json に `\\\\server\\share` のプレースホルダが
    そのまま残っていること（実在のサーバー名が混入していないこと）。

    「何を防いでいるか」: このリポジトリは公開前提なので、実在のサーバー名・組織名・
    社内ライブラリ名が入るとそのまま外へ出てしまう。create() はここへ実際の
    comken の場所を書き込む前提なので、プレースホルダが残っていること自体が
    「実名混入していない」ことの証拠になる。

    `認証情報の登録.bat` はサーバーの場所を**そもそも書かない**ので、この検査の
    対象にしない（代わりに下の test_credentials_bat_has_no_server_path で見る）。
    """
    suspects = [
        TEMPLATE_DIR / "実行.bat",
        TEMPLATE_DIR / ".vscode" / "settings.json",
    ]
    offenders: list[Path] = []
    for path in suspects:
        text = _read(path, encoding="cp932" if path.suffix.lower() == ".bat" else "utf-8")
        if _PLACEHOLDER_SERVER not in text:
            offenders.append(path)
    assert not offenders, (
        "雛形にプレースホルダ \\\\server\\share が無い"
        "（実在のサーバー名に置換されていないか確認すること）: "
        f"{offenders}"
    )


def test_credentials_bat_has_no_server_path() -> None:
    """`認証情報の登録.bat` に共有サーバーのパスが1つも出てこないこと。

    「何を防いでいるか」: この bat は `python -m comken init` が作ったプロジェクトに
    入るので、comken への PATH は既に通っている。だからサーバーの場所を書く必要が
    なく、書かないことで実名の混入経路そのものを閉じている。

    上の「プレースホルダが残っているか」という確かめ方はここでは使えない。
    プレースホルダが無いこと自体は正常なので、その検査だと**実在のサーバー名を
    書き込まれても通ってしまい**、公開リポジトリへの流出を止められない。
    UNC パス（`\\\\` 始まり）が出てこないことを直接見る。
    """
    path = TEMPLATE_DIR / "認証情報の登録.bat"
    text = _read(path, encoding="cp932")
    assert "\\\\" not in text, (
        f"{path.name} に共有サーバーのパスらしき記述がある"
        "（この bat は PATH が通っている前提なので、サーバーの場所を書かない）"
    )


# ── 12. カレントが別の場所でも、プロジェクト側の config.ini を読む ─────────────


def test_runs_from_another_working_directory(generated: Path, tmp_path: Path) -> None:
    r"""**カレントを別の場所にしたまま** `python <絶対パス>\main.py` で動くこと。

    「何を防いでいるか」: 社内 RPA 基盤は C:\ など別の場所をカレントにして
    絶対パスで main.py を呼ぶ。config.ini・state.ini・logs/ がカレント基準だと
    C:\config.ini を探し、C:\logs\ へ書いてしまう（2026-08-18 まで実際にそうだった）。

    1回目は config.ini が作られて止まり、2回目に run() まで進む。**どちらも
    生成先のフォルダに対して起きる**ことを見る。
    """
    elsewhere = tmp_path / "別のカレント"
    elsewhere.mkdir()
    env = {**os.environ, "PYTHONPATH": str(_ROOT), "PYTHONIOENCODING": "utf-8"}
    run = partial(
        subprocess.run,
        [sys.executable, str(generated / "main.py")],
        cwd=elsewhere,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )

    first = run()
    assert (generated / "config.ini").is_file(), (
        f"config.ini がプロジェクト側に作られていない:\n{first.stdout}\n{first.stderr}"
    )
    assert not (elsewhere / "config.ini").exists(), "カレント側に config.ini を作っている"

    second = run()
    assert second.returncode == 0, f"2回目が失敗した:\n{second.stdout}\n{second.stderr}"
    assert (generated / "logs").is_dir(), "logs がプロジェクト側に作られていない"
    assert not (elsewhere / "logs").exists(), "カレント側に logs を作っている"
