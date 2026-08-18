"""comken/core/config/check.py — config.ini の診断

``python -m comken config --check <path>`` から呼ばれる本体。
「``[FILES]`` が config.ini にあるのに ``ConfigSectionNotFoundError`` が出る」のような
見た目に分からない事故を、現場で 1 コマンドで特定できるようにするためのもの。

防いでいる事故:

| 事故 | 何が起きるか |
|---|---|
| ``  [FILES]`` のように **行頭に空白** がある | 前の値に含まれてセクションが消える |
| ``[FILES ]`` のように **セクション名に空白** が混じる | 別セクション扱いになり遠い場所でエラー |
| 値が **複数行に続いている** のに意図と違っている | 次のキーと思った行が前の値の継続に |
| **BOM** 付きで保存されている | エディタによりセクションが見えなくなる |
| ``; KEY = 値`` で **コメントアウト** されたまま | 設定を書いたつもりが無効 |
| 同じセクション内に **同じキーが 2 回** | configparser が弾く |
| **セクションが 1 つも認識されない** | configparser が黙って空になる |

**値は一切出力しない。** config.ini には業務情報（顧客名・パス・URL）が含まれるため、
このモジュールが出すのは「セクション名」「キー名」「行番号」「元の行」だけ。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

# 行頭の空白として扱う文字。半角スペース・タブに加えて全角スペースも対象。
# 全角スペースは非エンジニアが誤って入れてしまいがちで、気づかれにくい事故になる。
_LEADING_WHITESPACE = " \t　"

# INI のコメント開始文字。configparser.RawConfigParser と一致させる。
_COMMENT_CHARS = (";", "#")

# マッピング系セクションの判定（実行時の Config と同じ規約）。
# ここで import せず判定式を書くのは、循環 import を避けるため
# （config/__init__.py がこのモジュールを import できるようにする）。
_MAPPING_SUFFIX = "MAPPING"


@dataclass(frozen=True)
class CheckProblem:
    """config.ini で見つかった 1 件の指摘。

    Attributes:
        line_no: 1 始まりの行番号。ファイル全体に関わるエラー（重複キー等）は 0。
        snippet: その行の原文。**値は出さない**前提だが、行全体を出した方が
            ユーザーが自分の config.ini と見比べやすい。
        message: 何が問題か・どう直すかの短い説明。
    """

    line_no: int
    snippet: str
    message: str


@dataclass(frozen=True)
class CheckResult:
    """診断結果のサマリ。

    Attributes:
        path: 読んだ config.ini の絶対パス。
        bom: BOM 付き UTF-8 だったか。
        problems: 見つかった指摘のリスト。
        sections: 認識できたセクションの **空白落とし済みセクション名 → キー名一覧**。
            値そのものは含めない（業務情報を出さないため）。
        total_lines: 元ファイルの行数。
    """

    path: Path
    bom: bool
    problems: list[CheckProblem] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)
    total_lines: int = 0


def check_config(path: str | Path) -> CheckResult:
    """config.ini を読み、構造上の問題が無いかを診断する。

    **値は返さない。** 出力には名前（セクション名・キー名）と構造（キー一覧）
    だけを載せる。configparser 全体での失敗（``DuplicateOptionError`` 等）が
    出ても、行単位の解析は続けて 1 回の呼び出しで全ての指摘を返す。

    Args:
        path: 診断対象の config.ini のパス。

    Returns:
        診断結果。``problems`` が空なら「気になるところはない」。
    """
    path = Path(path).resolve()
    raw_bytes = path.read_bytes()
    bom = raw_bytes.startswith(b"\xef\xbb\xbf")
    # utf-8-sig は BOM を吸収しつつ BOM なし UTF-8 もそのまま読める
    text = raw_bytes.decode("utf-8-sig")
    lines = text.splitlines()

    problems: list[CheckProblem] = []
    for line_no, line in enumerate(lines, start=1):
        _check_line(line_no, line, problems)

    # configparser にも食わせて、読める範囲を確認する。
    # 重複キー等の全体エラーはここで拾う（line_no=0 で1件として積む）。
    sections: dict[str, list[str]] = {}
    try:
        cfg = configparser.RawConfigParser()
        cfg.optionxform = str  # type: ignore[method-assign]
        cfg.read_string(text, source=str(path))
        for original in cfg.sections():
            stripped = original.strip()
            if not stripped:
                # `[]` や `[   ]` のように空白しか無いセクション名は実行時も無視されるので
                # ここでも出さない（診断で出すと「セクションが消えた！」と騒ぎになるため）
                continue
            # 値ではなくキー名だけ集める。値そのものは出さない。
            sections[stripped] = list(cfg.options(original))
    except configparser.DuplicateOptionError as e:
        problems.append(
            CheckProblem(
                line_no=0,
                snippet="",
                message=(
                    f"同じセクション内で同じキーが 2 回以上書かれています（キー: {e.option}）。"
                    "configparser は最初の値だけを採用するため、"
                    "意図した設定と違うものが読まれている可能性があります"
                ),
            )
        )
    except configparser.Error as e:
        # その他の configparser エラー（セクションの [] が閉じられていない等）も
        # 1 件として積んで、行単位の解析と一緒に画面に出す
        problems.append(
            CheckProblem(
                line_no=0,
                snippet="",
                message=f"configparser が読めませんでした: {e}",
            )
        )

    return CheckResult(
        path=path,
        bom=bom,
        problems=problems,
        sections=sections,
        total_lines=len(lines),
    )


def _check_line(line_no: int, line: str, problems: list[CheckProblem]) -> None:
    """1 行分の検出ロジック。見つかった指摘は problems に追加する。

    1 行から複数の指摘が出る場合は先に検出したものを優先して ``return`` し、
    同じ行で「コメントアウト」と「行頭空白」を二重で指摘することがないようにする。
    """
    stripped_left = line.lstrip()
    if _check_commented_out_setting(line_no, line, stripped_left, problems):
        return
    if _check_leading_whitespace(line_no, line, stripped_left, problems):
        return
    _check_section_inner_whitespace(line_no, line, problems)


def _check_commented_out_setting(
    line_no: int,
    line: str,
    stripped_left: str,
    problems: list[CheckProblem],
) -> bool:
    """``; KEY = 値`` / ``# KEY = 値`` を検出する。指摘を見つけたら True を返す。

    純粋なコメント（KEY がない行）は対象外。**値は出さない** ため snippet は空。
    """
    if not stripped_left or stripped_left[0] not in _COMMENT_CHARS:
        return False
    body = stripped_left[1:].lstrip()
    if "=" not in body:
        return False
    key = body.split("=", 1)[0].strip()
    if not key:
        return False
    problems.append(
        CheckProblem(
            line_no=line_no,
            snippet="",
            message=(
                f"コメントアウトされた設定行です（キー: {key}）。"
                "先頭の ; か # を外すと有効になります"
            ),
        )
    )
    return True


def _count_leading_whitespace(line: str) -> int:
    """行頭の空白文字数（全角スペース含む）を返す。"""
    count = 0
    for ch in line:
        if ch in _LEADING_WHITESPACE:
            count += 1
        else:
            break
    return count


def _check_leading_whitespace(
    line_no: int,
    line: str,
    stripped_left: str,
    problems: list[CheckProblem],
) -> bool:
    """行頭に空白がある ``[SECTION]`` / ``KEY = 値`` を検出する。

    **いちばん見つけにくい事故**:  行頭に空白があると configparser はそこを
    セクション / 独立したキーと認識せず、前の値や前のセクションの末尾に含めてしまう。
    """
    leading_count = _count_leading_whitespace(line)
    if leading_count == 0 or not stripped_left:
        return False
    leading_text = line[:leading_count]
    if stripped_left.startswith("["):
        # セクション行は値を持たないので、行全体（= セクションヘッダ）を snippet として見せる
        problems.append(
            CheckProblem(
                line_no=line_no,
                snippet=line,
                message=(
                    f"行頭に空白が {leading_count} 文字あります。"
                    f"この書き方だとセクションとして認識されず、"
                    f"直前の値（または前のセクション）に含まれます。"
                    f"行頭の空白（{leading_text!r}）を消してください"
                ),
            )
        )
        return True
    # インデントされた ``KEY = 値``。configparser は前の値の継続行とみなす
    if "=" in stripped_left and not stripped_left.startswith("="):
        key = stripped_left.split("=", 1)[0].strip()
        if key:
            problems.append(
                CheckProblem(
                    line_no=line_no,
                    snippet="",
                    message=(
                        f"行頭に空白が {leading_count} 文字あります。"
                        f"この書き方だと独立した設定として読まれず、"
                        f"直前の値の続きとして扱われます（キー: {key}）。"
                        f"行頭の空白（{leading_text!r}）を消すと別キーとして読まれます"
                    ),
                )
            )
            return True
    return False


def _check_section_inner_whitespace(line_no: int, line: str, problems: list[CheckProblem]) -> None:
    """``[FILES ]`` のようにセクション名に空白（全角含む）が混じているか。

    セクション行は値を持たないので、行全体を出してよい。
    """
    if not line.startswith("["):
        return
    end = line.find("]")
    if end <= 1:
        return
    inner = line[1:end]
    if not any(c in " \t　" for c in inner):
        return
    problems.append(
        CheckProblem(
            line_no=line_no,
            snippet=line,
            message=(
                f"セクション名に空白が混じっています: {inner!r}。"
                "configparser は空白を落とさず別名として扱うため、"
                "空白を消すと config.ini の見た目と一致します"
            ),
        )
    )


def run_check(path: str | Path) -> int:
    """診断を実行して結果を画面に出す。

    Args:
        path: 診断対象の config.ini のパス。

    Returns:
        問題がなければ 0、何か見つかったら 1。
        「気になるところ」があっても読み込み自体は続け、見つけた指摘を全て出す。
    """
    result = check_config(path)

    print(f"読んだファイル: {result.path}")
    print("文字コード    : " + ("UTF-8（BOM 付き）" if result.bom else "UTF-8（BOM なし）"))

    print()
    if not result.problems:
        print("--- 気になるところ ---")
        print("  気になるところはありません")
    else:
        print("--- 気になるところ ---")
        for p in result.problems:
            if p.line_no == 0:
                # ファイル全体に関わるエラーは行番号を出さない
                print(f"  {p.message}")
                continue
            # snippet がセットされているときは原文も添える（値を含む行ではセットされない）
            if p.snippet:
                print(f"  {p.line_no}行目: {p.message}")
                print(f"          → {p.snippet!r}")
            else:
                print(f"  {p.line_no}行目: {p.message}")

    print()
    print("--- 認識したセクション ---")
    if not result.sections:
        print("  （セクションは 1 つも認識されませんでした）")
    else:
        for stripped, keys in result.sections.items():
            if stripped.endswith(_MAPPING_SUFFIX):
                # 列の対応表はキー名（列名）が業務情報になりうるため件数だけ出す
                print(f"  [{stripped}]  （列の対応表。{len(keys)}件）")
            else:
                keys_text = ", ".join(keys) if keys else "（キーなし）"
                print(f"  [{stripped}]  キー: {keys_text}")

    return 1 if result.problems else 0
