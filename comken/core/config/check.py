"""comken/core/config/check.py — config.ini の診断

``python -m comken config --check <path>`` から呼ばれる本体。
「``[FILES]`` が config.ini にあるのに ``ConfigSectionNotFoundError`` が出る」のような
見た目に分からない事故を、現場で 1 コマンドで特定できるようにするためのもの。
**コード側で ``config.SECTION.KEY`` と書かれている項目を AST で集めて config.ini と
突き合わせる** ところまで 1 回のコマンドで済ませる。

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
| 似たセクション名・キー名が **2 つ並んでいる** | 片方は古い設定で意図せず残っている／タイポ |
| コードに ``config.X.Y`` を足したが ini に書き忘れた | ``ConfigKeyNotFoundError`` で止まる |
| ini からセクションを消した | 遠いところで ``ConfigSectionNotFoundError`` |
| ``require()`` のリストが古い | 足りない項目でも起動時に止まらない |

**値は一切出力しない。** config.ini には業務情報（顧客名・パス・URL）が含まれるため、
このモジュールが出すのは「セクション名」「キー名」「行番号」「元の行」だけ。
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from comken.core.config.scan import (
    ProjectScan,
    UsageHit,
    scan_project,
)
from comken.exceptions.config import damerau_levenshtein_distance

# 行頭の空白として扱う文字。半角スペース・タブに加えて全角スペースも対象。
# 全角スペースは非エンジニアが誤って入れてしまいがちで、気づかれにくい事故になる。
_LEADING_WHITESPACE = " \t　"

# INI のコメント開始文字。configparser.RawConfigParser と一致させる。
_COMMENT_CHARS = (";", "#")

# マッピング系セクションの判定（実行時の Config と同じ規約）。
# ここで import せず判定式を書くのは、循環 import を避けるため
# （config/__init__.py がこのモジュールを import できるようにする）。
_MAPPING_SUFFIX = "MAPPING"

# 似た名前が 2 つ並んでいるときの警告条件。編集距離が 1 以下なら、
# 1 文字違いや隣り合う 2 文字の入れ替わりを拾う。
_SIMILAR_NAME_MAX_DISTANCE = 1


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


# ── コード走査の結果の型 ────────────────────────────────────────────────
# これらの dataclass は「コード vs config.ini」の突き合わせだけを扱う。
# **値は載せない**（config.ini の値・コードの値を両方とも絶対に漏らさない）。
# 表示側で整形しやすいように、種別ごとのフラグではなく独立した dataclass にする。


@dataclass(frozen=True)
class UsageOk:
    """``config.SECTION.KEY`` が config.ini にも存在する。"""

    usage: UsageHit


@dataclass(frozen=True)
class UsageMissingKey:
    """``config.SECTION.KEY`` の ``KEY`` が config.ini に無い。"""

    usage: UsageHit


@dataclass(frozen=True)
class UsageMissingSection:
    """``config.SECTION.KEY`` の ``SECTION`` が config.ini に無い。"""

    usage: UsageHit


# ── ``require()`` との食い違い ────────────────────────────────────────────
# 両方あると二重管理になるので、AST で両方を拾って差分を出す。
# 警告に留め、終了コードは上げない（``require()`` の本来の目的は
# 「動く前にまとめて出す」ことで、静的検査とは別物だから）。


@dataclass(frozen=True)
class RequireMismatch:
    """``require()`` とコードの使用箇所が食い違っている 1 件。

    Attributes:
        name: ``"SECTION.KEY"``（大文字に揃えてある）。
        direction: ``"missing_from_require"`` は **使われているのに require に無い**、
            ``"unused_in_require"`` は **require に書かれているのに使われていない**。
    """

    name: str
    direction: str


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
        scan: プロジェクトのソース走査結果。``None`` のときは走査しなかった
            （= 1 ファイルも無いプロジェクトでは作らない）。
        usage_results: ``config.SECTION.KEY`` の各使用箇所に対する突き合わせ結果。
            ``scan`` が無い、または ``scan.usages`` が空のときは空リスト。
        require_mismatches: ``require()`` と使用箇所の食い違い。
            ``scan`` が無い、または ``scan.usages`` も ``scan.requires`` も空のときは空リスト。
    """

    path: Path
    bom: bool
    problems: list[CheckProblem] = field(default_factory=list)
    sections: dict[str, list[str]] = field(default_factory=dict)
    total_lines: int = 0
    scan: ProjectScan | None = None
    usage_results: list[UsageOk | UsageMissingKey | UsageMissingSection] = field(
        default_factory=list
    )
    require_mismatches: list[RequireMismatch] = field(default_factory=list)


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

    sections, parser_problems = _parse_sections(path, text)
    problems.extend(parser_problems)
    _add_similar_name_problems(problems, sections)

    # ── プロジェクト側のコードを AST 走査する ─────────────────────────────
    # config.ini の隣にある main.py / src/**/*.py を読み取って、
    # ``config.SECTION.KEY`` と ``config.require(...)`` を集める。
    # **コードを実行しない（副作用なし）**。1 ファイルも無いプロジェクトでは
    # 走査結果を None のままにして、表示側で節を出さない。
    scan = scan_project(path.parent)
    if scan.usages or scan.requires:
        usage_results, require_mismatches = _match_scan(scan, sections)
    else:
        usage_results = []
        require_mismatches = []

    return CheckResult(
        path=path,
        bom=bom,
        problems=problems,
        sections=sections,
        total_lines=len(lines),
        scan=scan,
        usage_results=usage_results,
        require_mismatches=require_mismatches,
    )


def _parse_sections(path: Path, text: str) -> tuple[dict[str, list[str]], list[CheckProblem]]:
    """configparser でテキストを解析し、セクション一覧と全体エラーを返す。

    configparser 全体での失敗（``DuplicateOptionError`` 等）は
    ``line_no=0`` の 1 件として積む。**値は返さない**（キー名だけ集める）。

    Args:
        path: エラーメッセージ用に持つ config.ini のパス。
        text: 既に BOM 落とし済みのテキスト。

    Returns:
        ``(sections, problems)``。
    """
    sections: dict[str, list[str]] = {}
    problems: list[CheckProblem] = []
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
    return sections, problems


def _add_similar_name_problems(
    problems: list[CheckProblem], sections: dict[str, list[str]]
) -> None:
    """セクション名・キー名で似たペアを指摘として ``problems`` に追加する。

    ``[FILES]`` と ``[FILE]`` のように 1 文字違いで両方あると、片方は古い設定で
    意図せず残っている可能性が高い。ただし ``INPUT_FOLDER`` と ``OUTPUT_FOLDER``
    のような正しいペアは編集距離 3 のため、誤検知にはならない。
    マッピングセクションのキー（列名）は業務情報になりうるため、
    列挙するとチェック自体が情報漏洩になる。スキップする。
    """
    # セクション同士の類似
    for a, b, distance in _similar_pairs(list(sections)):
        problems.append(
            CheckProblem(
                line_no=0,
                snippet="",
                message=(
                    f"似た名前のセクションが 2 つあります。"
                    f"[{a}] と [{b}]（編集距離 {distance}）。"
                    "片方は古い設定で意図せず残っている／タイポの可能性が高いです。"
                    "意図して両方があるなら、この指摘は無視して構いません"
                ),
            )
        )
    # セクション内のキー同士の類似
    for stripped_section, keys in sections.items():
        if stripped_section.endswith(_MAPPING_SUFFIX):
            continue
        for a, b, distance in _similar_pairs(keys):
            problems.append(
                CheckProblem(
                    line_no=0,
                    snippet="",
                    message=(
                        f"[{stripped_section}] セクション内に似た名前のキーが 2 つあります。"
                        f"{a} と {b}（編集距離 {distance}）。"
                        "片方は古い設定で意図せず残っている／タイポの可能性が高いです。"
                        "意図して両方があるなら、この指摘は無視して構いません"
                    ),
                )
            )


def _similar_pairs(names: list[str]) -> list[tuple[str, str, int]]:
    """``names`` の中で、互いの編集距離が 1 以下のペアを返す。

    返り値は ``(a, b, distance)`` のリスト。``a < b`` の辞書順に整列して、
    ``(a, b)`` と ``(b, a)`` の両方は出さない（同ペアは最初の組合せ 1 回だけ）。
    マッピングセクションは列名が業務情報になりうるため、判定材料には
    使わない（呼び出し側で sections から除外する想定）。
    """
    found: list[tuple[str, str, int]] = []
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            distance = damerau_levenshtein_distance(a, b)
            if distance <= _SIMILAR_NAME_MAX_DISTANCE:
                found.append((a, b, distance))
    return found


def _match_scan(
    scan: ProjectScan,
    sections: dict[str, list[str]],
) -> tuple[list[UsageOk | UsageMissingKey | UsageMissingSection], list[RequireMismatch]]:
    """``scan`` と config.ini から読み取った ``sections`` を突き合わせる。

    大文字小文字は実行時の ``Config`` と同じ扱い（大文字に揃えて照合）にする。
    config.ini のセクション名・キー名は大文字強制なので、コード側が小文字で
    書かれていても一致する。

    Args:
        scan: AST 走査結果（``usages`` / ``requires`` を含む）。
        sections: config.ini から読み取った **空白落とし済み**セクション名 → キー一覧。

    Returns:
        ``(usage_results, require_mismatches)``。
    """
    # config.ini のキーは configparser 側で小文字に潰さない設定（optionxform=str）に
    # してあるので、書かれたとおりのキー名が来る。空文字キーは除外する。
    section_keys: dict[str, set[str]] = {}
    for stripped, keys in sections.items():
        section_keys[stripped.upper()] = {k.upper() for k in keys if k}

    usage_results: list[UsageOk | UsageMissingKey | UsageMissingSection] = []
    for usage in scan.usages:
        section = usage.section.upper()
        key = usage.key.upper()
        if section not in section_keys:
            usage_results.append(UsageMissingSection(usage))
        elif key not in section_keys[section]:
            usage_results.append(UsageMissingKey(usage))
        else:
            usage_results.append(UsageOk(usage))

    used = scan.used_names
    required = scan.required_names

    # 「require に無いのに使われている」は require の本来の目的（動く前に全部出す）
    # から漏れているので警告する。「require に書かれているのに使われていない」は
    # 将来使う前提で先に書くこともあるので警告に留める（終了コードは変えない）。
    mismatches: list[RequireMismatch] = []
    for name in sorted(used - required):
        mismatches.append(RequireMismatch(name, "missing_from_require"))
    for name in sorted(required - used):
        mismatches.append(RequireMismatch(name, "unused_in_require"))

    return usage_results, mismatches


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

    _print_usage_section(result)
    _print_require_section(result)

    # 終了コード:
    #   - 構造上の問題（problems）が 1 件でも → 1
    #   - コードで使っている項目が config.ini に無い → 1
    #     （動かすと ``ConfigSectionNotFoundError`` / ``ConfigKeyNotFoundError`` で
    #     落ちるので、CI でも止めたい）
    #   - ``require()`` との食い違いだけ → 0 のまま（警告レベル）。
    #     「将来使う予定で先に書く」運用もあるため、終了コードは上げない。
    has_usage_missing = any(
        isinstance(r, (UsageMissingKey, UsageMissingSection)) for r in result.usage_results
    )
    exit_code = 1 if (result.problems or has_usage_missing) else 0
    return exit_code


def _print_usage_section(result: CheckResult) -> None:
    """「コードで使っている設定」節を出す。

    走査結果が空（``scan`` が None または ``usages`` が空）のときは節ごと出さない。
    config.ini 単独で使うプロジェクトや、``src/`` が無いプロジェクトでも
    ``--check`` が動くようにするための配慮。

    Args:
        result: ``check_config()`` の戻り値。
    """
    if result.scan is None or not result.scan.usages:
        return
    print()
    print("--- コードで使っている設定 ---")
    for r in result.usage_results:
        usage = r.usage
        # Windows でもパスの区切りを / に揃える（表示の安定のため）。
        location = f"{usage.path.as_posix()}:{usage.line}"
        name = f"{usage.section.upper()}.{usage.key.upper()}"
        if isinstance(r, UsageOk):
            print(f"  {location:<22}{name:<24}OK")
        elif isinstance(r, UsageMissingSection):
            print(f"  {location:<22}{name:<24}★ [{usage.section.upper()}] セクションがありません")
        else:
            print(f"  {location:<22}{name:<24}★ config.ini にありません")


def _print_require_section(result: CheckResult) -> None:
    """「require() との食い違い」節を出す。

    走査が無いとき、または ``usages`` も ``requires`` も空のときは出さない。

    Args:
        result: ``check_config()`` の戻り値。
    """
    if result.scan is None or (not result.scan.usages and not result.scan.requires):
        return
    print()
    print("--- require() との食い違い ---")
    if not result.require_mismatches:
        print("  食い違いはありません")
        return
    for m in result.require_mismatches:
        if m.direction == "missing_from_require":
            print(f"  {m.name:<28}使われているのに require() に書かれていません")
        else:
            print(f"  {m.name:<28}require() に書かれていますが未使用です")
