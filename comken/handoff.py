r"""comken/handoff.py — 別のプロジェクトや人が置いたファイルを受け取る場所。

**取得を1つのプロジェクトにまとめ、使う側は置かれたファイルを読むだけ**にするための
薄い層。使う側は取得のしかた（Salesforce・ブラウザ・メール添付）を知らない。

    受け渡しフォルダ（\\server\share\受け渡し）
        売上レポート_20260814.csv     ← 取得担当プロジェクトが置く
        在庫レポート_20260814.csv     ← 取得に失敗したら、人が手で置く
            ↓  Handoff(FOLDER).require("売上レポート", "在庫レポート")
    使う側（取得の成否も手段も知らない）

**取得が落ちても、人が同じ場所へ同じ名前で置けば使う側はそのまま動く。** 取得と利用を
分ける一番の利点がこれで、夜間に取得が失敗しても、朝に手で置けば後続は待たずに進める。
「途中から動かす」ための特別な仕組みは要らない——**あるかどうかだけが条件**になる。

日付はファイル名に入れる（フォルダを日付で切らない）。前日のファイルが残っていても
名前が違うので、古いデータで黙って動くことがない。

配り先が決まっている場合（既存の RPA が特定の場所を見ている等）は、
**受け渡しフォルダへ集約してから配る**2段にする。配り先を変えずに済み、
「どのファイルがどこへ行くか」は config.ini の対応表1つに集まる。
→ examples/salesforce_handoff/
"""

import datetime
from pathlib import Path

from .exceptions import HandoffFilesMissingError
from .utils.clock import today

# ファイル名に入れる日付の形。FileFinder.today() の既定と合わせる
DATE_FORMAT = "%Y%m%d"

__all__ = ["Handoff"]


class Handoff:
    """受け渡しフォルダから、その日のファイルを受け取る。

    ファイル名は「名前_日付.拡張子」の形に固定する（例: 売上レポート_20260814.csv）。
    置く側と受け取る側で名前の作り方が違うと、置いたのに見つからないという
    分かりにくい失敗になるため、組み立てはこのクラスだけが行う。

    使い方:
        handoff = Handoff(r"\\\\server\\share\\受け渡し")

        # 使う側: 揃っているか確かめて受け取る（足りなければ止まる）
        files = handoff.require("売上レポート", "在庫レポート")
        rows = CsvReader(files["売上レポート"]).read_rows()

        # 取得側: もう取れているものは取り直さない
        if handoff.find("売上レポート") is None:
            download_to(handoff.path_of("売上レポート"))

    Args:
        folder: 受け渡しフォルダ。共有サーバー上の1か所を指す。
        date: 受け取る日付。省略すると今日。
        suffix: ファイルの拡張子。拡張子が混ざるなら Handoff を分けて作る。
    """

    def __init__(
        self,
        folder: str | Path,
        date: datetime.date | None = None,
        suffix: str = ".csv",
    ) -> None:
        self._folder = Path(folder)
        self._date = date or today()
        self._suffix = suffix

    @property
    def folder(self) -> Path:
        """受け渡しフォルダ。案内やログに出すために公開する。"""
        return self._folder

    def path_of(self, name: str) -> Path:
        """その名前のファイルが置かれるべきパスを返す（実際にあるかは見ない）。

        置く側がこれを保存先に使い、受け取る側が同じ規則で探す。

        Args:
            name: ファイルの名前（日付と拡張子は付けない。例: "売上レポート"）。
        """
        return self._folder / f"{name}_{self._date.strftime(DATE_FORMAT)}{self._suffix}"

    def find(self, name: str) -> Path | None:
        """置かれていればパスを返し、無ければ None を返す。

        取得側が「もう取れているか」を確かめて、取り直しを省くのに使う。
        """
        path = self.path_of(name)
        return path if path.is_file() else None

    def missing(self, *names: str) -> list[str]:
        """置かれていない名前を、渡した順で返す。"""
        return [name for name in names if self.find(name) is None]

    def require(self, *names: str) -> dict[str, Path]:
        """全部揃っていることを確かめて、名前とパスの対応を返す。

        1件目で止めずに**足りないものを全部集めて**から失敗させる。1件ずつ
        知らせると、置く人は「1つ置いて再実行」を人数分繰り返すことになる。

        Args:
            *names: 必要なファイルの名前（日付と拡張子は付けない）。

        Returns:
            {名前: パス} の対応。渡した順を保つ。

        Raises:
            HandoffFilesMissingError: 1件でも置かれていない場合。
                足りないファイル名と置き場所がメッセージに入る。
        """
        missing = self.missing(*names)
        if missing:
            raise HandoffFilesMissingError(
                self._folder, [self.path_of(name).name for name in missing]
            )
        return {name: self.path_of(name) for name in names}
