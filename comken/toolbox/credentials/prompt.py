"""comken/toolbox/credentials/prompt.py — 新しいパスワードをCLIから受け付けて保存する

ブラウザ自動化でサイト側からパスワード変更を強制されたとき、CLIで新しい
パスワードを2回入力させて一致を確かめ、そのまま DPAPI 認証情報ストアへ保存する
（呼び出し側で save() を別途呼ぶ必要はない）。

    from comken.toolbox.credentials import Credentials, prompt_new_password

    cred = Credentials(config.CREDENTIALS.AMS)
    new_password = prompt_new_password(cred)                 # CLI受付→DPAPI保存までここで完結
    change_password_page.submit_new_password(new_password)   # サイト側へは別途反映

サイト側が新しいパスワードを拒否しうる（記号が足りない等）場合は、
呼び出し側で再試行ループを書かせずに済む ``change_password()`` を使う。
サイト固有の画面クラスが ``PasswordRejectedError`` を送出するようにしておけば、
拒否のたびに自動でCLIへ戻って聞き直す（再試行させたくなければ
``max_attempts=1`` を指定する）。

    from comken.toolbox.credentials import Credentials, change_password

    cred = Credentials(config.CREDENTIALS.AMS)
    secure = change_password(cred, change_password_page.submit_new_password)

無人実行（RPAのスケジュール実行等）では対話入力できないため、
timeout_seconds を過ぎても入力が確定しなければ TimeoutError で失敗する
（入力待ちのままハングし続けない）。
"""

# 対話的にパスワードを受け付けるモジュールのため、プロンプト表示・マスク文字の
# 表示に print を使う（logging はログファイル向けで、対話プロンプトの
# 相手には届かない）
# ruff: noqa: T201

import logging
import msvcrt
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

from comken.exceptions import PasswordRejectedError

if TYPE_CHECKING:
    from comken.toolbox.credentials.store import Credentials

logger = logging.getLogger(__name__)

# submit() の戻り値（change_password() が呼び出し側へそのまま返す型）
_T = TypeVar("_T")

# Credentials に保存する項目名の既定値。パスワード以外を受け付けたいときだけ
# 呼び出し側で field を指定する。
DEFAULT_PASSWORD_FIELD = "password"
# 入力待ちの上限秒数の既定値。無人実行でハングし続けないための上限で、
# 人が使う分には十分長い値にしてある。
DEFAULT_TIMEOUT_SECONDS = 300.0
# change_password() がサイト側の拒否に対して自動で聞き直す既定の最大回数。
DEFAULT_MAX_ATTEMPTS = 3

_ENTER_CHARS = ("\r", "\n")
_BACKSPACE = "\x08"
_INTERRUPT = "\x03"

_EMPTY_MESSAGE = "空のパスワードは登録できません。もう一度入力してください。"
_MISMATCH_MESSAGE = "入力が一致しませんでした。もう一度入力してください。"


def prompt_new_password(
    cred: "Credentials",
    field: str = DEFAULT_PASSWORD_FIELD,
    *,
    label: str = "新しいパスワード",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """新しいパスワードをCLIから2回入力させ、一致したら cred へ保存して返す。

    入力文字は画面に表示しない。1回目と2回目が食い違う間、または未入力の間は
    確定させず何度でも聞き直す。timeout_seconds 以内に入力が確定しなければ
    TimeoutError にする（無人実行でハングし続けるのを防ぐ）。

    確定した値は ``cred.<field> = 値`` の形で代入し、その場で ``cred.save()``
    まで行う。ログイン時に読む側（``cred.password`` 等）と同じインスタンスを
    渡すことで、site 名を書き直す必要がない（typo で別サイトへ保存される
    事故を防ぐ）。

    Args:
        cred: 保存先。``Credentials(config.CREDENTIALS.<サイト>)`` で作ったもの。
        field: 保存する項目名。既定は ``"password"``。
        label: プロンプトに表示する項目名（表示用で、保存先の項目名とは独立）。
        timeout_seconds: 入力待ちの上限秒数。既定 300 秒（5分）。

    Returns:
        2回とも一致した入力値（保存済み）。

    Raises:
        TimeoutError: timeout_seconds 以内に入力が確定しなかった場合。
    """
    new_value = _prompt_confirmed(label, timeout_seconds)
    setattr(cred, field, new_value)
    cred.save()
    logger.debug("新しい値を Credentials へ保存しました: field=%s", field)
    return new_value


def change_password(
    cred: "Credentials",
    submit: Callable[[str], _T],
    field: str = DEFAULT_PASSWORD_FIELD,
    *,
    label: str = "新しいパスワード",
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> _T:
    """新しいパスワードをCLIから受け付け、``submit()`` でサイトへ送信する。

    サイト側が拒否した場合（記号が足りない・文字数が足りない等）は、
    自動でCLIへ戻って聞き直す。呼び出し側のプロジェクトで再試行ループを
    書く必要はない。

    ``submit`` はサイト固有の画面クラスのメソッド（例:
    ``change_password_page.submit_new_password``）を渡す。サイト側が
    拒否したことを検知したら ``PasswordRejectedError`` を送出する実装に
    しておくこと（検知の方法はサイトごとに違うため、ここでは決められない
    ――画面クラス側の責務にする）。

    再試行させたくない場合は ``max_attempts=1`` を指定する（1回失敗したら
    ``PasswordRejectedError`` をそのまま呼び出し側へ返す）。

    DPAPI への保存（``cred.save()``）は ``submit()`` が成功した後にだけ行う。
    サイト側に拒否された値を DPAPI へ残さないため（読む側とサイト側の
    パスワードがずれる事故を防ぐ）。

    Args:
        cred: 保存先。``Credentials(config.CREDENTIALS.<サイト>)`` で作ったもの。
        submit: 新しいパスワードを受け取ってサイトへ送信する関数。サイトが
            拒否した場合は ``PasswordRejectedError`` を送出すること。
        field: 保存する項目名。既定は ``"password"``。
        label: プロンプトに表示する項目名。
        timeout_seconds: 1回あたりの入力待ちの上限秒数（聞き直すたびにリセットされる）。
        max_attempts: 最大試行回数。既定3回。1にすると再試行しない。

    Returns:
        ``submit()`` の戻り値（通常はサイト側の遷移先の画面インスタンス）。

    Raises:
        ValueError: ``max_attempts`` が1未満の場合。
        TimeoutError: 入力待ちがタイムアウトした場合。
        PasswordRejectedError: ``max_attempts`` 回すべてサイト側に拒否された場合。
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts は1以上にしてください: {max_attempts}")
    attempt = 1
    while True:
        new_value = _prompt_confirmed(label, timeout_seconds)
        try:
            result = submit(new_value)
        except PasswordRejectedError as e:
            logger.debug("サイト側がパスワードを拒否しました: attempt=%d/%d", attempt, max_attempts)
            if attempt >= max_attempts:
                raise
            print(e)
            print(f"もう一度入力してください（{attempt}/{max_attempts}回目が拒否されました）。")
            attempt += 1
            continue
        setattr(cred, field, new_value)
        cred.save()
        logger.debug("新しい値をサイト・Credentials の両方へ反映しました: field=%s", field)
        return result


def _prompt_confirmed(label: str, timeout_seconds: float) -> str:
    """1回目と2回目が一致するまで、未入力・不一致のたびに聞き直す。"""
    while True:
        first = _read_masked(f"{label}: ", timeout_seconds)
        if not first:
            print(_EMPTY_MESSAGE)
            continue
        second = _read_masked(f"{label}（確認のため再入力）: ", timeout_seconds)
        if first != second:
            print(_MISMATCH_MESSAGE)
            continue
        return first


def _read_masked(prompt: str, timeout_seconds: float) -> str:
    """マスク付きでコンソール入力を受け付ける。timeout_seconds を過ぎたら TimeoutError。

    ``getpass.getpass()`` はタイムアウトできないため、Windows専用の msvcrt で
    1文字ずつ読みながら経過時間を見る形にしている。RPAのスケジュール実行など
    人がいない環境で誤って走らせても、入力待ちのまま延々ハングし続けない
    （対話利用時の見た目・挙動は getpass と変わらない）。
    """
    print(prompt, end="", flush=True)
    buffer: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    while True:
        if msvcrt.kbhit():
            char = msvcrt.getwch()
            if char in _ENTER_CHARS:
                print()
                return "".join(buffer)
            if char == _BACKSPACE:
                if buffer:
                    buffer.pop()
                    print("\b \b", end="", flush=True)
                continue
            if char == _INTERRUPT:
                raise KeyboardInterrupt
            buffer.append(char)
            print("*", end="", flush=True)
        if time.monotonic() >= deadline:
            print()
            raise TimeoutError(
                f"{timeout_seconds:.0f}秒以内に入力がありませんでした"
                "（無人実行では対話入力を待てません）"
            )
        time.sleep(0.05)
