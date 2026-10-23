# Access / Excel 資産の棚卸しスクリプト（Python）

既存の Access データベースと Excel ブック（VBA マクロ・Power Query・データ接続など）が何をしているかを洗い出すための Python スクリプトです。
フォルダを指定すると配下のファイルを再帰的に調べ、全体をまとめた `report.md` と、抽出したコード（VBA・M・SQL）のファイルを出力します。

## 調べる内容

| 対象 | 取得する内容 | 必要なもの |
|---|---|---|
| Excel（.xlsx .xlsm .xlsb .xls .xltm .xlam） | シート一覧（非表示も）・名前定義・データ接続・外部リンク・Power Query の M コード・VBA モジュール | `oletools`（Excel 本体は不要） |
| Access（.accdb .mdb） | テーブル（件数・列名）・リンクテーブルの接続先・クエリの種類と SQL・リレーション・フォーム／レポートのレコードソースとコードビハインド・マクロ・標準モジュール | `pywin32` と Access 本体 |

## 前提

- Windows、Python 3.10 以上
- `pip install oletools pywin32`
- Access の調査には Access 本体（またはランタイムではなく製品版）がインストールされていること

## 使い方

```
python office_inventory.py "調査したいフォルダ"
python office_inventory.py "調査したいフォルダ" -o 出力先フォルダ
python office_inventory.py "単体のファイル.accdb"
```

出力（既定は `inventory_out`）:

```
inventory_out/
├─ report.md              ← 全ファイルのまとめ（コード本文も含む）
├─ 000_売上集計/
│   ├─ vba/Module1.bas
│   └─ PowerQuery_Section1.m
└─ 001_顧客管理/
    ├─ queries/Q_月次集計.sql
    ├─ forms/F_顧客.txt
    ├─ reports/...
    ├─ macros/...
    └─ modules/...
```

## 安全面の配慮

- **元ファイルは書き換えない。** Excel はファイルを読むだけ。Access はコピーを一時フォルダに作ってから開く（Access は開くだけでファイルを更新することがあるため）。
- **Access のマクロ・VBA は実行しない。** `AutomationSecurity = 3`（強制無効）で開くので、AutoExec マクロや起動時のフォームのコードは動かない想定。ただしコードを含まない安全なマクロアクションまで止まるかは環境によるので、心配なら先に AutoExec の有無を確認すること。
- **データ本体は出力しない。** テーブルは名前・列名・件数だけ。
- **接続文字列のパスワードは伏せる。** `Password=` / `PWD=` の値は `***` に置き換える。ただしサーバー名・共有フォルダのパス・M コード内の URL などはそのまま出るので、外部に渡す前に `report.md` を目で確認すること。
- パスワード付きの Access ファイルは開けずにエラーとしてレポートに記録される。

## コード（office_inventory.py）

```python
"""既存の Access / Excel 資産を棚卸しする。

使い方:
    python office_inventory.py 調査フォルダ [-o 出力フォルダ]

Excel: シート・名前定義・データ接続・外部リンク・Power Query・VBA（Excel 本体は不要）
Access: テーブル・リンクテーブル・クエリ SQL・リレーション・フォーム・レポート・マクロ・モジュール
        （Access 本体が必要）
元ファイルは読むだけ。Access は一時フォルダのコピーを開く。
"""

from __future__ import annotations

import argparse
import base64
import io
import logging
import re
import shutil
import struct
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

import win32com.client
from oletools.olevba import VBA_Parser

logger = logging.getLogger(__name__)

EXCEL_EXTS = {".xlsx", ".xlsm", ".xlsb", ".xls", ".xltm", ".xlam"}
ACCESS_EXTS = {".accdb", ".mdb"}

NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
NS_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"

MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3

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

# (見出し, CurrentProject のコレクション名, SaveAsText の種類, 出力フォルダ)
ACCESS_OBJECTS = [
    ("フォーム", "AllForms", 2, "forms"),
    ("レポート", "AllReports", 3, "reports"),
    ("マクロ", "AllMacros", 4, "macros"),
    ("モジュール", "AllModules", 5, "modules"),
]


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


def safe_name(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def mask_secret(text: str) -> str:
    return re.sub(r"(?i)\b(password|pwd)=[^;]*", r"\1=***", text)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- Excel


def inspect_excel(path: Path, out_dir: Path) -> Report:
    report = Report(path, "Excel")
    # .xls は zip ではないので VBA だけ調べる
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            read_workbook_xml(zf, names, report)
            read_connections(zf, names, report)
            read_external_links(zf, names, report)
            read_power_query(zf, names, report, out_dir)
    read_vba(path, report, out_dir)
    return report


def read_workbook_xml(zf: zipfile.ZipFile, names: set[str], report: Report) -> None:
    # .xlsb は workbook.bin なのでここは読めない
    if "xl/workbook.xml" not in names:
        return
    root = ET.fromstring(zf.read("xl/workbook.xml"))
    for sheet in root.iter(f"{NS_MAIN}sheet"):
        state = sheet.get("state", "visible")
        report.add("シート", f"{sheet.get('name')}（{state}）")
    for defined in root.iter(f"{NS_MAIN}definedName"):
        report.add("名前定義", f"{defined.get('name')} = {defined.text}")


def read_connections(zf: zipfile.ZipFile, names: set[str], report: Report) -> None:
    if "xl/connections.xml" not in names:
        return
    root = ET.fromstring(zf.read("xl/connections.xml"))
    for conn in root.iter(f"{NS_MAIN}connection"):
        line = f"{conn.get('name')}（type={conn.get('type')}）"
        db = conn.find(f"{NS_MAIN}dbPr")
        if db is not None:
            line += f" 接続: {mask_secret(db.get('connection', ''))}"
            line += f" / コマンド: {db.get('command', '')}"
        report.add("データ接続", line)


def read_external_links(zf: zipfile.ZipFile, names: set[str], report: Report) -> None:
    for name in sorted(names):
        if not re.fullmatch(r"xl/externalLinks/_rels/externalLink\d+\.xml\.rels", name):
            continue
        root = ET.fromstring(zf.read(name))
        for rel in root.iter(f"{NS_REL}Relationship"):
            report.add("外部リンク", rel.get("Target", ""))


def read_power_query(
    zf: zipfile.ZipFile, names: set[str], report: Report, out_dir: Path
) -> None:
    # Power Query は customXml/itemN.xml の DataMashup 要素に base64 で入っている
    for name in sorted(names):
        if not re.fullmatch(r"customXml/item\d+\.xml", name):
            continue
        root = ET.fromstring(zf.read(name))
        if not root.tag.endswith("DataMashup") or not root.text:
            continue
        m_code = decode_data_mashup(root.text)
        write_text(out_dir / "PowerQuery_Section1.m", m_code)
        for query in re.findall(r'^shared\s+(#"[^"]+"|\w+)\s*=', m_code, re.MULTILINE):
            report.add("Power Query", query)
        report.add_code("Power Query（Section1.m）", "powerquery", m_code.strip())


def decode_data_mashup(text: str) -> str:
    # 先頭 4 バイトがバージョン、次の 4 バイトが続く zip（パッケージ）の長さ
    data = base64.b64decode(text)
    package_size = struct.unpack_from("<i", data, 4)[0]
    package = data[8 : 8 + package_size]
    with zipfile.ZipFile(io.BytesIO(package)) as pz:
        return pz.read("Formulas/Section1.m").decode("utf-8-sig")


def read_vba(path: Path, report: Report, out_dir: Path) -> None:
    parser = VBA_Parser(str(path))
    try:
        if not parser.detect_vba_macros():
            return
        for _, _, module_name, code in parser.extract_macros():
            body = "\n".join(
                line for line in code.splitlines() if not line.startswith("Attribute VB_")
            ).strip()
            if not body:
                continue
            write_text(out_dir / "vba" / safe_name(module_name), body)
            procs = re.findall(
                r"^\s*(?:Public\s+|Private\s+|Friend\s+)?(?:Static\s+)?"
                r"(?:Sub|Function|Property\s+\w+)\s+(\w+)",
                body,
                re.MULTILINE | re.IGNORECASE,
            )
            report.add(
                "VBA", f"{module_name}: {len(body.splitlines())}行 / {', '.join(procs) or '（プロシージャなし）'}"
            )
            report.add_code(f"VBA {module_name}", "vb", body)
    finally:
        parser.close()


# ---------------------------------------------------------------- Access


def inspect_access(path: Path, out_dir: Path) -> Report:
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
                read_queries(db, report, out_dir)
                read_relations(db, report)
                read_access_objects(app, report, out_dir)
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


def read_queries(db, report: Report, out_dir: Path) -> None:
    for qd in db.QueryDefs:
        # "~" 始まりはフォームやコンボボックスに埋め込まれた SQL
        if qd.Name.startswith("~"):
            continue
        kind = QUERY_TYPES.get(qd.Type, f"種類{qd.Type}")
        sql = qd.SQL.strip()
        report.add("クエリ", f"{qd.Name}（{kind}）")
        report.add_code(f"クエリ {qd.Name}（{kind}）", "sql", sql)
        write_text(out_dir / "queries" / f"{safe_name(qd.Name)}.sql", sql)


def read_relations(db, report: Report) -> None:
    for rel in db.Relations:
        if rel.Name.startswith("MSys"):
            continue
        pairs = ", ".join(f"{f.Name}={f.ForeignName}" for f in rel.Fields)
        report.add("リレーション", f"{rel.Table} → {rel.ForeignTable}（{pairs}）")


def read_access_objects(app, report: Report, out_dir: Path) -> None:
    for label, collection_name, object_type, folder in ACCESS_OBJECTS:
        collection = getattr(app.CurrentProject, collection_name)
        for i in range(collection.Count):
            name = collection.Item(i).Name
            dest = out_dir / folder / f"{safe_name(name)}.txt"
            dest.parent.mkdir(parents=True, exist_ok=True)
            app.SaveAsText(object_type, name, str(dest))
            text = read_saved_text(dest)
            dest.write_text(text, encoding="utf-8")

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
    parser.add_argument("-o", "--out", type=Path, default=Path("inventory_out"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    reports = []
    for i, path in enumerate(find_targets(args.target)):
        out_dir = args.out / f"{i:03d}_{safe_name(path.stem)}"
        is_access = path.suffix.lower() in ACCESS_EXTS
        logger.info("調査中: %s", path)
        try:
            report = inspect_access(path, out_dir) if is_access else inspect_excel(path, out_dir)
        except Exception as e:
            logger.exception("失敗: %s", path)
            report = Report(path, "Access" if is_access else "Excel", error=str(e))
        reports.append(report)

    write_report(reports, args.out / "report.md")
    logger.info("完了: %d ファイル → %s", len(reports), args.out / "report.md")


if __name__ == "__main__":
    main()
```

## 制限・既知の穴

- `.xlsb` はシート一覧・名前定義・データ接続が読めない（バイナリ形式のため）。VBA と Power Query は読める。
- `.xls` は VBA だけ。Power Query・接続を調べたい場合は Excel で `.xlsx` / `.xlsm` に保存し直してから実行する。
- Excel の VBA プロジェクトにパスワードがかかっていても oletools は中身を読めることが多いが、読めない場合はレポートに出ない。
- Access のフォームのレコードソースが長くて複数行に分かれている場合、先頭行しか拾わない（全文は `forms/*.txt` にある）。
- ワークシート上の数式（セルの関数）は調べていない。外部ブックを参照している数式は「外部リンク」に出る。
