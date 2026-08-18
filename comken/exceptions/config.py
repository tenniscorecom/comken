"""comken/exceptions/config.py — 設定ファイルに関する例外。"""

import difflib
from pathlib import Path

from comken.exceptions.base import ComkenError


class ConfigError(ComkenError):
    """config.ini に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class ConfigFileNotFoundError(ConfigError):
    """config.ini が見つからない

    発生箇所: Config.__init__() / generate_stub()

    対処:
        config.ini.example が同じ場所にあるか確認する（あれば実行し直すだけで作られる）
    """

    def __init__(self, path: Path | str) -> None:
        # config.ini.example があれば ConfigCreatedFromExampleError の側へ行く。
        # ここへ来たということは example も無いので、「コピーして作る」は案内できない
        super().__init__(
            f"config.ini が見つかりません: {path}\n"
            "同じ場所に config.ini.example があるか確認してください。"
            "あれば、もう一度実行するだけで config.ini が作られます。"
        )


class ConfigCreatedFromExampleError(ConfigError):
    """config.ini が無かったので example から作った

    発生箇所: Config.__init__()

    対処:
        作られた config.ini の値を書き換えて、もう一度実行する
    """

    def __init__(self, path: Path | str) -> None:
        super().__init__(
            f"config.ini が無かったので、config.ini.example から作成しました: {path}\n"
            "中の値（フォルダの場所など）を確認して書き換えてから、もう一度実行してください。"
        )


class ConfigLowerCaseNameError(ConfigError):
    """config.ini のセクション名・キー名に小文字がある

    発生箇所: Config.__init__()

    対処:
        表示された名前を大文字に書き換える（`[files]` → `[FILES]`）
    """

    def __init__(self, path: Path | str, wrong: list[str]) -> None:
        super().__init__(
            f"config.ini のセクション名とキー名は大文字で書いてください: {path}\n"
            + "\n".join(f"  {item}" for item in wrong)
        )


def _suggest_close_matches(name: str, existing: list[str]) -> list[str]:
    """名前に対して既存候補から近いものを最大2件まで返す。

    difflib.get_close_matches は候補が短いと似た判定が緩くなるため、
    cutoff は 0.7 程度にする（1 文字違いのタイポは拾いたいが、
    ``FILE`` と ``FILSE`` が両方候補にあるときに ``FILES`` だけを
    教えるためのバランス）。
    """
    if not existing:
        return []
    return difflib.get_close_matches(name, existing, n=2, cutoff=0.7)


class ConfigSectionNotFoundError(ConfigError):
    """config.ini の必要な節がない

    発生箇所: Config.__getattr__()

    対処:
        メッセージに表示された **「読んだファイル」のパス** が、編集している
        config.ini と一致するかを確認する（2026-08-18 にプロジェクトの場所を
        基準にするように変えてから、起動方法によって別の config.ini を読む
        ことがあるため）。パスが正しければ、表示されたセクション名を
        config.ini に追加する。**見た目では原因が分からない場合**（行頭に
        空白が混入していた等）は ``python -m comken config --check`` で
        構造上の問題点を指摘してもらえる
    """

    def __init__(self, name: str, existing: list[str], path: Path | str | None = None) -> None:
        # 2026-08-18 に「プロジェクトのフォルダ基準」に変える前は path を出さなくて
        # よかった。変えた後は「利用者が見ている config.ini」と違う場所を
        # 読んでいることがある（例: `python src/run.py` で起動すると src/ 配下を
        # 探しに行く）。だから path を必ず添えて、利用者が diff を取れるようにする。
        # path は configparser 等の挙動確認用に None を許容するが、内部利用では
        # 必ず Config が知っている _path を渡す。
        location = f"\n読んだファイル: {path}" if path is not None else ""
        # 防いでいる事故: セクション名を 1 文字タイポすると「セクションがありません」
        # とだけ出て、近い名前（FILE と FILES のように 1 文字違い）が目視で
        # 並んでいるのにも気付けない。difflib.get_close_matches で候補を出し、
        # 「もしかして」を添える。候補が無ければ何も足さない（誤誘導しない）。
        suggestion = _suggest_close_matches(name, existing)
        suggestion_line = f"\nもしかして: [{suggestion[0]}]" if len(suggestion) == 1 else ""
        if len(suggestion) >= 2:
            suggestion_line = f"\nもしかして: [{suggestion[0]}], [{suggestion[1]}]"
        super().__init__(
            f"config.ini に [{name}] セクションがありません。{location}\n"
            f"存在するセクション: {existing}{suggestion_line}\n"
            "セクション名の綴りと、config.ini に定義されているかを確認してください。"
        )


class ConfigKeyNotFoundError(ConfigError, AttributeError):
    """config.ini のセクションに必要なキーがない

    発生箇所: Config 内の SimpleNamespace への属性アクセス

    対処:
        メッセージに表示された **「読んだファイル」のパス** が、編集している
        config.ini と一致するかを確認する。パスが正しければ、表示された
        キー名を該当セクションへ追加する。**セクション名は合っているが
        キー名を 1 文字タイポした** とき（FILES.OUTPUT_FOLER 等）は、
        「もしかして」に近いキー名が出るので、それを config.ini に書き直す
    """

    def __init__(
        self,
        section: str,
        name: str,
        existing: list[str],
        path: Path | str | None = None,
    ) -> None:
        # セクション名エラーと同じ理屈で「読んだファイル」を添える。
        # キー名エラーはタイポ由来のことが大半なので、候補は常時計算する。
        location = f"\n読んだファイル: {path}" if path is not None else ""
        suggestion = _suggest_close_matches(name, existing)
        suggestion_line = f"\nもしかして: {suggestion[0]}" if len(suggestion) == 1 else ""
        if len(suggestion) >= 2:
            suggestion_line = f"\nもしかして: {suggestion[0]}, {suggestion[1]}"
        super().__init__(
            f"config.ini の [{section}] セクションに {name} キーがありません。{location}\n"
            f"存在するキー: {existing}{suggestion_line}\n"
            "キー名の綴りと、config.ini に定義されているかを確認してください。"
        )


class ConfigRequiredKeysMissingError(ConfigError):
    """config.ini に必須の項目がない

    対処:
        エラーに表示された項目を config.ini へ追加する
    """

    def __init__(self, missing: list[str], path: Path) -> None:
        items = "\n".join(f"  - {name}" for name in missing)
        super().__init__(
            f"config.ini に必要な項目がありません。\n{items}\n"
            f"このファイルへ追加してください: {path}"
        )
