"""comken/exceptions/config.py — 設定ファイルと認証情報の保存に関する例外。"""

from pathlib import Path

from comken.exceptions.base import ComkenError

_MAX_MATCH_DISTANCE = 1


_MAX_MATCH_COUNT = 2


def damerau_levenshtein_distance(left: str, right: str) -> int:
    """2 文字列の Damerau-Levenshtein 距離を返す。

    隣り合う 2 文字の入れ替わりを 1 回の編集として数える。標準ライブラリには
    同じ機能がないため、ここで小さな動的計画法を実装する。
    """
    if len(left) < len(right):
        left, right = right, left

    previous_previous_row = [0] * (len(right) + 1)
    previous_row = list(range(len(right) + 1))

    for left_index, left_character in enumerate(left, start=1):
        current_row = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            insertion = current_row[right_index - 1] + 1
            deletion = previous_row[right_index] + 1
            replacement = previous_row[right_index - 1] + (left_character != right_character)
            current_row.append(min(insertion, deletion, replacement))

            if (
                left_index > 1
                and right_index > 1
                and left[left_index - 1] == right[right_index - 2]
                and left[left_index - 2] == right[right_index - 1]
            ):
                current_row[-1] = min(
                    current_row[-1],
                    previous_previous_row[right_index - 2] + 1,
                )

        previous_previous_row, previous_row = previous_row, current_row

    return previous_row[-1]


def find_close_names(
    name: str,
    existing: list[str],
    max_count: int = _MAX_MATCH_COUNT,
) -> list[str]:
    """既存名から近い名前を距離順で最大 ``max_count`` 件返す。

    編集距離が 1 以下の名前だけを選び、同じ距離なら ``existing`` の並び順を守る。
    文字列長に依存する類似比率は、長い名前で別物まで拾うため使わない。
    """
    if not existing or max_count <= 0:
        return []

    candidates = sorted(
        (
            (index, damerau_levenshtein_distance(name, candidate), candidate)
            for index, candidate in enumerate(existing)
        ),
        key=lambda item: (item[1], item[0]),
    )
    return [
        candidate for _index, distance, candidate in candidates if distance <= _MAX_MATCH_DISTANCE
    ][:max_count]


class ConfigError(ComkenError):
    """config.ini に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


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


def _suggest_close_matches(name: str, existing: list[str]) -> list[str]:
    """名前に対して既存候補から近いものを最大2件まで返す。"""
    return find_close_names(name, existing)


class CredentialError(ComkenError):
    """認証情報の保存・取得に関するエラー。具体的な状況はメッセージに出る

    対処:
        メッセージに書かれた対処に従う。直らなければ画面全体のスクリーンショットを管理者へ
    """


class CredentialNotFoundError(CredentialError):
    """認証情報（パスワード・client_secret など）が登録されていない

    発生箇所: comken.toolbox.credentials の load_credential() / Credentials の属性アクセス

    対処:
        表示された登録済みキー名と見比べる。
        無ければ `python -m comken cred import 認証情報.json` で取り込む
    """

    def __init__(self, name: str, registered: list[str]) -> None:
        known = "\n".join(f"  {item}" for item in registered)
        detail = (
            f"登録済みのキー名:\n{known}"
            if registered
            else "まだ1件も登録されていません。次のコマンドで取り込んでください。\n"
            "  python -m comken cred import 認証情報.json"
        )
        super().__init__(f"認証情報が登録されていません: {name}\n{detail}")


class PasswordRejectedError(CredentialError):
    """サイト側が新しいパスワードを拒否した（記号が足りない・文字数が足りない等）

    サイト固有の画面クラス（例: ``ChangePasswordPage.submit_new_password()``）が、
    パスワード送信後にサイト側のエラー表示を検知した場合に送出する。
    ``comken.toolbox.credentials.change_password()`` はこの例外を受け取ると、
    理由を表示して新しいパスワードを CLI で受け付け直す
    （``max_attempts`` に達するまで自動で再試行する）。

    発生箇所: 利用プロジェクト側のパスワード変更画面クラス（サイト固有の実装）

    対処:
        表示されたエラー内容（サイト側の拒否理由）を確認し、要件を満たす
        パスワードを入力し直す
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"サイト側が新しいパスワードを拒否しました: {reason}")
