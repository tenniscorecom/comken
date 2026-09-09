"""管理表に登録された全レポートの ``reportFilters`` を CSV にダンプする。

**このファイルは開発用**（リポジトリ直下の ``tools/`` にあり、配布されない）。
``comken`` パッケージの ``__all__`` には載せず、恒久的な公開 API にもしない。

「本日のデータか／過去確定分か」をレポート毎に判定する自動化の設計を
検討するため、``ReportAPI.describe()`` が返す ``reportMetadata.reportFilters``
を人が読める形で一覧化する。目視確認用の使い捨てスクリプト。

使い方:
    python tools/dump_report_filters.py
    python tools/dump_report_filters.py --master reports.xlsx --output filters.csv

**300 件近いレポートを処理するため、組織ごとに接続を使い回す。** 1 件ごとに
``with site() as sf:`` を呼ぶと、認証・接続のたびに数秒を失うため、組織で
グルーピングして 1 組織 1 接続にまとめる。
"""

import argparse
import csv
import logging
import sys
from pathlib import Path
from typing import Any, TypedDict

# スクリプトとして実行すると sys.path の先頭は tools/ になるため、
# comken を import する前にリポジトリルートを探索対象へ加える。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from comken.constants import Encoding  # noqa: E402
from comken.services.salesforce_downloader.master import ReportEntry, load_master  # noqa: E402
from comken.toolbox.salesforce.sites import site_for  # noqa: E402

logger = logging.getLogger(__name__)

# 出力 CSV の見出し。すべて日本語で、利用者が Excel で開いてそのまま読める形にする
CSV_HEADERS = ("管理番号", "レポートID", "URL", "フィルタ列", "演算子", "値")


class _FilterRow(TypedDict):
    """CSV 1 行分。``csv.DictWriter.writerows()`` の ``rowdicts`` 引数は
    ``Mapping[Literal[...], Any]`` を要求するため、``TypedDict`` でキーを固定する。"""

    管理番号: str
    レポートID: str
    URL: str
    フィルタ列: str
    演算子: str
    値: str


# 出力ファイル名は、Excel で開いて文字化けしないよう BOM 付き UTF-8 にする
DEFAULT_OUTPUT_PATH = Path("report_filters_dump.csv")
# ``describe()`` が失敗したとき、``値`` 列にこのプレフィックスを付けて失敗事実を残す
FAILED_PREFIX = "取得失敗: "

# 1 組織あたり何件処理したかをログに出す区切り。 50 件ごとに「ここまで進んだ」が
# 分かれば、長時間の処理でも進捗の安心感が出るため
PROGRESS_LOG_INTERVAL = 50


def _stringify_filter_field(value: object) -> str:
    """フィルタ要素の 1 フィールドを CSV のセル用に文字列化する。

    Salesforce の ``reportFilters`` は ``value`` にリスト・辞書を返すことがある
    （例: ``["a", "b"]`` の ``in`` 演算子）。空のときは空文字を返し、リスト・
    辞書など複雑な型は ``str()`` で文字列化する。``None`` は空文字として扱い、
    「値が無い」と「未取得」を同じ空文字で表現する（CSV 上は区別が付かないため）。
    """
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return str(value)


def _filters_to_rows(
    entry: ReportEntry,
    report_filters: list[object],
) -> list[_FilterRow]:
    """1 レポート分の ``reportFilters`` を CSV 1 行ずつに変換する。

    フィルタが複数あれば複数行、無ければ 1 行（フィルタ列を空にして出す）。
    各フィルタが辞書型でないもの（壊れたレスポンス）は空のフィルタとして扱う。
    """
    if not report_filters:
        return [
            _FilterRow(
                管理番号=entry.key,
                レポートID=entry.report_id,
                URL=entry.url,
                フィルタ列="",
                演算子="",
                値="",
            )
        ]
    rows: list[_FilterRow] = []
    for report_filter in report_filters:
        if not isinstance(report_filter, dict):
            # 想定外の型（壊れたレスポンス等）はフィルタ無しと同じ扱いに倒し、
            # 1 行だけ出す
            field = operator = value = ""
        else:
            # Salesforce Reports and Dashboards REST API の reportFilters は
            # 列を "column" キーで持つ（公式ドキュメントの例:
            # {"column": "OPEN", "operator": "equals", "value": "True"}）。
            # "field" ではない点に注意（過去に取り違えていた実績あり）。
            field = _stringify_filter_field(report_filter.get("column"))
            operator = _stringify_filter_field(report_filter.get("operator"))
            value = _stringify_filter_field(report_filter.get("value"))
        rows.append(
            _FilterRow(
                管理番号=entry.key,
                レポートID=entry.report_id,
                URL=entry.url,
                フィルタ列=field,
                演算子=operator,
                値=value,
            )
        )
    return rows


def _describe_report_filters(salesforce_client: Any, entry: ReportEntry) -> list[object]:
    """1 レポートの ``reportFilters`` を取り出して返す。

    ``describe()`` 自体はこのスクリプトでは扱わないが、失敗時のメッセージを
    共通化するために関数化している。``salesforce_client`` はテストで差し替えやすい
    よう ``Any`` として受け取る（``SalesforceBase`` 互換）。
    """
    metadata = salesforce_client.report.describe(entry.report_id)
    if not isinstance(metadata, dict):
        return []
    report_metadata = metadata.get("reportMetadata", {})
    if not isinstance(report_metadata, dict):
        return []
    report_filters = report_metadata.get("reportFilters", [])
    if not isinstance(report_filters, list):
        return []
    return report_filters


def _group_entries_by_site(
    entries: dict[str, ReportEntry],
) -> list[tuple[type, list[ReportEntry]]]:
    """``site_for(url)`` で組織を解決し、同じ組織のレポートをまとめる。

    戻り値は「(組織クラス, その組織のレポート一覧)」のタプルのリスト。
    組織の登録順を保つため ``defaultdict(list)`` ではなく ``dict`` を使い、
    出現順を保持する。各値のリストも ``entries`` の挿入順を維持する。
    """
    grouped: dict[type, list[ReportEntry]] = {}
    for entry in entries.values():
        site_class = site_for(entry.url)
        grouped.setdefault(site_class, []).append(entry)
    # ``dict`` は挿入順を保つので、list() 化だけで安定する
    return list(grouped.items())


def _write_csv(output_path: Path, rows: list[_FilterRow]) -> None:
    """1 行ずつ dict で受け取ったデータを CSV に書き出す。

    Excel で開いて文字化けしないよう BOM 付き UTF-8 (``utf-8-sig``) で書く。
    ``newline=""`` を付けないと Windows で空行が混ざる (``csv`` モジュール
    の公式ガイドに従う)。
    """
    with output_path.open("w", encoding=Encoding.UTF8_SIG, newline="") as file:
        writer = csv.DictWriter(file, fieldnames=CSV_HEADERS)
        writer.writeheader()
        # TypedDict を ``writerows`` の ``rowdicts`` 引数に直接渡すと
        # pyright がキー型の invariance を理由にエラーにする。
        # TypedDict は dict のサブクラスなので実行時は問題ない。``Any`` で
        # 一段ラップして、責務上「Mapping として読める dict のリスト」だけ
        # を伝えている
        writer.writerows(rows)  # type: ignore[arg-type]


def dump_report_filters(
    master_path: str | Path | None,
    output_path: Path,
) -> int:
    """本体。``main()`` とテスト両方から呼ばれる。戻り値は書き出した行数。

    Args:
        master_path: 管理表（Excel）のパス。``None`` のときは ``load_master()``
            の既定（``comken.services.salesforce_downloader._paths`` の
            ``MASTER_PATH``）を使う。
        output_path: 出力先 CSV パス。

    Returns:
        CSV に書き出した行数（見出し行は含まない）。
    """
    entries = load_master(master_path)
    if not entries:
        logger.warning("管理表に登録されているレポートがありません: %s", master_path)
        _write_csv(output_path, [])
        return 0

    grouped = _group_entries_by_site(entries)
    logger.info("管理表: %d 件 / 組織: %d グループ", len(entries), len(grouped))

    rows: list[_FilterRow] = []
    processed = 0
    total = len(entries)
    for site_class, site_entries in grouped:
        logger.info(
            "組織 %s: %d 件を処理します",
            getattr(site_class, "DISPLAY_NAME", site_class.__name__),
            len(site_entries),
        )
        # 同じ組織のレポートは 1 つの ``with site() as sf:`` にまとめて、
        # 認証・接続を 1 組織 1 回にする
        try:
            with site_class() as salesforce_client:
                for entry in site_entries:
                    processed += 1
                    if processed % PROGRESS_LOG_INTERVAL == 0 or processed == total:
                        logger.info("処理中: %d/%d 件目 (%s)", processed, total, entry.key)
                    try:
                        report_filters = _describe_report_filters(salesforce_client, entry)
                    except Exception as exc:
                        # 想定した失敗（権限・削除済み・通信断）も想定外（バグ）も
                        # 1 件の失敗で全体を止めない方針のため、広く捕捉する
                        logger.error("describe に失敗しました: %s（%s）", entry.key, exc)
                        rows.append(
                            _FilterRow(
                                管理番号=entry.key,
                                レポートID=entry.report_id,
                                URL=entry.url,
                                フィルタ列="",
                                演算子="",
                                値=f"{FAILED_PREFIX}{exc}",
                            )
                        )
                        continue
                    rows.extend(_filters_to_rows(entry, report_filters))
        except Exception as exc:
            # 1 組織丸ごと失敗した場合、その組織の登録件すべてを「取得失敗」行として残す
            # 想定した失敗（認証・接続）も想定外（バグ）も 1 組織の失敗で全体を止めない
            # 方針のため、広く捕捉する
            logger.error(
                "%s への接続に失敗しました: %s",
                getattr(site_class, "DISPLAY_NAME", site_class.__name__),
                exc,
            )
            for entry in site_entries:
                rows.append(
                    _FilterRow(
                        管理番号=entry.key,
                        レポートID=entry.report_id,
                        URL=entry.url,
                        フィルタ列="",
                        演算子="",
                        値=f"{FAILED_PREFIX}{exc}",
                    )
                )

    _write_csv(output_path, rows)
    logger.info(
        "%s へ %d 行を書き出しました（管理表 %d 件）",
        output_path,
        len(rows),
        len(entries),
    )
    return len(rows)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--master",
        type=Path,
        default=None,
        help=(
            "管理表（Excel）のパス。省略時は ``load_master()`` の既定"
            "（``comken.services.salesforce_downloader._paths.MASTER_PATH``）"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help=f"出力先 CSV パス（既定 {DEFAULT_OUTPUT_PATH}）",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    dump_report_filters(args.master, args.output)
    return 0


if __name__ == "__main__":
    main()
