"""``Table.split_hierarchy()``（階層列の上埋めと小計行の分離）のテスト。"""

import logging

import pytest

from comken.core.table import Table
from comken.exceptions.tables import TableColumnNotFoundError, TableError

# ---------------------------------------------------------------------------
# テスト用のヘルパー
# ---------------------------------------------------------------------------


def _sample_rows() -> list[dict[str, object | int | None]]:
    """仕様の確認に使う 10 行のサンプルデータ。"""
    return [
        {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん", "金額": 100},
        {"大分類": None, "中分類": None, "小分類": "たまねぎ", "金額": 50},
        {"大分類": None, "中分類": "野菜計", "小分類": None, "金額": 150},
        {"大分類": None, "中分類": "果物", "小分類": "りんご", "金額": 80},
        {"大分類": None, "中分類": None, "小分類": "小計", "金額": 80},
        {"大分類": "食品 合計", "中分類": None, "小分類": None, "金額": 230},
        {"大分類": "日用品", "中分類": None, "小分類": "洗剤", "金額": 300},
        {"大分類": None, "中分類": None, "小分類": "時計", "金額": 1000},
        {"大分類": None, "中分類": None, "小分類": None, "金額": None},
        {"大分類": "総計", "中分類": None, "小分類": None, "金額": 1530},
    ]


def _sample_table() -> Table:
    """仕様の確認に使う 10 行のサンプル Table。"""
    return Table(["大分類", "中分類", "小分類", "金額"], _sample_rows())


# ---------------------------------------------------------------------------
# 仕様のテスト
# ---------------------------------------------------------------------------


def test_split_hierarchy_separates_details_and_subtotals() -> None:
    """仕様の 10 行で、明細と小計が正しく分かれることを確認する。"""
    table = _sample_table()

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    # 明細は 1, 2, 4, 7, 8 件目の 5 件
    assert result.details.to_rows() == [
        {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん", "金額": 100},
        {"大分類": "食品", "中分類": "野菜", "小分類": "たまねぎ", "金額": 50},
        {"大分類": "食品", "中分類": "果物", "小分類": "りんご", "金額": 80},
        {"大分類": "日用品", "中分類": None, "小分類": "洗剤", "金額": 300},
        {"大分類": "日用品", "中分類": None, "小分類": "時計", "金額": 1000},
    ]
    # 小計は 3, 5, 6, 10 件目の 4 件
    assert result.subtotals.to_rows() == [
        {"大分類": "食品", "中分類": "野菜計", "小分類": None, "金額": 150},
        {"大分類": "食品", "中分類": "果物", "小分類": "小計", "金額": 80},
        {"大分類": "食品 合計", "中分類": None, "小分類": None, "金額": 230},
        {"大分類": "総計", "中分類": None, "小分類": None, "金額": 1530},
    ]
    # 時計は「計」で終わるが小計ではないので unmatched に入る
    assert result.unmatched == [8]


def test_split_hierarchy_keeps_int_type() -> None:
    """数値の列は int のまま出力されること（str にしない）。"""
    table = Table(
        ["大分類", "金額"],
        [{"大分類": "食品", "金額": 100}, {"大分類": None, "金額": 50}],
        types={"金額": int},
    )

    result = table.split_hierarchy(["大分類"])

    amounts = [row["金額"] for row in result.details]
    assert amounts == [100, 50]
    assert all(isinstance(amount, int) for amount in amounts)
    # 元の types もそのまま引き継がれている
    assert result.details.types == {"金額": int}


def test_split_hierarchy_handles_numeric_category_codes() -> None:
    """数値の分類コード（int）でも動き、出力も int のまま、current+計も拾える。

    「10計」は current=10 の小計として判定される（ルール 3）。
    """
    table = Table(
        ["大分類", "中分類", "金額"],
        [
            {"大分類": 10, "中分類": 20, "金額": 100},
            {"大分類": None, "中分類": None, "金額": 50},
            {"大分類": None, "中分類": "20計", "金額": 150},
            {"大分類": "10計", "中分類": None, "金額": 150},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類"])

    # 明細は最初の 2 行
    assert result.details.to_rows() == [
        {"大分類": 10, "中分類": 20, "金額": 100},
        {"大分類": 10, "中分類": 20, "金額": 50},
    ]
    # 小計の「大分類」と「中分類」は元の int のまま
    assert result.subtotals.to_rows() == [
        {"大分類": 10, "中分類": "20計", "金額": 150},
        {"大分類": "10計", "中分類": None, "金額": 150},
    ]
    # int 型が保たれる（current から引き継いだ int 値）
    assert all(isinstance(row["大分類"], int) for row in result.details)
    assert all(isinstance(row["中分類"], int) for row in result.details)
    # 小計行の「大分類」が current の int のものはそのまま（上の階層=current）
    int_subtotal_rows = [row for row in result.subtotals if row["大分類"] == 10]
    assert int_subtotal_rows
    assert all(isinstance(row["大分類"], int) for row in int_subtotal_rows)


def test_split_hierarchy_normalizes_float_integers_for_comparison() -> None:
    """Excel COM が整数を float で返すため、float の current でも「計」ルールが動く。

    10.0 → ``"10"`` に正規化してから比較するため、current=10.0 のときの「10計」が拾える。
    出力の大分類は元の float のまま。
    """
    table = Table(
        ["大分類", "金額"],
        [
            {"大分類": 10.0, "金額": 100},
            {"大分類": None, "金額": 50},
            {"大分類": "10計", "金額": 150},
        ],
    )

    result = table.split_hierarchy(["大分類"])

    # 明細は最初の 2 行、current は 10.0 のまま引き継ぐ
    assert result.details.to_rows() == [
        {"大分類": 10.0, "金額": 100},
        {"大分類": 10.0, "金額": 50},
    ]
    # 小計の「大分類」は元の文字列
    assert result.subtotals.to_rows() == [
        {"大分類": "10計", "金額": 150},
    ]
    # float 型が保たれる（current から引き継いだ float 値）
    assert all(isinstance(row["大分類"], float) for row in result.details)


def test_split_hierarchy_keeps_current_when_top_level_unchanged() -> None:
    """上の階層が前と同じ値なら、下の current を切らない。

    大分類を毎行書いてある表で、中分類が空の行が前の中分類を引き継げることを確かめる。
    """
    table = Table(
        ["大分類", "中分類", "小分類"],
        [
            {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
            {"大分類": "食品", "中分類": None, "小分類": "たまねぎ"},
            {"大分類": "食品", "中分類": None, "小分類": "だいこん"},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    # 全行が明細、大分類・中分類は current の値で埋まる
    assert result.details.to_rows() == [
        {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
        {"大分類": "食品", "中分類": "野菜", "小分類": "たまねぎ"},
        {"大分類": "食品", "中分類": "野菜", "小分類": "だいこん"},
    ]
    assert result.subtotals.to_rows() == []


def test_split_hierarchy_resets_current_when_top_level_changes() -> None:
    """上の階層が変わったら、下の current を空に戻す（毎行書いてある表でも）。"""
    table = Table(
        ["大分類", "中分類", "小分類"],
        [
            {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
            {"大分類": "食品", "中分類": "野菜", "小分類": "たまねぎ"},
            {"大分類": "日用品", "中分類": None, "小分類": "洗剤"},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    # 大分類が日用品に変わった行の中分類は None
    assert result.details.to_rows() == [
        {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
        {"大分類": "食品", "中分類": "野菜", "小分類": "たまねぎ"},
        {"大分類": "日用品", "中分類": None, "小分類": "洗剤"},
    ]


def test_split_hierarchy_subtotal_does_not_update_current() -> None:
    """小計行では current を更新しない（小計の「野菜計」の値が current を壊さない）。

    小計行で大分類の「野菜計」が current に入ると、その後の明細行で大分類が
    「野菜計」になる壊れた版を検出する。
    """
    table = Table(
        ["大分類", "中分類", "小分類"],
        [
            {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
            {"大分類": None, "中分類": None, "小分類": None},
            {"大分類": "野菜計", "中分類": None, "小分類": None},  # 小計
            {"大分類": None, "中分類": "果物", "小分類": "りんご"},  # 直後の明細
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    # 小計行では current を更新しないので、直後の明細の大分類は「食品」のまま
    detail_rows = result.details.to_rows()
    assert detail_rows[1] == {
        "大分類": "食品",
        "中分類": "果物",
        "小分類": "りんご",
    }


def test_split_hierarchy_single_level() -> None:
    """1 階層だけでも動く（上の階層が変わったら下が空になる挙動は層が 1 つなら無関係）。"""
    table = Table(
        ["大分類", "金額"],
        [
            {"大分類": "食品", "金額": 100},
            {"大分類": None, "金額": 50},
            {"大分類": "日用品", "金額": 300},
            {"大分類": None, "金額": 1000},
        ],
    )

    result = table.split_hierarchy(["大分類"])

    assert result.details.to_rows() == [
        {"大分類": "食品", "金額": 100},
        {"大分類": "食品", "金額": 50},
        {"大分類": "日用品", "金額": 300},
        {"大分類": "日用品", "金額": 1000},
    ]
    assert result.subtotals.to_rows() == []


def test_split_hierarchy_raises_on_excel_error_in_level_column() -> None:
    """階層の列に Excel のエラー値があると ``TableError`` になり、件目と列名が出る。"""
    table = Table(
        ["大分類", "中分類", "金額"],
        [
            {"大分類": "食品", "中分類": "野菜", "金額": 100},
            {"大分類": "#REF!", "中分類": None, "金額": 50},
        ],
    )

    with pytest.raises(TableError, match="2件目") as exc_info:
        table.split_hierarchy(["大分類", "中分類"])
    assert "大分類" in str(exc_info.value)
    assert "#REF!" in str(exc_info.value)


def test_split_hierarchy_excel_error_in_non_level_column_passes_through() -> None:
    """階層以外の列（金額）の Excel エラー値はそのまま明細に出る（小計判定とは無関係）。"""
    table = Table(
        ["大分類", "中分類", "金額"],
        [
            {"大分類": "食品", "中分類": "野菜", "金額": 100},
            {"大分類": None, "中分類": None, "金額": "#DIV/0!"},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類"])

    # 両方が明細に出る
    assert len(result.details) == 2
    assert result.details.to_rows()[1]["金額"] == "#DIV/0!"


def test_split_hierarchy_raises_on_unknown_column() -> None:
    """存在しない列名を指定したら TableColumnNotFoundError になる。"""
    table = Table(["大分類", "金額"], [{"大分類": "食品", "金額": 100}])

    with pytest.raises(TableColumnNotFoundError):
        table.split_hierarchy(["大分類", "存在しない列"])


def test_split_hierarchy_custom_subtotal_words_and_suffixes() -> None:
    """``subtotal_words`` / ``subtotal_suffixes`` を渡すと判定が変わる。

    ``subtotal_suffixes`` に ``"部署計"`` を足すと「営業部署計」が小計になる
    （デフォルトでは「営業部署計」は小計にならない）。
    """
    table = Table(
        ["部署", "金額"],
        [
            {"部署": "営業", "金額": 100},
            {"部署": None, "金額": 50},
            {"部署": "営業部署計", "金額": 150},
        ],
    )

    # デフォルトでは「営業部署計」は小計にならない
    default_result = table.split_hierarchy(["部署"])
    assert default_result.unmatched == [3]

    # subtotal_suffixes に "部署計" を足すと小計になる
    result = table.split_hierarchy(
        ["部署"], subtotal_suffixes=("部署計",)
    )
    assert len(result.subtotals) == 1
    assert result.subtotals.to_rows()[0] == {"部署": "営業部署計", "金額": 150}
    assert result.unmatched == []


def test_split_hierarchy_does_not_mutate_source() -> None:
    """元の Table が変わっていないこと（新しい Table を返す）。"""
    table = _sample_table()
    before = table.to_rows()

    _ = table.split_hierarchy(["大分類", "中分類", "小分類"])

    assert table.to_rows() == before


def test_split_hierarchy_preserves_types_on_result() -> None:
    """結果の ``types`` が元の ``types`` と同じ（ ``_from_normalized_rows`` の流儀）。"""
    table = Table(
        ["大分類", "金額"],
        [{"大分類": "食品", "金額": 100}],
        types={"金額": int},
    )

    result = table.split_hierarchy(["大分類"])

    assert result.details.types == {"金額": int}


def test_split_hierarchy_all_empty_rows_are_dropped() -> None:
    """全部の列が空の行はどちらにも出ない（金額だけでも値があれば明細に出る）。"""
    table = Table(
        ["大分類", "中分類", "金額"],
        [
            {"大分類": None, "中分類": None, "金額": None},  # 全部空 → スキップ
            {"大分類": "食品", "中分類": None, "金額": 2},
            {"大分類": None, "中分類": None, "金額": None},  # 全部空 → スキップ
            {"大分類": None, "中分類": None, "金額": 3},  # 金額に値があるので明細
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類"])

    # 1, 3 件目はスキップ、2 と 4 件目は明細。4 件目の大分類は 2 件目の current が入る
    assert result.details.to_rows() == [
        {"大分類": "食品", "中分類": None, "金額": 2},
        {"大分類": "食品", "中分類": None, "金額": 3},
    ]
    assert result.subtotals.to_rows() == []


def test_split_hierarchy_warns_on_unmatched_kei(caplog: pytest.LogCaptureFixture) -> None:
    """「計」で終わるのに小計判定外なら ``logger.warning`` で知らせる。"""
    table = Table(
        ["大分類", "中分類"],
        [
            {"大分類": "食品", "中分類": "野菜"},
            {"大分類": None, "中分類": "時計"},
        ],
    )

    with caplog.at_level(logging.WARNING, logger="comken.core.table.hierarchy"):
        result = table.split_hierarchy(["大分類", "中分類"])

    assert result.unmatched == [2]
    assert any("2件目" in record.getMessage() for record in caplog.records)
    assert any("時計" in record.getMessage() for record in caplog.records)


def test_split_hierarchy_rule3_picks_current_plus_kei() -> None:
    """ルール 3 の確認: current + 「計」と完全一致する値を小計にする。

    中分類の現在値が「野菜」のとき、「野菜計」は小計として拾われる
    （デフォルトの subtotal_suffixes には「計」だけしかないため、ルール 3 のみ
    で拾えることを確認している）。
    """
    table = Table(
        ["大分類", "中分類", "小分類"],
        [
            {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
            {"大分類": None, "中分類": None, "小分類": "たまねぎ"},
            {"大分類": None, "中分類": "野菜計", "小分類": None},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    assert result.unmatched == []
    assert len(result.subtotals) == 1
    assert result.subtotals.to_rows()[0]["中分類"] == "野菜計"


def test_split_hierarchy_uses_topmost_matched_level() -> None:
    """小計の言葉が複数の階層に出ても、一番上の階層が基準になる。"""
    table = Table(
        ["大分類", "中分類", "小分類"],
        [
            {"大分類": "食品", "中分類": "野菜", "小分類": "にんじん"},
            {"大分類": None, "中分類": None, "小分類": "たまねぎ"},
            # 複数の階層に「小計」が出ている
            {"大分類": "小計", "中分類": "小計", "小分類": None},
        ],
    )

    result = table.split_hierarchy(["大分類", "中分類", "小分類"])

    # 一番上の大分類が基準になり、matched level（大分類）の上は current、
    # matched level は元の値、下は None
    assert result.subtotals.to_rows() == [
        {"大分類": "小計", "中分類": None, "小分類": None},
    ]


def test_split_hierarchy_returns_empty_tables_when_no_data() -> None:
    """空の Table でもエラーにならず、空の details / subtotals が返る。"""
    table = Table(["大分類", "中分類"], [])

    result = table.split_hierarchy(["大分類", "中分類"])

    assert result.details.to_rows() == []
    assert result.subtotals.to_rows() == []
    assert result.unmatched == []


def test_split_hierarchy_accepts_tuple_for_levels() -> None:
    """``levels`` は tuple でも list でも受け付ける（シグネチャ通り）。"""
    table = _sample_table()

    result = table.split_hierarchy(("大分類", "中分類", "小分類"))

    assert len(result.details) == 5
