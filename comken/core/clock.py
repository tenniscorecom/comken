"""comken/core/clock.py — 現在のローカル日時を取得するユーティリティ。

タイムゾーンが必要なのは「今の時刻を取るとき」だけ。
業務で扱う日付（CSV に書かれた日付、ファイル名に入っている日付、帳票の日付）は
「その日」を表すただの日付であり、時刻もタイムゾーンも持たない。
これらは datetime.date のまま扱い、タイムゾーンを付けようとしないこと。
"""

import datetime


def now() -> datetime.datetime:
    """タイムゾーン付きの現在時刻（この PC のローカル時刻）を返す。"""
    # NOTE: Windows のオフライン環境で追加の tzdata を要求しないよう ZoneInfo は使わない。
    return datetime.datetime.now(datetime.UTC).astimezone()


def today() -> datetime.date:
    """この PC のローカルの今日の日付を返す。"""
    return now().date()
