"""comken/core/files/name.py — ファイル名の組み立て。

命名方式を追加するときは、ここに追記する（1ファイル内でクラスを増やす）。
UUID・タイムスタンプ・ランダム値・連番などは標準ライブラリで十分なため、
comken ではラップしない方針（薄いラッパーを増やさない）。
現状は ``DateNameBuilder`` のみ。

``core/files/naming/`` パッケージから ``name.py`` 単一ファイルに集約した
経緯は、命名レビュー（2026-08-19）を参照。

**拡張子は名前の文字列にだけ書く**（例: ``"売上.xlsx"``）。引数 ``ext`` は存在しない。
拡張子が無い名前は ``FileSuffixMissingError`` で止める。
「黙って ``.xlsx`` を付ける」挙動は廃止した（付け忘れの方が付け間違いより高くつくため）。
"""

from datetime import date, datetime
from pathlib import Path

from comken.core.clock import now
from comken.exceptions import FileSuffixMissingError


class DateNameBuilder:
    """今日の日付を付けたファイル名を組み立てる。

    日付は ``__init__`` 時点で確定する。``for_date=None`` のときだけ
    ``__init__`` 呼び出し時点の日付を使い、``prefix()`` / ``suffix()`` を
    呼ぶたびに日付を取り直すことはない。

    日付はコンストラクタで固定できる。テストや過去日付のファイル名を組み立てる
    ときは ``date(2026, 8, 20)`` 等を渡す。省略時は呼び出し時点の日付。

    拡張子は **名前の文字列に含めて** 渡す（例: ``DateNameBuilder("ログ.csv")``）。
    拡張子なしの名前は ``FileSuffixMissingError`` を送出して止める。
    """

    def __init__(
        self,
        name: str,
        for_date: date | datetime | None = None,
    ) -> None:
        """
        Args:
            name: ファイル名（**拡張子を含む**）。例: ``"売上.xlsx"`` / ``"ログ.csv"``。
                拡張子が無いと ``FileSuffixMissingError``。
            for_date: ファイル名に付ける日付。``None``（既定）なら ``__init__``
                呼び出し時点の日付。``prefix()`` / ``suffix()`` を呼ぶたびに
                日付を取り直すことはない。``date`` / ``datetime`` どちらも
                受け付ける（``datetime`` は内部で ``.date()`` に変換）。

        Raises:
            FileSuffixMissingError: ``name`` に拡張子が含まれていないとき。
        """
        self._stem, self._extension = _split_suffix(name)
        self._date = _resolve_date(for_date)

    def prefix(self, prefix: str = "{:%Y%m%d}_") -> str:
        """``prefix + 日付 + ベース名 + 拡張子`` を返す（例: ``"20260825_売上.xlsx"``）。

        ``prefix("DIY_{:%Y%m%d}_")`` のように日付の位置と書式を指定する。
        日付書式を含まない prefix には ``YYYYMMDD`` を末尾へ補う。
        日付は **拡張子の手前** に入る。
        """
        dated_prefix = (
            prefix.format(self._date) if "{:" in prefix else f"{prefix}{self._date:%Y%m%d}_"
        )
        return f"{dated_prefix}{self._stem}{self._extension}"

    def suffix(self, date_format: str = "%Y%m%d") -> str:
        """今日の日付を後ろに付けたファイル名を返す（例: ``"売上_20260825.xlsx"``）。

        日付は **拡張子の手前** に入る。メソッド名 ``suffix()`` と「拡張子（suffix）」が
        紛らわしいため、内部状態は ``_extension``（= 拡張子）と ``_stem``（= 拡張子を除いた
        ベース名）で持つ。``self._extension`` は常にドット付きで ``".xlsx"`` / ``".csv"`` 等。
        """
        return f"{self._stem}_{self._date.strftime(date_format)}{self._extension}"


def _resolve_date(value: date | datetime | None) -> date | datetime:
    """``for_date`` 引数を正規化する。``None`` のときは ``now()`` をそのまま返す
    （秒単位まで含めたフォーマットに対応するため ``date`` には丸めない）。
    """
    if value is None:
        return now()
    if isinstance(value, datetime):
        return value
    return value


def _split_suffix(name: str) -> tuple[str, str]:
    """ファイル名を ``stem`` と拡張子（``".xlsx"`` 等）に分ける。

    ``pathlib.Path`` の規則に従う:

    - ``"売上.xlsx"`` → ``("売上", ".xlsx")``
    - ``"売上"`` → ``FileSuffixMissingError``
    - ``"data.tar.gz"`` → ``("data.tar", ".gz")``（最後のドット以降を拡張子とみなす）
    - ``".hidden"`` → ``FileSuffixMissingError``（ドット始まりのファイル名は不可）

    Raises:
        FileSuffixMissingError: 拡張子が無いとき。
    """
    parsed = Path(name)
    extension = parsed.suffix
    if not extension:
        raise FileSuffixMissingError(name)
    return parsed.stem, extension
