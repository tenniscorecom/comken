"""現行の Table / Transfer を使う、非破壊転記の最小例。"""
# ruff: noqa: T201

from typing import Any

from comken.core.table import Table, Transfer

Row = dict[str, Any]


def main() -> None:
    read = Table(
        ["顧客ID", "住所", "対象"], [{"顧客ID": "A001", "住所": "東京都", "対象": "対象外"}]
    )
    write = Table(
        ["お客様ID", "住所", "備考"], [{"お客様ID": "A001", "住所": "旧住所", "備考": ""}]
    )

    def transform(read_row: Row, working_row: Row | None) -> object | None:
        if working_row is None or read_row["対象"] == "対象":
            return Transfer.SKIP
        working_row["備考"] = "CSVから更新"
        return None

    result = Transfer(read, write, {"住所": "住所"}, read_key="顧客ID", write_key="お客様ID").run(
        transform=transform
    )
    print("転記結果:", result.read())
    print("入力は不変:", read.read(), write.read())

    master = Table(["顧客ID", "担当者"], [{"顧客ID": "A001", "担当者": "山田"}])
    print("結合結果:", read.merge(master, on="顧客ID").read())


if __name__ == "__main__":
    main()
