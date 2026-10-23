# Access / Excel 資産の棚卸しスクリプト（Python）

既存の Access データベースと Excel ブック（VBA マクロ・Power Query・データ接続など）が何をしているかを洗い出すための Python スクリプトです。
フォルダを指定すると配下のファイルを再帰的に調べ、結果を **Markdown 1つ**（既定は `inventory.md`）にまとめて出力します。VBA・M・SQL のコード本文もその中に入ります。

**追加のパッケージは不要。** 標準ライブラリと pywin32（comken で既に使用）だけで動きます。Excel・Access は COM で操作します。

## 調べる内容

| 対象 | 取得する内容 |
|---|---|
| Excel（.xlsx .xlsm .xlsb .xls .xltm .xlam） | シート一覧（非表示も）・名前定義・データ接続・外部リンク・Power Query の M コード・VBA モジュール |
| Access（.accdb .mdb） | テーブル（件数・列名）・リンクテーブルの接続先・クエリの種類と SQL・リレーション・フォーム／レポートのレコードソースとコードビハインド・マクロ・標準モジュール |

## 前提

- Windows、Python 3.10 以上、pywin32
- Excel・Access の製品版がインストールされていること（調べる種類の分だけ）
- Power Query の取得は Excel 2016 以降
- **VBA を読むには Excel の設定が必要**: [ファイル] → [オプション] → [トラスト センター] → [トラスト センターの設定] → [マクロの設定] → 「VBA プロジェクト オブジェクト モデルへのアクセスを信頼する」にチェック。オフのままでも他の項目は調べられ、VBA だけ「読めない」とレポートに出る。

## 使い方

```
python office_inventory.py "調査したいフォルダ"
python office_inventory.py "調査したいフォルダ" -o 出力ファイル.md
python office_inventory.py "単体のファイル.accdb"
```

出力は `inventory.md` 1つだけ（`-o` で変更可）。ファイルごとに見出しが分かれ、一覧のあとにコード本文が続きます。

## 安全面の配慮

- **元ファイルは書き換えない。** Excel は読み取り専用で開き、保存せずに閉じる。Access はコピーを一時フォルダに作ってから開く（Access は開くだけでファイルを更新することがあるため）。
- **マクロ・VBA は実行しない。** Excel・Access とも `AutomationSecurity = 3`（強制無効）で開くので、Workbook_Open や AutoExec は動かない想定。Excel はイベントも止め、外部リンクの更新もしない。
- **パスワード付きのファイルで止まらない。** 入力画面を出さずにエラーとしてレポートに記録する。
- **データ本体は出力しない。** テーブルは名前・列名・件数だけ。
- **接続文字列のパスワードは伏せる。** `Password=` / `PWD=` の値は `***` に置き換える。ただしサーバー名・共有フォルダのパス・M コード内の URL などはそのまま出るので、外部に渡す前に出力した Markdown を目で確認すること。

## コード（office_inventory.py）

```python
"""既存の Access / Excel 資産を棚卸しする。

使い方:
    python office_inventory.py 調査フォルダ [-o 出力ファイル.md]

Excel: シート・名前定義・データ接続・外部リンク・Power Query・VBA
Access: テーブル・リンクテーブル・クエリ SQL・リレーション・フォーム・レポート・マクロ・モジュール
どちらも COM で開く（pywin32 のみ使用）。元ファイルは書き換えない。結果は Markdown 1つにまとめる。
"""

from __future__ import annotations

import argparse
import logging
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import win32com.client

logger = logging.getLogger(__name__)

EXCEL_EXTS = {".xlsx", ".xlsm", ".xlsb", ".xls", ".xltm", ".xlam"}
ACCESS_EXTS = {".accdb", ".mdb"}

MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3
XL_EXCEL_LINKS = 1
# パスワード付きブックで入力画面を出さずに失敗させるためのダミー
# （パスワード無しのブックでは無視される）
DUMMY_PASSWORD = "__no_password__"

SHEET_VISIBILITY = {-1: "表示", 0: "非表示", 2: "完全非表示"}
CONNECTION_TYPES = {
    1: "OLEDB",
    2: "ODBC",
    3: "XML",
    4: "テキスト",
    5: "Web",
    7: "ワークシート",
    8: "データモデル",
}
# VBComponent.Type
VBA_COMPONENT_TYPES = {
    1: "標準モジュール",
    2: "クラスモジュール",
    3: "ユーザーフォーム",
    100: "シート／ブック",
}

# DAO の QueryDef.Type
QUERY_TYPES = {
    0: "選択",
    16: "クロス集計",
    32: "削除",
    48: "更新",
    64: "追加",
    80: "テーブル作成",
    96: "データ定義",
    112: "パススルー",
    128: "ユニオン",
}

# (見出し, CurrentProject のコレクション名, SaveAsText の種類)
ACCESS_OBJECTS = [
    ("フォーム", "AllForms", 2),
    ("レポート", "AllReports", 3),
    ("マクロ", "AllMacros", 4),
    ("モジュール", "AllModules", 5),
]

PROCEDURE_PATTERN = re.compile(
    r"^\s*(?:Public\s+|Private\s+|Friend\s+)?(?:Static\s+)?"
    r"(?:Sub|Function|Property\s+\w+)\s+(\w+)",
    re.MULTILINE | re.IGNORECASE,
)


@dataclass
class Report:
    path: Path
    kind: str
    sections: dict[str, list[str]] = field(default_factory=dict)
    codes: list[tuple[str, str, str]] = field(default_factory=list)
    error: str = ""

    def add(self, section: str, line: str) -> None:
        self.sections.setdefault(section, []).append(line)

    def add_code(self, title: str, lang: str, code: str) -> None:
        self.codes.append((title, lang, code))


def mask_secret(text: str) -> str:
    return re.sub(r"(?i)\b(password|pwd)=[^;]*", r"\1=***", text)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def is_access(path: Path) -> bool:
    return path.suffix.lower() in ACCESS_EXTS


# ---------------------------------------------------------------- Excel


def start_excel():
    excel = win32com.client.DispatchEx("Excel.Application")
    excel.Visible = False
    excel.DisplayAlerts = False
    excel.AskToUpdateLinks = False
    excel.EnableEvents = False
    excel.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
    return excel


def inspect_excel(excel, path: Path) -> Report:
    report = Report(path, "Excel")
    wb = excel.Workbooks.Open(
        str(path),
        UpdateLinks=0,
        ReadOnly=True,
        Password=DUMMY_PASSWORD,
        IgnoreReadOnlyRecommended=True,
        AddToMru=False,
    )
    try:
        read_sheets(wb, report)
        read_names(wb, report)
        read_connections(wb, report)
        read_external_links(wb, report)
        read_power_query(wb, report)
        read_vba(wb, report)
    finally:
        wb.Close(SaveChanges=False)
    return report


def read_sheets(wb, report: Report) -> None:
    for sheet in wb.Sheets:
        visibility = SHEET_VISIBILITY.get(sheet.Visible, str(sheet.Visible))
        report.add("シート", f"{sheet.Name}（{visibility}）")


def read_names(wb, report: Report) -> None:
    for name in wb.Names:
        hidden = "" if name.Visible else "（非表示）"
        report.add("名前定義", f"{name.Name}{hidden} = {name.RefersTo}")


def read_connections(wb, report: Report) -> None:
    for conn in wb.Connections:
        kind = CONNECTION_TYPES.get(conn.Type, f"種類{conn.Type}")
        line = f"{conn.Name}（{kind}）"
        detail = {1: "OLEDBConnection", 2: "ODBCConnection"}.get(conn.Type)
        if detail:
            source = getattr(conn, detail)
            line += f" 接続: {mask_secret(str(source.Connection))}"
            line += f" / コマンド: {source.CommandText}"
        report.add("データ接続", line)


def read_external_links(wb, report: Report) -> None:
    for link in wb.LinkSources(XL_EXCEL_LINKS) or ():
        report.add("外部リンク", link)


def read_power_query(wb, report: Report) -> None:
    for query in wb.Queries:
        report.add("Power Query", query.Name)
        report.add_code(f"Power Query {query.Name}", "powerquery", query.Formula.strip())


def read_vba(wb, report: Report) -> None:
    if not wb.HasVBProject:
        return
    try:
        project = wb.VBProject
    except Exception:
        report.add(
            "VBA",
            "読めない（「VBA プロジェクト オブジェクト モデルへのアクセスを信頼する」が無効）",
        )
        return
    if project.Protection == 1:
        report.add("VBA", "パスワードでロックされていて読めない")
        return

    for comp in project.VBComponents:
        module = comp.CodeModule
        if module.CountOfLines == 0:
            continue
        code = module.Lines(1, module.CountOfLines).strip()
        if not code:
            continue
        kind = VBA_COMPONENT_TYPES.get(comp.Type, f"種類{comp.Type}")
        procs = ", ".join(PROCEDURE_PATTERN.findall(code)) or "（プロシージャなし）"
        report.add("VBA", f"{comp.Name}（{kind}）: {len(code.splitlines())}行 / {procs}")
        report.add_code(f"VBA {comp.Name}（{kind}）", "vb", code)


# ---------------------------------------------------------------- Access


def inspect_access(path: Path) -> Report:
    report = Report(path, "Access")
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / path.name
        shutil.copy2(path, copy)
        app = win32com.client.DispatchEx("Access.Application")
        try:
            app.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
            app.OpenCurrentDatabase(str(copy))
            try:
                db = app.CurrentDb()
                read_tables(db, report)
                read_queries(db, report)
                read_relations(db, report)
                read_access_objects(app, report, Path(tmp))
            finally:
                app.CloseCurrentDatabase()
        finally:
            app.Quit()
    return report


def read_tables(db, report: Report) -> None:
    for td in db.TableDefs:
        name = td.Name
        if name.startswith(("MSys", "USys", "~")):
            continue
        if td.Connect:
            report.add(
                "リンクテーブル", f"{name} → {mask_secret(td.Connect)} / {td.SourceTableName}"
            )
        else:
            columns = ", ".join(f.Name for f in td.Fields)
            report.add("テーブル", f"{name}（{td.RecordCount}件）: {columns}")


def read_queries(db, report: Report) -> None:
    for qd in db.QueryDefs:
        # "~" 始まりはフォームやコンボボックスに埋め込まれた SQL
        if qd.Name.startswith("~"):
            continue
        kind = QUERY_TYPES.get(qd.Type, f"種類{qd.Type}")
        sql = qd.SQL.strip()
        report.add("クエリ", f"{qd.Name}（{kind}）")
        report.add_code(f"クエリ {qd.Name}（{kind}）", "sql", sql)


def read_relations(db, report: Report) -> None:
    for rel in db.Relations:
        if rel.Name.startswith("MSys"):
            continue
        pairs = ", ".join(f"{f.Name}={f.ForeignName}" for f in rel.Fields)
        report.add("リレーション", f"{rel.Table} → {rel.ForeignTable}（{pairs}）")


def read_access_objects(app, report: Report, work_dir: Path) -> None:
    # SaveAsText はファイルにしか書き出せないので、作業フォルダに出して読んだら消す
    dest = work_dir / "object.txt"
    for label, collection_name, object_type in ACCESS_OBJECTS:
        collection = getattr(app.CurrentProject, collection_name)
        for i in range(collection.Count):
            name = collection.Item(i).Name
            app.SaveAsText(object_type, name, str(dest))
            text = read_saved_text(dest)
            dest.unlink()

            if label in ("フォーム", "レポート"):
                summarize_form(label, name, text, report)
            else:
                report.add(label, name)
                report.add_code(f"{label} {name}", "vb", text.strip())


def read_saved_text(path: Path) -> str:
    # SaveAsText はフォーム等を UTF-16、モジュールを ANSI(cp932) で書き出す
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe"):
        return raw.decode("utf-16")
    return raw.decode("cp932", errors="replace")


def summarize_form(label: str, name: str, text: str, report: Report) -> None:
    source = re.search(r'^\s*RecordSource\s*=\s*"(.*)"', text, re.MULTILINE)
    report.add(label, f"{name}: レコードソース={source.group(1) if source else '（なし）'}")
    _, found, code = text.partition("CodeBehindForm")
    if found and code.strip():
        body = "\n".join(
            line for line in code.splitlines() if not line.startswith("Attribute VB_")
        ).strip()
        report.add_code(f"{label} {name} のコード", "vb", body)


# ---------------------------------------------------------------- 出力


def write_report(reports: list[Report], path: Path) -> None:
    lines = ["# Access / Excel 棚卸しレポート", ""]
    for r in reports:
        lines += [f"## {r.path.name}（{r.kind}）", "", f"- パス: `{r.path}`", ""]
        if r.error:
            lines += [f"**読み取りエラー**: {r.error}", ""]
        for section, items in r.sections.items():
            lines += [f"### {section}（{len(items)}件）", ""]
            lines += [f"- {item}" for item in items]
            lines.append("")
        for title, lang, code in r.codes:
            lines += [f"#### {title}", "", f"````{lang}", code, "````", ""]
    write_text(path, "\n".join(lines))


def find_targets(target: Path) -> list[Path]:
    candidates = [target] if target.is_file() else target.rglob("*")
    return sorted(
        p
        for p in candidates
        if p.suffix.lower() in EXCEL_EXTS | ACCESS_EXTS and not p.name.startswith("~$")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Access / Excel 資産を棚卸しする")
    parser.add_argument("target", type=Path, help="調査するフォルダまたはファイル")
    parser.add_argument("-o", "--out", type=Path, default=Path("inventory.md"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    targets = find_targets(args.target)
    excel = start_excel() if not all(is_access(p) for p in targets) else None
    reports = []
    try:
        for path in targets:
            kind = "Access" if is_access(path) else "Excel"
            logger.info("調査中: %s", path)
            try:
                report = inspect_access(path) if kind == "Access" else inspect_excel(excel, path)
            except Exception as e:
                logger.exception("失敗: %s", path)
                report = Report(path, kind, error=str(e))
            reports.append(report)
    finally:
        if excel is not None:
            excel.Quit()

    write_report(reports, args.out)
    logger.info("完了: %d ファイル → %s", len(reports), args.out)


if __name__ == "__main__":
    main()
```

## 制限・既知の穴

- Excel の VBA は上記のトラストセンター設定が必要。VBA プロジェクトにパスワードがかかっている場合は読めない。
- Access のフォームのレコードソースが長くて複数行に分かれている場合、先頭行しか拾わない。
- ワークシート上の数式（セルの関数）は調べていない。外部ブックを参照している数式は「外部リンク」に出る。
- 1 ファイルの途中で失敗すると、そのファイルはエラーだけが記録される（途中まで取れた内容は残らない）。
