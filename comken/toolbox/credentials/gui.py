"""comken/toolbox/credentials/gui.py — 認証情報の登録画面（GUI）

    python -m comken cred gui

tkinter（Python 標準ライブラリ）製。ターミナルを使わない人向けの入口で、
コマンドでできること（登録・取り込み・一覧・削除）を1つの画面にまとめたもの。
平文 JSON もこの画面から選んで取り込めるので、登録の作業はここだけで済む。

**登録した値を読み出す機能は載せない。** 画面に出せば覗き見やスクリーンショットで
漏れる経路が増える。登録できたかどうかは、キー名の一覧と文字数で確かめられる。
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from comken.exceptions import CredentialError, CredentialNotFoundError
from comken.toolbox.credentials.importer import credential_name, import_json
from comken.toolbox.credentials.store import (
    CREDENTIAL_NAME_PATTERN,
    CREDENTIALS_PATH,
    delete_credential,
    list_names,
    load_credential,
    save_credential,
)

# 入力中の値を隠す文字。伏せ字にしておき、確認したいときだけ表示に切り替える
_MASK_CHARACTER = "●"


def build_credential_name(system: str, field: str) -> tuple[str | None, str | None]:
    """フォームの入力を検証して、保存に使うキー名を組み立てる。

    例外ではなくメッセージを返す。画面にそのまま出す文章なので、
    「何がどう間違っているか」を書ける場所を1か所にまとめたい。

    Args:
        system: システム名の入力欄の値（例: "site_a"）。
        field: 項目名の入力欄の値（例: "client_secret"）。

    Returns:
        (キー名, None): 入力が正しい場合。
        (None, エラーメッセージ): 入力に問題がある場合。
    """
    system = system.strip()  # コピペで前後に空白が入ることが多い
    field = field.strip()
    if not system:
        return None, "システム名を入力してください（例: site_a）。"
    if not CREDENTIAL_NAME_PATTERN.fullmatch(system):
        return None, "システム名に使えるのは半角英数字とアンダースコアだけです（例: site_a）。"
    if not field:
        return None, "項目名を入力してください（例: client_id / client_secret / password）。"
    if not CREDENTIAL_NAME_PATTERN.fullmatch(field):
        return None, "項目名に使えるのは半角英数字とアンダースコアだけです（例: client_id）。"
    return credential_name(system, field), None


class CredentialsApp:
    """認証情報の登録画面。

    左: 登録済みキー名の一覧（値は表示しない）と、選んだキーの削除
    右: 手入力での登録フォームと、平文 JSON の取り込み
    下: 保存先のパスと、直前の操作の結果
    """

    def __init__(self, root: tk.Tk, path: Path | None = None) -> None:
        """
        Args:
            root: 画面を載せるウィンドウ。
            path: 保存先ファイル。省略時は CREDENTIALS_PATH（通常は省略する）。
        """
        self.root = root
        self._path = path
        root.title("comken 認証情報の登録")
        root.geometry("640x420")
        root.minsize(560, 380)

        self._build_widgets()
        self._refresh()

    # --------------------------------------------------------- 画面の組み立て
    def _build_widgets(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        # ── 左: 登録済み一覧 ──
        left = ttk.LabelFrame(main, text="登録済みのキー名", padding=8)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.listbox = tk.Listbox(left, exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True)

        ttk.Label(left, text="値は表示されません（登録できたかの確認用）").pack(
            anchor=tk.W, pady=(4, 0)
        )
        ttk.Button(left, text="選択したキーを削除", command=self._on_delete).pack(
            anchor=tk.W, pady=(8, 0)
        )

        # ── 右: 登録フォーム ──
        right = ttk.Frame(main, padding=(12, 0, 0, 0))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(right, text="登録（同じキー名なら上書き）", padding=8)
        form.pack(fill=tk.X)

        ttk.Label(form, text="システム名（例: site_a）").pack(anchor=tk.W)
        self.system_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.system_var).pack(fill=tk.X, pady=(0, 6))

        ttk.Label(form, text="項目名（例: client_id / client_secret）").pack(anchor=tk.W)
        self.field_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.field_var).pack(fill=tk.X, pady=(0, 6))

        ttk.Label(form, text="値").pack(anchor=tk.W)
        self.value_var = tk.StringVar()
        self.value_entry = ttk.Entry(form, textvariable=self.value_var, show=_MASK_CHARACTER)
        self.value_entry.pack(fill=tk.X)

        self.show_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form,
            text="値を表示する（貼り間違いの確認用）",
            variable=self.show_var,
            command=self._on_toggle_show,
        ).pack(anchor=tk.W, pady=(2, 6))

        ttk.Button(form, text="登録する", command=self._on_save).pack(anchor=tk.E)

        # ── 右下: JSON の取り込み ──
        importer = ttk.LabelFrame(right, text="まとめて取り込む", padding=8)
        importer.pack(fill=tk.X, pady=(12, 0))

        ttk.Label(
            importer,
            text="同じ値を何台にも配るときは、平文 JSON を選んでまとめて登録します。",
            wraplength=280,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(0, 6))
        ttk.Button(importer, text="JSON を選んで取り込む…", command=self._on_import_json).pack(
            anchor=tk.W
        )

        # ── ステータスバー ──
        self.status_var = tk.StringVar(value=f"保存先: {self._path or CREDENTIALS_PATH}")
        ttk.Label(self.root, textvariable=self.status_var, padding=(12, 4)).pack(
            side=tk.BOTTOM, anchor=tk.W
        )

    # ------------------------------------------------------------- 表示の更新
    def _refresh(self) -> None:
        """登録済みキー名の一覧を最新にする。"""
        self.listbox.delete(0, tk.END)
        for name in list_names(self._path):
            self.listbox.insert(tk.END, name)

    def _status(self, message: str) -> None:
        self.status_var.set(message)

    # --------------------------------------------------------- イベント処理
    def _on_toggle_show(self) -> None:
        self.value_entry.config(show="" if self.show_var.get() else _MASK_CHARACTER)

    def _on_save(self) -> None:
        """フォームの1件を保存し、読み直して文字数を出す。"""
        name, error = build_credential_name(self.system_var.get(), self.field_var.get())
        if error:
            messagebox.showwarning("入力を確認してください", error, parent=self.root)
            return

        value = self.value_var.get()
        if not value:
            messagebox.showwarning("入力を確認してください", "値が空です。", parent=self.root)
            return

        if name in list_names(self._path) and not messagebox.askyesno(
            "上書きの確認", f"{name} は登録済みです。上書きしますか？", parent=self.root
        ):
            return

        try:
            save_credential(name, value, self._path)
            # 読み直せることまで確かめる。桁数を出せば、貼り間違いはここで気づける
            length = len(load_credential(name, self._path))
        except CredentialError as e:
            messagebox.showerror("登録できませんでした", str(e), parent=self.root)
            return

        self.value_var.set("")
        self._refresh()
        self._status(f"登録しました: {name}（{length} 文字）")

    def _on_delete(self) -> None:
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo(
                "削除", "左の一覧から削除するキーを選んでください。", parent=self.root
            )
            return
        name = self.listbox.get(selection[0])

        if not messagebox.askyesno(
            "削除の確認", f"{name} を削除します。よろしいですか？", parent=self.root
        ):
            return

        try:
            delete_credential(name, self._path)
        except CredentialNotFoundError:
            pass  # 一覧を開いたあとに消えていた場合。_refresh で表示が揃う
        except CredentialError as e:
            messagebox.showerror("削除できませんでした", str(e), parent=self.root)
            return
        self._refresh()
        self._status(f"削除しました: {name}")

    def _on_import_json(self) -> None:
        """平文 JSON を選んでまとめて取り込む（コマンドの import と同じ）。"""
        selected = filedialog.askopenfilename(
            parent=self.root,
            title="取り込む JSON を選ぶ",
            filetypes=[("JSON ファイル", "*.json"), ("すべてのファイル", "*.*")],
        )
        if not selected:
            return

        json_path = Path(selected)
        try:
            names = import_json(json_path, self._path)
        except CredentialError as e:
            messagebox.showerror("取り込めませんでした", str(e), parent=self.root)
            return

        self._refresh()
        self._status(f"{len(names)} 件を取り込みました。")
        self._offer_source_deletion(json_path, names)

    def _offer_source_deletion(self, json_path: Path, names: list[str]) -> None:
        """読み直せたときだけ、平文 JSON の削除を勧める。

        読み直せていれば、この実行アカウントで復号できることが確かめられている。
        確かめる前に消すと、登録時と別のアカウントだった場合に元の値を失う
        （DPAPI は「登録したユーザー × PC」でしか復号できない）。
        """
        try:
            for name in names:
                load_credential(name, self._path)
        except CredentialError:
            messagebox.showwarning(
                "平文の JSON は残します",
                "取り込んだ値を読み直せませんでした。\n"
                f"平文の JSON は消さずに残します: {json_path}",
                parent=self.root,
            )
            return

        if not messagebox.askyesno(
            "平文の JSON を削除しますか？",
            f"{len(names)} 件すべてを読み直せました。平文の JSON は不要です。\n\n{json_path}",
            parent=self.root,
        ):
            self._status(f"平文の JSON が残っています: {json_path}")
            return

        try:
            json_path.unlink()
        except OSError as e:
            # 取り込みは成功しているので失敗扱いにはせず、消し忘れだけ伝える
            messagebox.showwarning(
                "削除できませんでした",
                f"平文の JSON を削除できませんでした（{e}）。手で削除してください。",
                parent=self.root,
            )
            return
        self._status(f"平文の JSON を削除しました: {json_path}")


def main() -> None:
    """登録画面を開く（閉じるまで戻らない）。"""
    root = tk.Tk()
    CredentialsApp(root)
    root.mainloop()
