"""comken/toolbox/excel/reader.py — Excel を読み取り専用で開く入口。"""

from pathlib import Path

from comken.toolbox.excel.base import ExcelBase


class ExcelReader(ExcelBase):
    """Excel ブックを読み取り専用で開くクラス。

    read_only=True で開くため、大きなブックもメモリ効率よく速く読み取れる。
    書き込みメソッドを持たないので、誤って元ファイルを書き換える事故を防げる。

    """

    def __init__(
        self,
        path: str | Path,
        data_only: bool = False,
        local_copy_threshold_mb: float = 10,
        headers: list[str] | None = None,
        tables: bool = False,
    ) -> None:
        """
        Args:
            path: Excel ファイルのパス。
            data_only: True にすると数式セルのキャッシュ値を読む（read_computed_rows 推奨）。
            local_copy_threshold_mb: この MB 以上のファイルはローカルにコピーしてから開く。
                NAS・ネットワークドライブのファイルが遅い・不安定な場合に有効。
                0 を指定するとローカルコピーを無効化できる。
            headers: ヘッダー行がない Excel の場合に、列名のリストをここで付ける。
                指定すると read_rows_as_dicts() は全行をデータとして読む。
            tables: True にするとテーブル名で読むために read_only=False で開く。
                大きなブックでもメモリ効率が下がる点に注意。
                read_only モードでは openpyxl がテーブル定義を読めないため、
                read_table() を呼ぶときに必要。
        """
        super().__init__(
            path,
            data_only=data_only,
            read_only=not tables,
            local_copy_threshold_mb=local_copy_threshold_mb,
            headers=headers,
        )
