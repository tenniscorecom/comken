"""comken/services/salesforce_downloader/contract.py — 契約の正。

soql-collector（書き手）とダウンローダー（読み手）の **両方が import する** 契約の
正をここに置く。両リポジトリはここを import して使う（手作業で同期しない）。

- **未完成の SOQL の印** — ``INCOMPLETE_MARKER_PREFIX`` / ``INCOMPLETE_MARKER``
  検知側は ``INCOMPLETE_MARKER_PREFIX`` を使い、書き手は ``INCOMPLETE_MARKER`` を
  SOQL の 1 行目に置く
- **列名の対応.csv の列** — ``COLUMN_NAMES_CSV_COLUMNS``
- **バイト単位の見本** — ``load_sample()`` で ``contract_samples/`` 配下の
  CSV / TXT を取り出す。SOQL が未完成だったときの下書きファイルと、
  「``列名の対応.csv`` の完成形」をバイト比較で検証するための正本

サンプルは ``importlib.resources`` 経由で読むため、 ``pyproject.toml`` の
``[tool.setuptools.package-data]`` に ``contract_samples/*`` を含めている。
``.gitattributes`` 側で見本ファイルに ``-text`` を当てて BOM・改行コードを
保ったままリポジトリへ入れている（``text=auto`` で CRLF/BOM が書き換わると
バイト比較が壊れるため）。

例（検知）:

    from comken.services.salesforce_downloader.contract import (
        INCOMPLETE_MARKER_PREFIX,
    )
    if soql_text.splitlines()[0].startswith(INCOMPLETE_MARKER_PREFIX):
        raise SoqlIncompleteError(soql_text)

例（書き手）: 下書き SOQL の 1 行目に置く

    from comken.services.salesforce_downloader.contract import INCOMPLETE_MARKER

    soql_text = INCOMPLETE_MARKER + "\n" + soql_body

例（バイト比較）: 「``列名の対応.csv`` の完成形」と同じバイトか検証する

    from comken.services.salesforce_downloader.contract import load_sample

    assert path.read_bytes() == load_sample("列名の対応.contract.csv")
"""

from importlib import resources

from comken.exceptions import ComkenFileNotFoundError

# 検知側が使う「未完成 SOQL」の印。先頭一致で検知する。
# soql-collector 側の ``INCOMPLETE_MARKER`` と同じ。変えるときは両方同時に。
INCOMPLETE_MARKER_PREFIX = "【未完成】"

# 書き手が SOQL の 1 行目に置く全文（検知側の ``INCOMPLETE_MARKER_PREFIX`` ＋本文）。
# 見本ファイル ``未完成のSOQL.contract.txt`` の 1 行目は ``INCOMPLETE_MARKER_PREFIX``
# で始まり、検知側の先頭一致でこの全文を検知する。
# （実物の見本は手書きの ``【未完成】ここから下を補ってください`` のように PREFIX
# だけで ``INCOMPLETE_MARKER`` の全文を含まない。接頭辞判定は ``INCOMPLETE_MARKER_PREFIX``
# 側で行うため、 サンプルと全文を一致させる必要はない）。
# soql-collector 側の ``INCOMPLETE_MARKER`` と同じ。変えるときは両方同時に。
INCOMPLETE_MARKER = (
    INCOMPLETE_MARKER_PREFIX + "作れなかった部分があります。このままでは実行できません。"
)

# ``列名の対応.csv`` の列。順序は出力ファイルそのものなので、追加・並び替えは
# 全プロジェクトの既存 ``列名の対応.csv`` を読む処理へ影響する（互換性ポリシーに従う）。
# soql-collector 側の ``COLUMN_NAMES_COLUMNS`` と同じ。変えるときは両方同時に。
COLUMN_NAMES_CSV_COLUMNS: tuple[str, ...] = (
    "主オブジェクト",
    "SOQL列名",
    "表示名",
    "備考",
    "更新日",
)

# 見本を置くパッケージ相対ディレクトリ名。 ``importlib.resources.files()`` に渡す。
_CONTRACT_SAMPLES_PACKAGE = "comken.services.salesforce_downloader.contract_samples"


def load_sample(name: str) -> bytes:
    """``contract_samples/`` 配下の見本を返す。バイト比較用の正本。

    Args:
        name: ファイル名（例 ``「列名の対応.contract.csv」`` /
            ``「未完成のSOQL.contract.txt」``）。

    Returns:
        ファイルの生バイト。 BOM と改行コードはそのまま返す
        （``importlib.resources`` はテキストとして読み替えない）。

    Examples:
        >>> from comken.services.salesforce_downloader.contract import load_sample
        >>> load_sample("列名の対応.contract.csv").startswith(b"\xef\xbb\xbf")
        True
    """
    try:
        return resources.files(_CONTRACT_SAMPLES_PACKAGE).joinpath(name).read_bytes()
    except OSError as exc:  # FileNotFoundError / IsADirectoryError は OSError のサブクラス
        # 利用可能な名前をメッセージに並べる（comken の流儀: メッセージに「どうすればよいか」）。
        available = sorted(
            entry.name for entry in resources.files(_CONTRACT_SAMPLES_PACKAGE).iterdir()
        )
        available_str = "、".join(available) if available else "（なし）"
        raise ComkenFileNotFoundError(
            what=f"契約の見本 {name!r}",
            path=f"{_CONTRACT_SAMPLES_PACKAGE}/{name}",
            hint=(
                f"利用可能な名前: {available_str}\n"
                "このパッケージに含まれる見本は comken の package-data に列挙されている"
                "（pyproject.toml の [tool.setuptools.package-data]）。\n"
                "インストール形態（eggs / wheel / ソース）を確認してください。"
            ),
        ) from exc


__all__ = [
    "COLUMN_NAMES_CSV_COLUMNS",
    "INCOMPLETE_MARKER",
    "INCOMPLETE_MARKER_PREFIX",
    "load_sample",
]
