from __future__ import annotations

from typing import Any

import httpx

from config import settings


class CIAdapter:
    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        provider = config.get("provider", "github_actions")
        if provider != "github_actions":
            return {"items": [], "meta": {"error": f"unsupported_provider:{provider}"}}

        if not settings.github_token:
            return {"items": [], "meta": {"error": "missing_github_token"}}

        repo = config["repo"]
        owner, name = repo.split("/", 1)
        branch = config.get("branch")
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        }
        params = {"per_page": 20}
        if branch:
            params["branch"] = branch

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{owner}/{name}/actions/runs",
                headers=headers,
                params=params,
            )
            response.raise_for_status()
            runs = response.json().get("workflow_runs", [])
            items = [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "status": item["status"],
                    "conclusion": item["conclusion"],
                    "html_url": item["html_url"],
                    "run_number": item["run_number"],
                    "head_branch": item["head_branch"],
                    "updated_at": item["updated_at"],
                }
                for item in runs
            ]
            return {"items": items, "meta": {"repo": repo, "provider": provider}}

    def diff(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        previous_items = {str(item["id"]): item for item in (previous or {}).get("items", [])}
        failures = []
        for item in current.get("items", []):
            old_item = previous_items.get(str(item["id"]))
            if item.get("conclusion") == "failure" and (old_item is None or old_item.get("updated_at") != item.get("updated_at")):
                failures.append(item)
        return {"created": failures, "updated": []}

    def recommended_actions(self, watcher: dict[str, Any], changes: dict[str, Any]) -> list[dict[str, Any]]:
        if not changes.get("created"):
            return []
        latest = changes["created"][0]
        return [
            {
                "label": "自动修复",
                "kind": "create_run",
                "params": {
                    "agent": "codex",
                    "task": f"检查监控 {watcher['name']} 发现的 CI 失败 #{latest['run_number']}，并给出修复方案。",
                },
            },
            {
                "label": "重新运行流水线",
                "kind": "rerun_workflow",
                "params": {"repo": watcher["config"]["repo"], "run_id": latest["id"]},
            },
        ]

    async def perform(self, action: dict[str, Any]) -> dict[str, Any]:
        if not settings.github_token:
            return {"ok": False, "error": "missing_github_token"}
        if action.get("kind") != "rerun_workflow":
            return {"ok": False, "error": f"unsupported_action:{action.get('kind', 'unknown')}"}

        params = action.get("params", {})
        owner, name = params["repo"].split("/", 1)
        headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"https://api.github.com/repos/{owner}/{name}/actions/runs/{params['run_id']}/rerun",
                headers=headers,
            )
        if response.status_code not in {200, 201}:
            return {"ok": False, "error": response.text}
        return {"ok": True}
