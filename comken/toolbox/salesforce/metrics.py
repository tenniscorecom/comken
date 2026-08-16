"""comken/toolbox/salesforce/metrics.py — API 呼び出しの計測

「どのモジュールから何回 API を呼んだか」「リトライが何回起きたか」
「レポートが上限で切り捨てられたか」を貯めて、実行の最後にまとめて出す。

計測を1か所に集められるのは、API 呼び出しがすべて SalesforceBase._request() を
通るため。呼び出し元は component（"report" / "crud" / "query"）で区別する。

組織の 24 時間 API 消費量は、自前で数えるより Salesforce が返す
`Sforce-Limit-Info` ヘッダーの方が正確なので、そちらを併せて記録する。
"""

import csv
import logging
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from ...core.utils import now

logger = logging.getLogger(__name__)

CSV_HEADERS = (
    "日時",
    "組織",
    "呼び出し元",
    "呼び出し回数",
    "エラー回数",
    "リトライ回数",
    "合計秒数",
    "API消費量",
    "API上限",
    "切り捨てレポート",
)


class RetryReason:
    """リトライの理由。どれが多いかで対処が変わるため区別して数える。"""

    REAUTH = "再認証"  # 401。トークンが切れただけなので取り直せば直る
    SERVER_ERROR = "サーバーエラー"  # 5xx。Salesforce 側の一時的な不調
    RATE_LIMIT = "制限超過"  # API コール数の上限。設計を見直す合図


@dataclass
class ComponentStat:
    """呼び出し元ごとの集計。"""

    calls: int = 0
    errors: int = 0
    retries: int = 0
    seconds: float = 0.0


@dataclass(frozen=True)
class ApiUsage:
    """組織の 24 時間 API 消費量（Sforce-Limit-Info ヘッダーの値）。"""

    used: int
    limit: int


@dataclass
class ApiMetrics:
    """API 呼び出しの計測を貯める。

    使い方:
        metrics = ApiMetrics("sandbox")
        # …API を呼ぶ…
        metrics.log_summary()
        metrics.append_csv(Path("logs/salesforce_metrics.csv"))
    """

    org_name: str
    api_usage: ApiUsage | None = None
    truncated_reports: list[str] = field(default_factory=list)
    _by_component: dict[str, ComponentStat] = field(default_factory=dict)
    _retry_reasons: dict[str, int] = field(default_factory=dict)

    def record_call(self, component: str, elapsed_seconds: float, is_error: bool = False) -> None:
        """API 呼び出しを1件記録する。"""
        stat = self._stat(component)
        stat.calls += 1
        stat.seconds += elapsed_seconds
        if is_error:
            stat.errors += 1

    def record_retry(self, component: str, reason: str) -> None:
        """リトライを1件記録する。reason は RetryReason の値を渡す。"""
        self._stat(component).retries += 1
        self._retry_reasons[reason] = self._retry_reasons.get(reason, 0) + 1

    def record_truncated_report(self, report_id: str) -> None:
        """レポートが上限で切り捨てられたことを記録する。

        止めずに続けた場合（allow_truncated=True）でも記録は残す。
        あとから「どのレポートを SOQL へ移すか」を実測で決めるための材料になる。
        """
        if report_id not in self.truncated_reports:
            self.truncated_reports.append(report_id)

    def component_stats(self) -> dict[str, ComponentStat]:
        """呼び出し元別の集計を、読み取り用のコピーとして返す。"""
        return deepcopy(self._by_component)

    def retry_reason_counts(self) -> dict[str, int]:
        """リトライ理由別の回数を、読み取り用のコピーとして返す。"""
        return self._retry_reasons.copy()

    def update_api_usage(self, limit_info: str) -> None:
        """`Sforce-Limit-Info` ヘッダーの値から API 消費量を取り出して更新する。

        Args:
            limit_info: "api-usage=1234/15000" の形式。
                        解釈できない形式は無視する（計測のために本処理を止めない）。
        """
        for part in limit_info.split(","):
            key, _, value = part.strip().partition("=")
            if key != "api-usage":
                continue
            used, _, limit = value.partition("/")
            if used.isdigit() and limit.isdigit():
                self.api_usage = ApiUsage(used=int(used), limit=int(limit))
            return

    def log_summary(self) -> None:
        """集計結果を INFO ログに出す。実行の最後に1回呼ぶ。"""
        total_calls = sum(stat.calls for stat in self._by_component.values())
        logger.info("Salesforce API 集計（%s）: 合計 %d 回", self.org_name, total_calls)

        for component, stat in sorted(self._by_component.items()):
            logger.info(
                "  %s: %d 回 / エラー %d / リトライ %d / %.2f 秒",
                component,
                stat.calls,
                stat.errors,
                stat.retries,
                stat.seconds,
            )

        for reason, count in sorted(self._retry_reasons.items()):
            logger.info("  リトライ内訳 %s: %d 回", reason, count)

        if self.api_usage and self.api_usage.limit > 0:
            # 上限に対する割合が分かると「増やしてよいか」の判断ができる
            percentage = self.api_usage.used / self.api_usage.limit * 100
            logger.info(
                "  組織の API 消費量: %d / %d（%.1f%%）",
                self.api_usage.used,
                self.api_usage.limit,
                percentage,
            )

        if self.truncated_reports:
            logger.warning("  上限で切り捨てられたレポート: %s", "、".join(self.truncated_reports))

    def append_csv(self, path: str | Path) -> None:
        """集計結果を CSV に1行ずつ追記する（呼び出し元ごとに1行）。

        日ごとに追記していくと、API 消費量の推移と切り捨ての発生が追える。
        ファイルが無ければ見出し行から作る。
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        is_new_file = not path.exists()
        timestamp = now().strftime("%Y-%m-%d %H:%M:%S")
        truncated = "、".join(self.truncated_reports)

        # newline="" は csv モジュールの作法（Windows で空行が入るのを防ぐ）
        with path.open("a", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            if is_new_file:
                writer.writerow(CSV_HEADERS)
            for component, stat in sorted(self._by_component.items()):
                writer.writerow(
                    [
                        timestamp,
                        self.org_name,
                        component,
                        stat.calls,
                        stat.errors,
                        stat.retries,
                        f"{stat.seconds:.2f}",
                        self.api_usage.used if self.api_usage else "",
                        self.api_usage.limit if self.api_usage else "",
                        truncated,
                    ]
                )

    def _stat(self, component: str) -> ComponentStat:
        """呼び出し元ごとの集計を取り出す（無ければ作る）。"""
        return self._by_component.setdefault(component, ComponentStat())
