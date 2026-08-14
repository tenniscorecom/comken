"""comken/exceptions/settings.py — comken 自身の設定（settings.ini）の例外。

プロジェクトの config.ini（config.py の例外）とは別物。settings.ini は
**comken を共有サーバーへ配置する人が1回だけ書く**もの。
"""

from pathlib import Path

from .base import ComkenError


class SettingsError(ComkenError):
    """comken の設定（settings.ini）に関するエラー

    対処:
        画面に表示された具体的なエラー名を上の表から探す
    """


class SettingsCreatedFromExampleError(SettingsError):
    """settings.ini が無かったので、example から作った

    **仮の値のまま動かさないために、作った時点で止める。** 共有フォルダのパスなどが
    仮名のままだと、つながらないか、誰も見ない場所を読みに行くことになる。

    発生箇所: comken.settings の読み込み

    対処:
        作られた settings.ini を開き、社内の実際の値へ書き換えてから、もう一度実行する。
        settings.ini は git 管理外なので、comken を更新（git pull）しても消えない
    """

    def __init__(self, path: Path, created: bool) -> None:
        if created:
            super().__init__(
                f"settings.ini が無かったので、example から作成しました: {path}\n"
                "中の値（共有フォルダの場所など）を実際のものへ書き換えてから、"
                "もう一度実行してください。"
            )
        else:
            super().__init__(
                f"settings.ini がありません: {path}\n"
                "雛形（settings.ini.example）も見つかりませんでした。"
                "comken の配置が正しいか確認してください。"
            )


class SettingsSectionNotFoundError(SettingsError):
    """settings.ini に必要なセクションが無い

    発生箇所: comken.settings.get()

    対処:
        settings.ini.example と見比べて、足りないセクションを書き足す
    """

    def __init__(self, section: str, existing: list[str], path: Path) -> None:
        known = "、".join(existing) or "（セクションなし）"
        super().__init__(
            f"settings.ini に [{section}] がありません: {path}\n"
            f"今あるセクション: {known}\n"
            "settings.ini.example と見比べて書き足してください。"
        )


class SettingsKeyNotFoundError(SettingsError):
    """settings.ini に必要なキーが無い

    発生箇所: comken.settings.get()

    対処:
        settings.ini.example と見比べて、足りないキーを書き足す
    """

    def __init__(self, section: str, key: str, existing: list[str], path: Path) -> None:
        known = "、".join(existing) or "（キーなし）"
        super().__init__(
            f"settings.ini の [{section}] に {key} がありません: {path}\n"
            f"今あるキー: {known}\n"
            "settings.ini.example と見比べて書き足してください。"
        )
