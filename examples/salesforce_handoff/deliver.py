r"""サンプル: 受け渡しフォルダから、決まった配り先へ配る（配布担当）。

`copy A B` の bat がプロジェクトの数だけ増えるのは、**配り先が既存の RPA に
決められていて、そこを変えられない**ため。変えられないなら、変えなくていい形にする。

    受け渡しフォルダ（1か所に集約）
        案件一覧_20260814.csv
            ↓  このファイル（管理表のとおりに配る）
    \\server\rpa_a\input\案件.csv        ← RPA が見ている場所・名前のまま
    \\server\rpa_b\データ\売上_最新.csv   ← 別の RPA には別の名前で

こうすると、

- **配り先を1つも変えずに済む。** 既存の RPA も bat も影響を受けない
- **「どれがどこへ行くか」が管理表1つに集まる。** 今は bat のコピー行に散っていて、
  全部を開かないと把握できない
- **取得と配布が切れる。** 取得が落ちても受け渡しフォルダへ手で置けば、
  ここから先はそのまま動く（→ download.py）

配り先はフォルダではなく**ファイル名まで**書く。RPA が固定名で待っていることが多く、
配りながら名前を変える必要があるため。管理表の値をそのまま保存先に使う。

実行方法:
    リポジトリのルートで python -m examples.salesforce_handoff.deliver
"""

import logging
import sys
from pathlib import Path

from comken.csv import CsvReader
from comken.handoff import Handoff
from comken.logger import setup_logging
from comken.utils.files import copy_file

HERE = Path(__file__).parent

# 取得側（download.py）と同じ管理表を読む。名前と配り先の対応が2か所に分かれない
REPORT_LIST_PATH = HERE / "レポート一覧.csv"
NAME_COLUMN = "名前"
DESTINATION_COLUMN = "配り先"

# 受け渡しフォルダ。取得担当（download.py）と同じ場所を指す
HANDOFF_FOLDER = Path(r"\\server\share\受け渡し")

logger = logging.getLogger(__name__)


def main() -> int:
    """受け渡しフォルダのファイルを、管理表のとおりに配る。"""
    setup_logging()
    destinations = {
        row[NAME_COLUMN]: row[DESTINATION_COLUMN] for row in CsvReader(REPORT_LIST_PATH).read_rows()
    }
    handoff = Handoff(HANDOFF_FOLDER)

    # 配る前に全部揃っているか確かめる。1つ足りないまま配り始めると、
    # 配り先によって新しい日付と古い日付が混ざる
    files = handoff.require(*destinations)

    for name, source in files.items():
        delivered = copy_file(source, Path(destinations[name]))
        logger.info("配りました: %s → %s", source.name, delivered)

    logger.info("%d 件を配りました。", len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
