from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import settings  # noqa: E402


@dataclass(frozen=True)
class AgentReadinessResult:
    agent: str
    ok: bool
    binary: str
    command: list[str]
    message: str
    detail: str | None = None


def _resolve_binary(executable: str) -> str:
    candidate = Path(executable)
    if candidate.is_file():
        return str(candidate)

    if sys.platform.startswith("win") and not candidate.suffix:
        for suffix in (".cmd", ".exe", ".bat"):
            resolved = shutil.which(f"{executable}{suffix}")
            if resolved:
                return resolved

    return shutil.which(executable) or executable


def _agent_spec(agent: str) -> tuple[str, list[str], str, str]:
    normalized = agent.strip().lower()
    if normalized == "codex":
        configured = settings.codex_path
        return (
            configured,
            ["login", "status"],
            "默认真实 agent smoke 需要可用的 codex 命令。",
            "默认真实 agent smoke 需要可用的 codex 登录态。",
        )
    if normalized == "claude-code":
        configured = settings.claude_code_path
        return (
            configured,
            ["auth", "status"],
            "真实 agent smoke 需要可用的 claude-code 命令。",
            "真实 agent smoke 需要可用的 claude-code 登录态。",
        )
    raise ValueError(f"unsupported_agent:{agent}")


def check_agent_readiness(agent: str) -> AgentReadinessResult:
    executable, args, missing_message, not_ready_message = _agent_spec(agent)
    binary = _resolve_binary(executable)
    command = [binary, *args]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return AgentReadinessResult(
            agent=agent,
            ok=False,
            binary=binary,
            command=command,
            message=f"{missing_message} 若当前只想跑快速本地回归，请显式传入 -SkipRealAgentSmoke。",
            detail=f"missing binary: {binary}",
        )

    detail = (completed.stderr or completed.stdout or "").strip() or None
    if completed.returncode == 0:
        return AgentReadinessResult(
            agent=agent,
            ok=True,
            binary=binary,
            command=command,
            message=f"{agent} readiness check passed.",
            detail=detail,
        )

    return AgentReadinessResult(
        agent=agent,
        ok=False,
        binary=binary,
        command=command,
        message=f"{not_ready_message} 若当前只想跑快速本地回归，请显式传入 -SkipRealAgentSmoke。",
        detail=detail,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check whether a real-agent smoke target is ready.")
    parser.add_argument("--agent", choices=("codex", "claude-code"), required=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    result = check_agent_readiness(args.agent)
    if not args.quiet:
        print(result.message)
        if result.detail:
            print(result.detail)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
