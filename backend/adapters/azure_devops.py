from __future__ import annotations

import base64
from typing import Any

import httpx

from config import settings


class AzureDevOpsAdapter:
    async def fetch(self, config: dict[str, Any]) -> dict[str, Any]:
        if not settings.azure_devops_pat:
            return {"items": [], "meta": {"error": "missing_azure_devops_pat"}}

        org = config.get("org") or settings.azure_devops_org
        project = config["project"]
        watch = config.get("watch", "assigned_work_items")
        headers = {
            "Authorization": "Basic " + base64.b64encode(f":{settings.azure_devops_pat}".encode("utf-8")).decode("utf-8")
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            if watch == "assigned_work_items":
                query = {
                    "query": "Select [System.Id], [System.Title], [System.State] "
                    "From WorkItems Where [System.AssignedTo] = @Me And [System.TeamProject] = @project "
                    "Order By [System.ChangedDate] Desc"
                }
                response = await client.post(
                    f"https://dev.azure.com/{org}/{project}/_apis/wit/wiql?api-version=7.1-preview.2",
                    headers=headers,
                    json=query,
                )
                response.raise_for_status()
                rows = response.json().get("workItems", [])
                items = [{"id": row["id"], "url": row["url"]} for row in rows]
                return {"items": items, "meta": {"org": org, "project": project, "watch": watch}}

            if watch == "pr_threads":
                repo = config["repo"]
                pull_request_id = config["pullRequestId"]
                response = await client.get(
                    f"https://dev.azure.com/{org}/{project}/_apis/git/repositories/{repo}/pullRequests/{pull_request_id}/threads?api-version=7.1",
                    headers=headers,
                )
                response.raise_for_status()
                threads = response.json().get("value", [])
                items = [{"id": item["id"], "status": item["status"], "publishedDate": item.get("publishedDate")} for item in threads]
                return {"items": items, "meta": {"org": org, "project": project, "watch": watch}}

        return {"items": [], "meta": {"org": org, "project": project, "watch": watch}}

    def diff(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        previous_ids = {str(item["id"]) for item in (previous or {}).get("items", [])}
        created = [item for item in current.get("items", []) if str(item["id"]) not in previous_ids]
        return {"created": created, "updated": []}

    def recommended_actions(self, watcher: dict[str, Any], changes: dict[str, Any]) -> list[dict[str, Any]]:
        if not changes.get("created"):
            return []
        return [
            {
                "label": "Plan my sprint",
                "kind": "create_run",
                "params": {
                    "agent": "codex",
                    "task": f"Review the new Azure DevOps work items surfaced by watcher {watcher['name']} and produce a concise plan.",
                },
            }
        ]

    async def perform(self, action: dict[str, Any]) -> dict[str, Any]:
        return {"ok": False, "error": f"unsupported_action:{action.get('kind', 'unknown')}"}
