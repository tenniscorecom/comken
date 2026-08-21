"""Table と Transfer の最小設計サンプル。

ここでは Excel や CSV の実装を入れず、データ操作の形だけを確認する。
CSV / Excel のアダプターは、最終的に Table を返す想定。
"""

from collections.abc import Callable, Iterable, Mapping
from typing import Any


Row = dict[str, Any]
Transform = Callable[[Row, Row | None], object]


class Table:
    """行を辞書のリストとして保持する、簡易DataFrame。"""

    def __init__(self, rows: Iterable[Mapping[str, Any]]) -> None:
        self.rows: list[Row] = [dict(row) for row in rows]

    def read(self) -> list[Row]:
        """現在の行を返す。"""
        return self.rows

    def replace(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """テーブルのデータを全置換する。"""
        self.rows = [dict(row) for row in rows]

    def find_one(self, column: str, value: Any) -> Row | None:
        """指定列の値で1行を探す。複数件ならデータ不備として止める。"""
        matches = [row for row in self.rows if row.get(column) == value]
        if len(matches) > 1:
            raise ValueError(f"キーが重複しています: {column}={value!r}")
        return matches[0] if matches else None

    def select(self, columns: list[str]) -> "Table":
        """指定した列だけを持つ新しいTableを返す。"""
        return Table([{column: row.get(column, "") for column in columns} for row in self.rows])

    def filter(self, column: str, value: Any) -> "Table":
        """指定列の値が一致する行だけを持つ新しいTableを返す。"""
        return Table([row for row in self.rows if row.get(column) == value])

    def merge(
        self,
        other: "Table",
        *,
        left_on: str,
        right_on: str,
        how: str = "left",
    ) -> "Table":
        """キーで別のTableを結合する。まずはleft / innerだけ対応する。"""
        if how not in {"left", "inner"}:
            raise ValueError("how は 'left' または 'inner' を指定してください")

        merged_rows: list[Row] = []
        for left_row in self.rows:
            right_row = other.find_one(right_on, left_row.get(left_on))
            if right_row is None:
                if how == "left":
                    merged_rows.append(dict(left_row))
                continue

            merged_row = dict(left_row)
            for column, value in right_row.items():
                if column != right_on:
                    merged_row[column] = value
            merged_rows.append(merged_row)

        return Table(merged_rows)


class Transfer:
    """キーで行を照合し、利用者の変換関数で転記する。"""

    SKIP = object()
    STOP = object()

    def __init__(
        self,
        source: Table,
        destination: Table,
        source_key: str,
        destination_key: str,
    ) -> None:
        self.source = source
        self.destination = destination
        self.source_key = source_key
        self.destination_key = destination_key

    def run(self, transform: Transform) -> int:
        """変換関数を各行へ適用し、処理件数を返す。"""
        transferred = 0

        for source_row in self.source.read():
            destination_row = self.destination.find_one(
                self.destination_key,
                source_row.get(self.source_key),
            )
            result = transform(source_row, destination_row)

            if result is self.STOP:
                break
            if result is self.SKIP:
                continue
            if result is not None:
                raise TypeError("transform は None / SKIP / STOP のいずれかを返してください")
            if destination_row is not None:
                transferred += 1

        return transferred


def main() -> None:
    source = Table(
        [
            {"顧客ID": "A001", "住所": "東京都", "キャンペーン対象": "対象外"},
            {"顧客ID": "A002", "住所": "大阪府", "キャンペーン対象": "対象"},
            {"顧客ID": "A003", "住所": "愛知県", "キャンペーン対象": "対象外"},
        ]
    )
    destination = Table(
        [
            {"お客様ID": "A001", "住所": "旧住所", "備考": ""},
            {"お客様ID": "A002", "住所": "旧住所", "備考": ""},
            {"お客様ID": "A004", "住所": "旧住所", "備考": ""},
        ]
    )

    def transform(source_row: Row, destination_row: Row | None) -> object | None:
        # 転記先に該当するお客様がいなければ何もしない。
        if destination_row is None:
            return Transfer.SKIP

        # キャンペーン対象者は住所を更新しない。
        if source_row["キャンペーン対象"] == "対象":
            return Transfer.SKIP

        destination_row["住所"] = source_row["住所"]
        destination_row["備考"] = "CSVから更新"
        return None

    count = Transfer(
        source=source,
        destination=destination,
        source_key="顧客ID",
        destination_key="お客様ID",
    ).run(transform)

    print(f"転記件数: {count}")
    for row in destination.read():
        print(row)

    # XLOOKUPのような単純な結合は merge() で書ける。
    customer_master = Table(
        [
            {"顧客ID": "A001", "担当者": "山田"},
            {"顧客ID": "A003", "担当者": "佐藤"},
        ]
    )
    joined = source.merge(
        customer_master,
        left_on="顧客ID",
        right_on="顧客ID",
        how="left",
    )
    print("結合結果:")
    for row in joined.read():
        print(row)

    # 既存帳票へ直接書く場合は、Tableを使わずセル操作を残してよい。
    # 例: report_sheet.write_value("B3", "山田")


if __name__ == "__main__":
    main()
