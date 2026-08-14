"""comken/salesforce/sites/__init__.py — 組織（サイト）ごとの Salesforce クライアント。

組織は My Domain の URL と認証情報が違うので、1組織につき1クラス・1インスタンスにする。
共通の操作（SOQL・CRUD・レポート・計測）は `SalesforceBase` が持っているので、
ここに書くのは**その組織でしか通じないもの**だけにする。

    from comken.salesforce.sites import Sandbox

    with Sandbox() as sf:
        rows = sf.案件一覧()

URL と認証情報のシステム名はクラス定数なので、呼び出し側は何も渡さなくてよい。
本番とテストで登録を切り替えるときだけシステム名を渡す:

    with Sandbox(prefix=config.SALESFORCE.CREDENTIAL_PREFIX) as sf:
        ...

client_id / client_secret は DPAPI から読む（`comken.credentials`）ので、
コードにも config.ini にも秘密の値は現れない。

組織を増やすときは、このフォルダにファイルを1つ足して `SalesforceBase` を継承する。

> [!warning] 組織名と URL は仮の値
> **このリポジトリは公開しているので、実際の組織名・URL を書かない。**
> `Sandbox` の `DOMAIN_URL` はダミーで、共有サーバーへ配置するときに
> 実際の値へ書き換える（`comken/run.py` の `example_libs.v0000` と同じ扱い）。
> 書き換えるのは各ファイルの `DOMAIN_URL`・`CREDENTIAL_PREFIX`・`REPORT_*` と、
> 組織名を出すならクラス名。**実名をこのリポジトリへ書き戻さないこと。**
"""

from .sandbox import Sandbox

__all__ = ["Sandbox"]
