"""comken/core/doctor/cli.py — ``python -m comken doctor`` の本体と、
ライブラリ関数 ``comken.doctor()``。

`comken/__main__.py` から ``main(argv)`` で呼ばれるほか、
``from comken import doctor`` でライブラリからも呼べる。

**toolbox / services への依存はここに集約する。** `runner.py` は
検査ロジックを純粋関数として持つので、層の制約（core が toolbox /
services を import しない）に違反しない。cli は CLI 入口なので
依存してもよい。
"""
# このファイルは CLI 入口。`print` で結果を出すのが仕事なので
# ファイル全体で T201（print 検出）を許可する。
# ruff: noqa: T201

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from comken.core.timer import measure

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from comken.core.doctor.runner import DoctorResult


def _resolve_salesforce_deps() -> tuple:
    """Salesforce 検査に必要な部品を遅延 import で取る。

    戻り値は ``(list_names, names, sandbox_cls)``:
    - ``list_names``: 資格情報キー名一覧を返す関数（monkeypatch 用に保持）
    - ``names``: 上記を呼んだ結果（空リストなら Salesforce は import しない）
    - ``sandbox_cls``: Salesforce 組織クラス。**資格情報が空のときは import しない**
      ので ``None`` になる（BO 環境で ``requests`` が無いときに
      ``salesforce.client`` を読み込まないため）
    """
    # モジュールを import してから属性経由で関数を取る。
    # こうすると `comken.toolbox.credentials.list_names` を
    # monkeypatch したときに、それが反映される。
    from comken.toolbox import credentials as credentials_module  # noqa: PLC0415

    list_names_fn = credentials_module.list_names

    # 認証情報が無いならここで Salesforce を import しない
    # （BO 環境で `requests` が無いときに client.py まで読み込まれないよう）
    try:
        names = list_names_fn()
    except Exception:
        names = []

    sandbox_cls: type | None = None
    if names:
        try:
            from comken.toolbox.salesforce.sites import Sandbox

            sandbox_cls = Sandbox
        except ImportError:
            sandbox_cls = None

    return list_names_fn, names, sandbox_cls


def _resolve_share_paths() -> tuple[Path, Path]:
    """共有サーバー上の管理表・履歴のパスを取る。

    `comken.services.salesforce_downloader._paths` は services 層にある。
    cli.py は CLI 入口なので services に依存しても問題ない（層ルール外）。
    """
    from comken.services.salesforce_downloader._paths import HISTORY_PATH, MASTER_PATH

    return Path(MASTER_PATH), Path(HISTORY_PATH)


def doctor() -> list["DoctorResult"]:
    """環境・依存・設定・接続をまとめて検査する（ライブラリ関数）。

    戻り値は `DoctorResult` のリスト。CLI は ``python -m comken doctor``、
    ライブラリ利用者は ``from comken import doctor`` で呼べる。

    検査は独立して動く（1 個失敗しても残りは続ける）。Salesforce は
    資格情報が無ければ SKIP し、`requests` を import しない経路を選ぶ
    （BO 環境対応、テスト `test_does_not_load_requests_for_skipped_salesforce`
    で守られる）。
    """
    # 検査関数本体は `runner.py` に置いてある（純粋関数）。
    # ここでは「toolbox / services に触る必要がある引数」を組み立てて渡す。
    from comken.core.doctor.runner import (
        check_comken_path,
        check_comken_version,
        check_dependency,
        check_history_path,
        check_master_path,
        check_pywin32,
        check_python_version,
        check_rpa_placeholder,
        check_run_section,
        check_salesforce,
        check_sandbox_placeholder,
        check_service_placeholder,
    )

    results: list[DoctorResult] = []

    # comken 自体の情報
    results.append(check_comken_version())
    results.append(check_python_version())
    results.append(check_comken_path())

    # 依存モジュール
    results.append(check_dependency("openpyxl", "openpyxl"))
    results.append(check_dependency("selenium", "selenium"))
    results.append(check_pywin32())
    results.append(check_dependency("requests", "requests"))

    # 設定の正しさ
    results.append(check_run_section())
    results.append(check_rpa_placeholder())
    results.append(check_sandbox_placeholder())
    results.append(check_service_placeholder())

    # 共有サーバー
    try:
        master, history = _resolve_share_paths()
    except ImportError:
        # services モジュールが sparse-checkout で除外されている環境
        results.append(DoctorResult_ok_skip("share.master_path", "services モジュールなし"))
        results.append(DoctorResult_ok_skip("share.history_path", "services モジュールなし"))
    else:
        results.append(check_master_path(master))
        results.append(check_history_path(history))

    # Salesforce（資格情報なしは SKIP。`doctor()` 全体が落ちないように try/except）
    _list_names_fn, names, sandbox_cls = _resolve_salesforce_deps()
    try:
        results.append(check_salesforce(names, sandbox_cls))
    except Exception as e:
        logger.warning("Salesforce 検査で予期しない例外: %s", e)
        from comken.core.doctor.runner import DoctorResult

        results.append(
            DoctorResult(
                "salesforce.connectivity",
                "skip",
                f"実行できません: {type(e).__name__}",
            )
        )

    return results


# helper: services が無い環境向けの簡易 SKIP 結果
from comken.core.doctor.runner import DoctorResult  # noqa: E402  # 関数内利用


def DoctorResult_ok_skip(name: str, message: str) -> "DoctorResult":
    """SKIP の DoctorResult を作る小さなヘルパー（`doctor()` 内専用）。"""
    return DoctorResult(name, "skip", message)


# ── CLI 本体 ─────────────────────────────────────────────────────────────────


@measure
def main(argv: list[str] | None = None) -> int:
    """コマンドを実行して終了コードを返す（0=全 OK / 1=NG あり）。"""
    args = _build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    from comken.core.doctor.runner import summarize

    results = doctor()
    ok, ng, skip = summarize(results)

    if args.json:
        _print_json(results, ok, ng, skip)
    else:
        _print_human(results, ok, ng, skip)

    return 1 if ng > 0 else 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m comken doctor",
        description="環境の切り分け診断 (依存・設定・接続)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="機械可読な JSON で出力する（CI 等から利用）",
    )
    return parser


# 表示順を固定する。CLI の出力はセクションごとにグルーピングして見せる
SECTIONS: list[tuple[str, list[str]]] = [
    ("comken", ["comken.version", "python.version", "comken.path"]),
    (
        "依存モジュール",
        ["deps.openpyxl", "deps.selenium", "deps.pywin32", "deps.requests"],
    ),
    (
        "設定の正しさ",
        [
            "config.run_section",
            "config.placeholder.rpa",
            "config.placeholder.sandbox",
            "config.placeholder.service",
        ],
    ),
    ("共有サーバー", ["share.master_path", "share.history_path"]),
    ("Salesforce", ["salesforce.connectivity"]),
]


def _print_human(results: list[DoctorResult], ok: int, ng: int, skip: int) -> None:
    """人が読む形式。セクション分けして表形式で出す。"""
    print("=== comken doctor ===")
    print()

    sections = {r.name: r for r in results}
    for title, keys in SECTIONS:
        rows = [(name, sections[name]) for name in keys if name in sections]
        if not rows:
            continue
        print(f"[{title}]")
        max_name = max(len(name) for name, _ in rows)
        for name, r in rows:
            print(f"  {_pad(name, max_name)}: {_status_label(r)}")
        print()

    print("=== 結果 ===")
    print(f"OK: {ok} / NG: {ng} / SKIP: {skip}")
    print()
    print(f"終了コード: {1 if ng > 0 else 0}")


def _pad(text: str, width: int) -> str:
    """ASCII を想定した簡易パディング（検査名は ASCII のみ）。"""
    return text + " " * max(0, width - len(text))


def _status_label(r: DoctorResult) -> str:
    """status を見やすい文字列に変換する。"""
    if r.status == "ok":
        return r.message if r.message else "OK"
    suffix = f": {r.message}" if r.message else ""
    if r.status == "ng":
        return f"NG{suffix}"
    if r.status == "skip":
        return f"SKIP{suffix}"
    return r.status


def _print_json(results: list[DoctorResult], ok: int, ng: int, skip: int) -> None:
    """機械可読な JSON 形式で出力する。"""
    output = {
        "results": [{"name": r.name, "status": r.status, "message": r.message} for r in results],
        "summary": {"ok": ok, "ng": ng, "skip": skip},
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
