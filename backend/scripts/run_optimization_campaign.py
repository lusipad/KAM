"""
运行 KAM 自治优化战役

作用：
- 自动创建至少 10 个优化任务
- 用现有自治系统逐个执行
- 根据失败结果动态强化后续策略提示
- 输出 JSON / Markdown 报告
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://localhost:8000/api"
POLL_INTERVAL_SECONDS = 5
TASK_TIMEOUT_SECONDS = 20 * 60


@dataclass
class OptimizationTaskSpec:
    title: str
    description: str
    success_criteria: str
    file_refs: list[str] = field(default_factory=list)


def build_task_specs() -> list[OptimizationTaskSpec]:
    return [
        OptimizationTaskSpec(
            title="README 自治快速上手补强",
            description="补一段清晰的自治会话快速上手说明，让新用户能在 3 分钟内理解如何创建会话、启动 dogfood、查看三项核心指标。",
            success_criteria="README 中新增自治快速上手段落，内容准确且不会破坏现有说明。",
            file_refs=["README.md", "docs/autonomy-v2.md"],
        ),
        OptimizationTaskSpec(
            title="架构文档补自治样本口径",
            description="把自主完成率、打断率、完成成功率的口径和适用边界写清楚，避免以后统计漂移。",
            success_criteria="system_architecture.md 中能明确说明三个指标的定义和分母口径。",
            file_refs=["system_architecture.md", "docs/autonomy-v2.md"],
        ),
        OptimizationTaskSpec(
            title="自治面板显示样本量提示",
            description="前端自治面板除了百分比，还要把样本量展示出来，避免看到一个 100% 却不知道只跑过 1 个会话。",
            success_criteria="自治面板可以看到核心指标对应的样本量提示，并通过现有前端检查。",
            file_refs=["app/src/components/Tasks/AutonomyPanel.tsx", "app/src/types/index.ts"],
        ),
        OptimizationTaskSpec(
            title="自治面板突出最近失败原因",
            description="如果最近一轮 cycle 失败，需要在自治面板上方直接露出失败摘要，不要让用户先翻开 accordion 才看到问题。",
            success_criteria="选中失败会话时，自治面板首屏可以直接看到最近失败摘要。",
            file_refs=["app/src/components/Tasks/AutonomyPanel.tsx"],
        ),
        OptimizationTaskSpec(
            title="E2E 覆盖自治标签页骨架",
            description="补一个最小的端到端检查，确保任务工作台存在自治标签页或对应空态，不要让后续重构把入口弄丢。",
            success_criteria="Playwright 用例能覆盖自治入口骨架，并通过 e2e。",
            file_refs=["app/e2e/app.spec.ts", "app/src/components/Tasks/TasksView.tsx"],
        ),
        OptimizationTaskSpec(
            title="后端自治指标补充失败检查摘要",
            description="指标接口除了比例，还要给出最常见失败检查标签，便于人快速判断系统到底卡在哪里。",
            success_criteria="自治指标接口能返回高频失败检查摘要，并有对应单测。",
            file_refs=["backend/app/api/autonomy.py", "backend/app/services/autonomy_service.py", "backend/tests/test_lite_core.py"],
        ),
        OptimizationTaskSpec(
            title="自治文档补操作手册",
            description="给 autonomy-v2 文档补一节操作手册，说明如何跑一轮 10 任务样本、怎么看达成率、什么时候该调整策略。",
            success_criteria="autonomy-v2 文档新增 operator playbook 段落，能指导实际操作。",
            file_refs=["docs/autonomy-v2.md"],
        ),
        OptimizationTaskSpec(
            title="Backlog 明确自治优化优先级",
            description="根据当前产品方向，把 backlog 里的自治改进项按优先级重排，不要和普通 UI polish 混在一起。",
            success_criteria="MVP_BACKLOG.md 中 Now/Next 能更清楚区分自治闭环与普通体验项。",
            file_refs=["MVP_BACKLOG.md", "docs/autonomy-v2.md"],
        ),
        OptimizationTaskSpec(
            title="README 补优化战役脚本说明",
            description="让 README 能说明如何直接运行优化战役脚本，产出报告文件在哪里，方便下一次 dogfood。",
            success_criteria="README 中新增优化战役脚本的运行方式和报告位置说明。",
            file_refs=["README.md", "backend/scripts/run_optimization_campaign.py"],
        ),
        OptimizationTaskSpec(
            title="自治单测补战役指标稳定性检查",
            description="补一条后端测试，确保完成率、打断率、成功率不会因为没有样本或只有失败样本而出现错误值。",
            success_criteria="后端新增指标稳定性测试，覆盖空样本或单边样本场景。",
            file_refs=["backend/tests/test_lite_core.py", "backend/app/services/autonomy_service.py"],
        ),
    ]


def build_default_checks() -> list[dict[str, str]]:
    return [
        {
            "label": "App lint",
            "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run lint",
        },
        {
            "label": "App build",
            "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run build",
        },
        {
            "label": "App e2e",
            "command": "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'app'); npm run test:e2e",
        },
        {
            "label": "Backend unit",
            "command": (
                "$python = Join-Path '{execution_cwd}' '.venv\\Scripts\\python.exe'; "
                "if (!(Test-Path $python)) { $python = Join-Path '{repo_path}' '.venv\\Scripts\\python.exe' }; "
                "Set-Location -LiteralPath (Join-Path '{execution_cwd}' 'backend'); "
                "if (Test-Path $python) { & $python -m unittest discover -s tests -v } else { py -m unittest discover -s tests -v }"
            ),
        },
    ]


def build_codex_command() -> str:
    return (
        "Get-Content -Raw \"{prompt_file}\" | "
        "codex exec --skip-git-repo-check --full-auto "
        "--model gpt-5.4 "
        "-c 'model_reasoning_effort=\"low\"' "
        "--output-last-message \"{run_dir}\\final.md\" "
        "-C \"{execution_cwd}\" -"
    )


def safe_slug(text: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")
    return slug or "campaign"


def pct(value: float) -> str:
    return f"{round(value * 100, 1)}%"


class CampaignRunner:
    def __init__(self, base_url: str, limit: int):
        self.client = httpx.Client(base_url=base_url, timeout=120)
        self.limit = limit
        self.campaign_id = f"campaign-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        self.started_at = datetime.now()
        self.task_specs = build_task_specs()[:limit]
        self.checks = build_default_checks()
        self.codex_command = build_codex_command()
        self.strategy_notes: list[str] = [
            "必须先阅读相关文件后再动手。",
            "修改完成后要主动运行全部检查，不要只输出结论。",
        ]
        self.results: list[dict[str, Any]] = []

    def run(self) -> dict[str, Any]:
        for index, spec in enumerate(self.task_specs, start=1):
            result = self._run_single_task(index, spec)
            self.results.append(result)
            self._adapt_strategy(result)

        finished_at = datetime.now()
        summary = self._build_summary(finished_at)
        report = {
            "campaignId": self.campaign_id,
            "startedAt": self.started_at.isoformat(),
            "finishedAt": finished_at.isoformat(),
            "summary": summary,
            "results": self.results,
        }
        self._write_report(report)
        return report

    def _run_single_task(self, index: int, spec: OptimizationTaskSpec) -> dict[str, Any]:
        objective = self._build_objective(spec)
        task = self._post(
            "/tasks",
            {
                "title": f"[{index:02d}] {spec.title}",
                "description": objective,
                "priority": "high" if index <= 3 else "medium",
                "metadata": {
                    "campaignId": self.campaign_id,
                    "taskIndex": index,
                },
            },
        )

        self._post(
            f"/tasks/{task['id']}/refs",
            {
                "type": "repo-path",
                "label": "KAM repo",
                "value": str(ROOT_DIR),
            },
        )
        for ref_path in spec.file_refs:
            self._post(
                f"/tasks/{task['id']}/refs",
                {
                    "type": "file",
                    "label": Path(ref_path).name,
                    "value": str(ROOT_DIR / ref_path),
                },
            )

        session_payload = {
            "title": f"{spec.title} / benchmark",
            "objective": objective,
            "repoPath": str(ROOT_DIR),
            "primaryAgentName": f"optimizer-{index:02d}",
            "primaryAgentType": "custom",
            "primaryAgentCommand": self.codex_command,
            "maxIterations": self._pick_iteration_budget(index),
            "successCriteria": f"{spec.success_criteria} 并且 App / Backend 检查全部通过。",
            "checkCommands": self.checks,
            "metadata": {
                "campaignId": self.campaign_id,
                "taskIndex": index,
                "strategyNotes": self.strategy_notes.copy(),
            },
        }
        session = self._post(f"/tasks/{task['id']}/autonomy/sessions", session_payload)
        self._post(f"/autonomy/sessions/{session['id']}/start", {})

        deadline = time.time() + TASK_TIMEOUT_SECONDS
        final_session = None
        while time.time() < deadline:
            current = self._get(f"/autonomy/sessions/{session['id']}")
            final_session = current
            if current["status"] in {"completed", "failed", "interrupted"}:
                break
            time.sleep(POLL_INTERVAL_SECONDS)

        timed_out = False
        if not final_session:
            final_session = self._get(f"/autonomy/sessions/{session['id']}")
        if final_session["status"] == "running":
            timed_out = True
            try:
                final_session = self._post(f"/autonomy/sessions/{session['id']}/interrupt", {})
            except Exception:
                final_session = self._get(f"/autonomy/sessions/{session['id']}")

        task_metrics = self._get(f"/tasks/{task['id']}/autonomy/metrics")
        latest_cycle = (final_session.get("cycles") or [None])[0]
        failed_checks = [
            item["label"]
            for cycle in final_session.get("cycles") or []
            for item in cycle.get("checkResults") or []
            if not item.get("passed")
        ]
        result = {
            "taskIndex": index,
            "taskId": task["id"],
            "title": spec.title,
            "status": final_session["status"],
            "timedOut": timed_out,
            "currentIteration": final_session["currentIteration"],
            "maxIterations": final_session["maxIterations"],
            "interruptionCount": final_session["interruptionCount"],
            "sessionId": final_session["id"],
            "latestCycleStatus": latest_cycle["status"] if latest_cycle else None,
            "latestFeedback": latest_cycle["feedbackSummary"] if latest_cycle else "",
            "failedChecks": failed_checks,
            "taskMetrics": task_metrics,
        }
        return result

    def _pick_iteration_budget(self, index: int) -> int:
        if len(self.results) < 2:
            return 2

        failed = sum(1 for item in self.results if item["status"] != "completed")
        failure_rate = failed / len(self.results)
        if failure_rate >= 0.5:
            return 3
        if index >= 8:
            return 3
        return 2

    def _build_objective(self, spec: OptimizationTaskSpec) -> str:
        notes = "\n".join(f"- {item}" for item in self.strategy_notes)
        refs = "\n".join(f"- {path}" for path in spec.file_refs) if spec.file_refs else "- 先自行定位相关文件"
        return (
            f"{spec.description}\n\n"
            f"建议关注文件：\n{refs}\n\n"
            f"执行策略：\n{notes}"
        )

    def _adapt_strategy(self, result: dict[str, Any]) -> None:
        if result["status"] == "completed":
            return

        failed_checks = result.get("failedChecks") or []
        if failed_checks:
            most_common = ", ".join(sorted(set(failed_checks)))
            self.strategy_notes.append(f"高频失败检查包括：{most_common}。提交前必须逐项复跑并确认通过。")

        latest_feedback = result.get("latestFeedback") or ""
        if latest_feedback:
            snippet = latest_feedback.strip().splitlines()[:6]
            text = " / ".join(line.strip() for line in snippet if line.strip())
            if text:
                self.strategy_notes.append(f"上一轮失败摘要：{text[:260]}")

        deduped: list[str] = []
        for note in self.strategy_notes:
            if note not in deduped:
                deduped.append(note)
        self.strategy_notes = deduped[-6:]

    def _build_summary(self, finished_at: datetime) -> dict[str, Any]:
        terminal = self.results
        completed = [item for item in terminal if item["status"] == "completed"]
        interrupted = [item for item in terminal if item["status"] == "interrupted"]
        failed = [item for item in terminal if item["status"] == "failed"]
        denominator = len(terminal) or 1
        failed_check_counter = Counter(check for item in terminal for check in item.get("failedChecks") or [])
        return {
            "totalTasks": len(terminal),
            "completedTasks": len(completed),
            "failedTasks": len(failed),
            "interruptedTasks": len(interrupted),
            "autonomyCompletionRate": len(completed) / denominator if terminal else 0,
            "interruptionRate": len(interrupted) / denominator if terminal else 0,
            "successRate": len(completed) / denominator if terminal else 0,
            "averageIterations": (
                sum(item["currentIteration"] for item in terminal) / len(terminal) if terminal else 0
            ),
            "topFailedChecks": failed_check_counter.most_common(5),
            "durationMinutes": round((finished_at - self.started_at).total_seconds() / 60, 2),
        }

    def _write_report(self, report: dict[str, Any]) -> None:
        output_dir = ROOT_DIR / "storage" / "campaigns" / self.campaign_id
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (output_dir / "report.md").write_text(self._render_markdown(report), encoding="utf-8")

    def _render_markdown(self, report: dict[str, Any]) -> str:
        summary = report["summary"]
        lines = [
            f"# Optimization Campaign {report['campaignId']}",
            "",
            f"- Started: {report['startedAt']}",
            f"- Finished: {report['finishedAt']}",
            f"- Total tasks: {summary['totalTasks']}",
            f"- Completed: {summary['completedTasks']}",
            f"- Failed: {summary['failedTasks']}",
            f"- Interrupted: {summary['interruptedTasks']}",
            f"- Autonomy completion rate: {pct(summary['autonomyCompletionRate'])}",
            f"- Interruption rate: {pct(summary['interruptionRate'])}",
            f"- Success rate: {pct(summary['successRate'])}",
            f"- Average iterations: {round(summary['averageIterations'], 2)}",
            "",
            "## Top Failed Checks",
        ]

        if summary["topFailedChecks"]:
            for label, count in summary["topFailedChecks"]:
                lines.append(f"- {label}: {count}")
        else:
            lines.append("- None")

        lines.extend(["", "## Task Results"])
        for item in report["results"]:
            lines.extend(
                [
                    f"### {item['taskIndex']:02d}. {item['title']}",
                    f"- Status: {item['status']}",
                    f"- Iterations: {item['currentIteration']}/{item['maxIterations']}",
                    f"- Timed out: {item['timedOut']}",
                    f"- Failed checks: {', '.join(item['failedChecks']) if item['failedChecks'] else 'None'}",
                ]
            )
            feedback = (item.get("latestFeedback") or "").strip()
            if feedback:
                lines.append("")
                lines.append("```text")
                lines.append(feedback[:4000])
                lines.append("```")
            lines.append("")
        return "\n".join(lines)

    def _get(self, path: str) -> dict[str, Any]:
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload)
        response.raise_for_status()
        return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 KAM 自治优化战役")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="KAM 后端 API 基地址")
    parser.add_argument("--limit", type=int, default=10, help="执行多少个任务，默认 10")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runner = CampaignRunner(base_url=args.base_url, limit=max(1, min(args.limit, len(build_task_specs()))))
    report = runner.run()
    summary = report["summary"]
    print(json.dumps(
        {
            "campaignId": report["campaignId"],
            "totalTasks": summary["totalTasks"],
            "completedTasks": summary["completedTasks"],
            "failedTasks": summary["failedTasks"],
            "interruptedTasks": summary["interruptedTasks"],
            "autonomyCompletionRate": summary["autonomyCompletionRate"],
            "interruptionRate": summary["interruptionRate"],
            "successRate": summary["successRate"],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
