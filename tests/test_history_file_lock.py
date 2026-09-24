"""``HistoryFileLock`` の排他と、後片付けの挙動を検証する。

ロック用ファイル（``.lock``）は ``with`` ブロックを抜けたときに削除される。
共有サーバー上に古い ``.lock`` が溜まらないこと、作業ツリーにも残骸が出ないことが
このテスト群で確認したい中核の挙動。テストは必ず ``tmp_path`` を使い、リポジトリ内
には一切ファイルを残さない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from comken.exceptions import HistoryLockTimeoutError
from comken.services.salesforce_downloader.history_file_lock import HistoryFileLock


def _acquire_or_fail(path: Path, timeout: float) -> None:
    """テスト用ヘルパー: ``timeout=0`` でロック取得を試み、失敗を確認する。

    pytest.raises のブロック内に直接 ``with`` をネストすると ruff の
    ``SIM117``（複数の ``with`` を 1 つにまとめる推奨）に当たるため、
    ロック取得の本体だけを関数に括り出してネストを浅くしている。
    統合すると ``HistoryFileLock.__exit__`` が二重に呼ばれる経路も
    できるため、意図的に分けている。
    """
    with HistoryFileLock(path, timeout=timeout):
        pytest.fail("timeout=0 では取得できないはず")


def _raise_inside_lock(path: Path) -> None:
    """テスト用ヘルパー: ロック取得中に例外を発生させ、ロック解放後の状態を見る。

    ``pytest.raises`` と ``HistoryFileLock`` を同じ ``with`` に統合すると
    ロック解放の ``__exit__`` が二重に呼ばれる経路ができるため、別関数に
    切り出している（ruff ``SIM117`` の回避策でもある）。
    """
    with HistoryFileLock(path):
        raise RuntimeError("テスト用の例外")


def test_lock_file_is_removed_after_with_block(tmp_path: Path) -> None:
    """``with`` ブロックを抜けた後、``.lock`` ファイルが残らないこと。"""
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("", encoding="utf-8-sig")
    lock_path = Path(f"{history_path}.lock")

    with HistoryFileLock(history_path):
        # ブロック内ではロック用ファイルが存在してよい（共有サーバー側で
        # 別プロセスが同じパスを掴むための前提）
        assert lock_path.exists()

    # 抜けた後は削除済み
    assert not lock_path.exists()


def test_lock_file_is_removed_after_timeout_then_release(tmp_path: Path) -> None:
    """1 つ目が保持中、2 つ目が ``timeout=0`` でタイムアウトし、
    1 つ目を解放した後、``.lock`` ファイルが残らないこと。

    1 つ目だけが自分自身のファイルを消すので、待機中の 2 つ目が誤って
    相手のファイルを消すレースは起こらない（自分の ``_file`` を
    持っているのが 1 つ目だけ）。
    """
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("", encoding="utf-8-sig")
    lock_path = Path(f"{history_path}.lock")

    with HistoryFileLock(history_path):
        # 1 つ目が保持している間に 2 つ目が ``timeout=0`` で 1 回試して失敗
        with pytest.raises(HistoryLockTimeoutError):
            _acquire_or_fail(history_path, timeout=0)

        # まだ 1 つ目が保持しているのでロック用ファイルは残っている
        assert lock_path.exists()

    # 1 つ目を抜けた後にロック用ファイルが消えていること
    assert not lock_path.exists()


def test_lock_file_is_removed_when_block_raises(tmp_path: Path) -> None:
    """``with`` ブロック内で例外が出ても、ロック用ファイルは削除されること。

    ロック解除 → ファイルクローズ → ロック用ファイル削除 の順なので、
    ``with`` の ``__exit__`` が例外を伝播させる場合でも後片付けが走る。
    """
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("", encoding="utf-8-sig")
    lock_path = Path(f"{history_path}.lock")

    with pytest.raises(RuntimeError, match="テスト用の例外"):
        _raise_inside_lock(history_path)

    assert not lock_path.exists()


def test_lock_file_is_not_created_when_target_missing(tmp_path: Path) -> None:
    """保護対象ファイルが無くても、ロック用ファイルは作られる（既存挙動）。"""
    history_path = tmp_path / "存在しない.csv"
    lock_path = Path(f"{history_path}.lock")

    with HistoryFileLock(history_path):
        assert lock_path.exists()

    assert not lock_path.exists()


def test_lock_release_runs_after_timeout_does_not_drop_foreign_lock(tmp_path: Path) -> None:
    """タイムアウトで ``__exit__`` を抜けたとき、自分のファイルだけ閉じ、
    ロック用ファイルは他プロセスが所有しているため削除しない。

    待機中にロック用ファイルを消してしまうと、他プロセスとの排他が
    成立しなくなる（消えた直後に別プロセスが新規ファイルを作ってロック
    取得 → 元のプロセスと並行に動く）。タイムアウト経路ではファイルを
    閉じただけで削除せず、本体（保持側）が ``__exit__`` を抜けた時に
    削除される。
    """
    history_path = tmp_path / "履歴.csv"
    history_path.write_text("", encoding="utf-8-sig")
    lock_path = Path(f"{history_path}.lock")

    # 1 つ目を保持した状態で ``__exit__`` を経由させない（手動で解放もしない）
    first = HistoryFileLock(history_path)
    first.__enter__()
    assert lock_path.exists()

    try:
        # 2 つ目は ``timeout=0`` で失敗する（ロック用ファイルを他プロセスが
        # 所有している想定だが、ここでは同じプロセス内でも同じ動作になる）
        with pytest.raises(HistoryLockTimeoutError):
            _acquire_or_fail(history_path, timeout=0)

        # ロック用ファイルは残っている（1 つ目が解放していないので当然）
        assert lock_path.exists()
    finally:
        # 1 つ目を解放
        first.__exit__(None, None, None)

    # 1 つ目が抜けた後に消える
    assert not lock_path.exists()
