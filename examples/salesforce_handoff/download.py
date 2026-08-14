r"""サンプル: Salesforce のレポートを1つのプロジェクトでまとめて落とす（取得担当）。

各プロジェクトが個別に取りに行くと、同じレポートを何度も叩き、認証情報の登録先も
プロジェクトの数だけ増える。取得はここ1本にまとめ、**落としたものは受け渡しフォルダへ
置くだけ**にする。使う側は取得の手段を知らない。

    Salesforce ──→ 受け渡しフォルダ ──→ 配り先（既存の RPA が見ている場所）
                   （このファイル）      （deliver.py）

**何を落とすかはコードに書かず、管理表（レポート一覧.csv）に書く。** レポートは
増えるので、増えるたびにコードを直す形にしない。管理表には Salesforce の画面の
アドレスをそのまま貼れる（ID の部分だけ抜き出す工程で写し間違いが起きるため）。

    名前,レポートURL,配り先
    案件一覧,https://組織A.../lightning/r/Report/00O.../view,\\server\rpa_a\input\案件.csv
    売上,https://組織B.../lightning/r/Report/00O.../view,\\server\rpa_b\データ\売上.csv

**組織は URL のドメインで決まる。** 表に組織を選ぶ列は作らない（URL と食い違ったとき、
別組織へ問い合わせて「レポートが無い」という分かりにくい失敗になる）。
組織ごとにまとめてから接続するので、認証は組織につき1回で済む。

Excel で管理したいときは、CsvReader を ExcelReader に変えるだけでよい
（列名が同じなら、あとの処理は変わらない）。

4つ決めてある。

1. **すでに置かれているものは取りに行かない。** 落とし直しの時間を省くためだけでなく、
   **人が手で置いたファイルを上書きしないため**。取得が失敗した分を手で置いて再実行
   すれば、残りだけを取りに行く。
2. **1件失敗しても残りは続ける。** 組織ごと落ちた場合も、その組織の分だけを失敗にする。
   5本のうち1本が落ちたときに全部落とすと、手で用意する手間が5本ぶんになる。
3. **0 行は成功にしない。** 空の CSV を置くと、使う側は「データが無い日」と
   「取得が失敗した日」を区別できなくなる。
4. **失敗があれば終了コード 1 を返す。** 途中で続けたぶん、最後に必ず失敗を報せる。
   ログだけに出して 0 を返すと、RPA 基盤側から見て成功と区別が付かない。

事前準備:
    認証情報の登録（python -m comken.credentials gui）と、
    組織クラスの DOMAIN_URL・レポート一覧.csv を実際の組織のものに書き換える。

実行方法:
    リポジトリのルートで python -m examples.salesforce_handoff.download
"""

import logging
import sys
from pathlib import Path

from comken.csv import CsvReader, CsvWriter
from comken.exceptions import ComkenError
from comken.handoff import Handoff
from comken.logger import setup_logging
from comken.salesforce import SalesforceBase, report_id_from_url
from comken.salesforce.sites import site_for

HERE = Path(__file__).parent

# 何を落として、どこへ配るかを書いた管理表。増減はこのファイルだけを直す
REPORT_LIST_PATH = HERE / "レポート一覧.csv"
NAME_COLUMN = "名前"
URL_COLUMN = "レポートURL"

# 受け渡しフォルダ。使う側と取得側が同じ場所を指すよう、共有サーバー上の1か所にする
HANDOFF_FOLDER = Path(r"\\server\share\受け渡し")

logger = logging.getLogger(__name__)


def main() -> int:
    """管理表のレポートをまとめて落とし、受け渡しフォルダへ置く。失敗があれば 1 を返す。"""
    setup_logging()
    handoff = Handoff(HANDOFF_FOLDER)
    reports = CsvReader(REPORT_LIST_PATH).read_rows()

    pending, failed = _group_by_site(reports, handoff)
    for site, rows in pending.items():
        failed.extend(_download_site(site, rows, handoff))

    return _report_result(handoff, failed)


def _group_by_site(
    reports: list[dict], handoff: Handoff
) -> tuple[dict[type[SalesforceBase], list[dict]], list[str]]:
    """まだ置かれていないレポートを組織ごとにまとめる。組織を引けなかったものは失敗にする。"""
    pending: dict[type[SalesforceBase], list[dict]] = {}
    failed: list[str] = []
    for report in reports:
        name = report[NAME_COLUMN]
        if handoff.find(name) is not None:
            # 手で置いたものも「置いてある」として扱う。上書きしない
            logger.info("すでに置かれているので飛ばします: %s", handoff.path_of(name).name)
            continue
        try:
            site = site_for(report[URL_COLUMN])
        except ComkenError as error:
            logger.error("組織を特定できません: %s（%s）", name, error)
            failed.append(name)
            continue
        pending.setdefault(site, []).append(report)
    return pending, failed


def _download_site(site: type[SalesforceBase], reports: list[dict], handoff: Handoff) -> list[str]:
    """1つの組織へつないで、その組織のレポートを順に落とす。失敗した名前を返す。"""
    failed: list[str] = []
    try:
        with site() as salesforce:
            for report in reports:
                name = report[NAME_COLUMN]
                try:
                    _download(salesforce, name, report[URL_COLUMN], handoff)
                except ComkenError as error:
                    # 1件の失敗で残りを落とさない。何が失敗したかは最後にまとめて出す
                    logger.error("取得に失敗しました: %s（%s）", name, error)
                    failed.append(name)
    except ComkenError as error:
        # 認証やネットワークで組織ごと落ちた場合。ほかの組織は続ける
        logger.error("%s へつなげませんでした（%s）", site.__name__, error)
        failed.extend(
            report[NAME_COLUMN] for report in reports if report[NAME_COLUMN] not in failed
        )
    return failed


def _download(salesforce: SalesforceBase, name: str, url: str, handoff: Handoff) -> None:
    """レポート1本を落として、受け渡しフォルダへ CSV で置く。"""
    rows = salesforce.report.run(report_id_from_url(url))
    if not rows:
        # 0 行は「取れた」と言い切れないので、置かずに失敗として扱う
        raise _EmptyReportError(name, url)

    path = handoff.path_of(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    CsvWriter(path, list(rows[0])).write_rows(rows)
    logger.info("置きました: %s（%d 行）", path.name, len(rows))


def _report_result(handoff: Handoff, failed: list[str]) -> int:
    """結果をログに出して終了コードを返す。"""
    if not failed:
        logger.info("すべて置きました: %s", handoff.folder)
        return 0

    logger.error("%d 件が取得できませんでした。手で置く場合の置き場所:", len(failed))
    for name in failed:
        logger.error("  %s", handoff.path_of(name))
    return 1


class _EmptyReportError(ComkenError):
    """レポートは取れたが明細が 0 行だった（このプロジェクト固有の失敗）。

    comken の例外にしないのは、0 行を異常と見るかが業務ごとに違うため。
    「毎日必ず何か入っている」と分かっているこのプロジェクトでだけ失敗にする。
    """

    def __init__(self, name: str, url: str) -> None:
        super().__init__(
            f"レポートの明細が 0 行でした: {name}\n"
            f"{url}\n"
            "取得の失敗と区別できないため、受け渡しフォルダには置きません。"
        )


if __name__ == "__main__":
    sys.exit(main())
