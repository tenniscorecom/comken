"""comken/core/files/name.py — ファイル名の組み立て。

命名方式を追加するときは、ここに追記する（1ファイル内でクラスを増やす）。
UUID・タイムスタンプ・ランダム値・連番などは標準ライブラリで十分なため、
comken ではラップしない方針（薄いラッパーを増やさない）。
現状は ``DateNameBuilder`` のみ。

``core/files/naming/`` パッケージから ``name.py`` 単一ファイルに集約した
経緯は、命名レビュー（2026-08-19）を参照。
"""

from datetime import date, datetime

from comken.core.clock import now


class DateNameBuilder:
    """今日の日付を付けたファイル名を組み立てる。

    日付は ``__init__`` 時点で確定する。``for_date=None`` のときだけ
    ``__init__`` 呼び出し時点の日付を使い、``prefix()`` / ``suffix()`` を
    呼ぶたびに日付を取り直すことはない。

    日付はコンストラクタで固定できる。テストや過去日付のファイル名を組み立てる
    ときは ``date(2026, 8, 20)`` 等を渡す。省略時は呼び出し時点の日付。
    """

    def __init__(
        self,
        name: str,
        for_date: date | datetime | None = None,
        ext: str = ".xlsx",
    ) -> None:
        """
        Args:
            name: ファイル名（拡張子なし）。
            for_date: ファイル名に付ける日付。``None``（既定）なら ``__init__``
                呼び出し時点の日付。``prefix()`` / ``suffix()`` を呼ぶたびに
                日付を取り直すことはない。``date`` / ``datetime`` どちらも
                受け付ける（``datetime`` は内部で ``.date()`` に変換）。
            ext: 拡張子（デフォルト: ".xlsx"）。ドットなしで渡しても補完される。
        """
        self._name = name
        self._date = _resolve_date(for_date)
        self._ext = ext if ext.startswith(".") else f".{ext}"

    def prefix(self, prefix: str = "{:%Y%m%d}_") -> str:
        """prefix + 日付 + ベース名を返す。

        ``prefix("DIY_{:%Y%m%d}_")`` のように日付の位置と書式を指定する。
        日付書式を含まない prefix には ``YYYYMMDD`` を末尾へ補う。
        """
        dated_prefix = (
            prefix.format(self._date) if "{:" in prefix else f"{prefix}{self._date:%Y%m%d}_"
        )
        return f"{dated_prefix}{self._name}{self._ext}"

    def suffix(self, date_format: str = "%Y%m%d") -> str:
        """今日の日付を後ろに付けたファイル名を返す（例: 売上レポート_20260711.xlsx）。"""
        return f"{self._name}_{self._date.strftime(date_format)}{self._ext}"


def _resolve_date(value: date | datetime | None) -> date | datetime:
    """``for_date`` 引数を正規化する。``None`` のときは ``now()`` をそのまま返す
    （秒単位まで含めたフォーマットに対応するため ``date`` には丸めない）。
    """
    if value is None:
        return now()
    if isinstance(value, datetime):
        return value
    return value
