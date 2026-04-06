from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


ACTION_ALIASES: dict[str, str] = {
    "start-global": "start_global_autodrive",
    "stop-global": "stop_global_autodrive",
    "restart-global": "restart_global_autodrive",
    "dispatch": "dispatch_next",
    "continue": "continue_task_family",
    "start-scope": "start_task_autodrive",
    "stop-scope": "stop_task_autodrive",
    "adopt": "adopt_run",
    "retry": "retry_run",
    "cancel": "cancel_run",
}

WATCH_COMMAND = "watch"
STATUS_COMMAND = "status"
MENU_COMMAND = "menu"


@dataclass(frozen=True)
class OperatorCliError(Exception):
    message: str
    exit_code: int = 1

    def __str__(self) -> str:
        return self.message


def _configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                continue


def _normalized_api_base(api_base_url: str) -> str:
    value = api_base_url.strip()
    if not value:
        raise OperatorCliError("缺少 KAM API 地址。")
    return value.rstrip("/")


def _request_json(method: str, url: str, *, payload: dict[str, Any] | None = None, timeout_seconds: float = 10.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        if detail:
            try:
                payload = json.loads(detail)
            except json.JSONDecodeError:
                pass
            else:
                if isinstance(payload, dict):
                    message = payload.get("detail") or payload.get("message")
                    if isinstance(message, str) and message.strip():
                        detail = message.strip()
        raise OperatorCliError(f"请求失败：{exc.code} {detail or exc.reason}".strip(), exit_code=1) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise OperatorCliError(f"无法连接 KAM API：{reason}", exit_code=1) from exc

    if not body.strip():
        return {}
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OperatorCliError(f"KAM API 返回了非 JSON 内容：{body[:200]}", exit_code=1) from exc
    if not isinstance(decoded, dict):
        raise OperatorCliError("KAM API 返回了非对象 JSON。", exit_code=1)
    return decoded


def _control_plane_url(api_base_url: str, task_id: str | None) -> str:
    base = _normalized_api_base(api_base_url)
    url = f"{base}/operator/control-plane"
    if task_id:
        query = urllib.parse.urlencode({"task_id": task_id.strip()})
        return f"{url}?{query}"
    return url


def _actions_url(api_base_url: str) -> str:
    return f"{_normalized_api_base(api_base_url)}/operator/actions"


def fetch_control_plane(api_base_url: str, *, task_id: str | None, timeout_seconds: float) -> dict[str, Any]:
    return _request_json("GET", _control_plane_url(api_base_url, task_id), timeout_seconds=timeout_seconds)


def perform_operator_action(
    api_base_url: str,
    *,
    action: str,
    task_id: str | None,
    run_id: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"action": action}
    if task_id:
        payload["taskId"] = task_id.strip()
    if run_id:
        payload["runId"] = run_id.strip()
    return _request_json("POST", _actions_url(api_base_url), payload=payload, timeout_seconds=timeout_seconds)


def _system_status_label(value: str | None) -> str:
    if value == "running":
        return "执行中"
    if value == "attention":
        return "待介入"
    if value == "ready":
        return "可推进"
    if value == "idle":
        return "空闲"
    if value == "waiting_for_run":
        return "等待 Run"
    if value == "waiting_for_lease":
        return "等待 lease"
    if value == "paused":
        return "已暂停"
    return value or "未知"


def _global_status_label(control_plane: dict[str, Any]) -> str:
    global_auto_drive = control_plane.get("globalAutoDrive")
    if not isinstance(global_auto_drive, dict):
        return "未知"
    enabled = global_auto_drive.get("enabled") is True
    status = global_auto_drive.get("status")
    if isinstance(status, str) and status.strip():
        return f"{'已开启' if enabled else '未开启'} / {status.strip()}"
    return "已开启" if enabled else "未开启"


def _task_title(record: Any) -> str | None:
    if not isinstance(record, dict):
        return None
    title = record.get("title")
    record_id = record.get("id")
    if isinstance(title, str) and title.strip():
        if isinstance(record_id, str) and record_id.strip():
            return f"{title.strip()} ({record_id.strip()})"
        return title.strip()
    if isinstance(record_id, str) and record_id.strip():
        return record_id.strip()
    return None


def _optional_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _action_descriptors(control_plane: dict[str, Any]) -> list[dict[str, Any]]:
    actions = control_plane.get("actions")
    if not isinstance(actions, list):
        return []
    return [action for action in actions if isinstance(action, dict)]


def _action_key(action: dict[str, Any]) -> str | None:
    return _optional_text(action.get("key"))


def _find_action_descriptor(control_plane: dict[str, Any], action_key: str) -> dict[str, Any] | None:
    matches = [action for action in _action_descriptors(control_plane) if _action_key(action) == action_key]
    if not matches:
        return None
    for action in matches:
        if action.get("disabled") is not True:
            return action
    return matches[0]


def _preferred_action(control_plane: dict[str, Any]) -> dict[str, Any] | None:
    for action in _action_descriptors(control_plane):
        if action.get("disabled") is not True:
            return action
    return None


def _format_action(action: dict[str, Any]) -> str:
    label = action.get("label") if isinstance(action.get("label"), str) else action.get("key")
    description = action.get("description") if isinstance(action.get("description"), str) else ""
    disabled_reason = action.get("disabledReason") if isinstance(action.get("disabledReason"), str) else None
    suffix = f" | {description}" if description else ""
    if disabled_reason:
        suffix += f" | 不可用：{disabled_reason}"
    return f"- {label}{suffix}"


def format_control_plane(control_plane: dict[str, Any]) -> str:
    focus = control_plane.get("focus") if isinstance(control_plane.get("focus"), dict) else {}
    stats = control_plane.get("stats") if isinstance(control_plane.get("stats"), dict) else {}
    attention = control_plane.get("attention") if isinstance(control_plane.get("attention"), list) else []
    actions = _action_descriptors(control_plane)
    preferred = _preferred_action(control_plane)

    lines = [
        f"状态: {_system_status_label(control_plane.get('systemStatus') if isinstance(control_plane.get('systemStatus'), str) else None)}",
        f"摘要: {control_plane.get('systemSummary') if isinstance(control_plane.get('systemSummary'), str) else '无'}",
        f"全局: {_global_status_label(control_plane)}",
        (
            "焦点: "
            f"task={_task_title(focus.get('task')) or '-'} | "
            f"scope={_task_title(focus.get('scopeTask')) or '-'} | "
            f"run={focus.get('activeRun', {}).get('id') if isinstance(focus.get('activeRun'), dict) and focus.get('activeRun', {}).get('id') else '-'}"
        ),
        (
            "统计: "
            f"running={stats.get('runningRunCount', 0)} "
            f"blocked={stats.get('blockedTaskCount', 0)} "
            f"failed={stats.get('failedTaskCount', 0)} "
            f"pending={stats.get('pendingRunCount', 0)} "
            f"awaiting_adopt={stats.get('passedRunAwaitingAdoptCount', 0)}"
        ),
    ]
    if preferred is not None:
        preferred_label = preferred.get("label") if isinstance(preferred.get("label"), str) else preferred.get("key")
        if isinstance(preferred_label, str):
            lines.append(f"推荐动作: {preferred_label}")

    if attention:
        lines.append("需要关注:")
        for item in attention[:4]:
            if not isinstance(item, dict):
                continue
            title = item.get("title") if isinstance(item.get("title"), str) else item.get("kind")
            summary = item.get("summary") if isinstance(item.get("summary"), str) else ""
            lines.append(f"- {title}: {summary}".rstrip())

    if actions:
        lines.append("可执行动作:")
        for action in actions[:6]:
            if isinstance(action, dict):
                lines.append(_format_action(action))

    return "\n".join(lines)


def _resolve_action(command: str) -> str | None:
    if command in {STATUS_COMMAND, WATCH_COMMAND, MENU_COMMAND}:
        return None
    return ACTION_ALIASES.get(command)


def _validate_action_requirements(command: str, *, task_id: str | None, run_id: str | None) -> None:
    if command in {"continue", "start-scope", "stop-scope"} and not task_id:
        raise OperatorCliError(f"`{command}` 需要传入 --task-id。")
    if command in {"adopt", "retry", "cancel"} and not run_id:
        raise OperatorCliError(f"`{command}` 需要传入 --run-id。")


def _resolve_action_targets(
    *,
    api_base_url: str,
    command: str,
    task_id: str | None,
    run_id: str | None,
    timeout_seconds: float,
) -> tuple[str | None, str | None]:
    requires_task_id = command in {"continue", "start-scope", "stop-scope"}
    requires_run_id = command in {"adopt", "retry", "cancel"}
    if (not requires_task_id or task_id) and (not requires_run_id or run_id):
        return task_id, run_id

    action = _resolve_action(command)
    if action is None:
        return task_id, run_id

    control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
    descriptor = _find_action_descriptor(control_plane, action)
    if descriptor is None:
        return task_id, run_id
    return task_id or _optional_text(descriptor.get("taskId")), run_id or _optional_text(descriptor.get("runId"))


def _emit_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _status_exit_code(control_plane: dict[str, Any], *, fail_on_attention: bool) -> int:
    if fail_on_attention and control_plane.get("systemStatus") == "attention":
        return 2
    return 0


def _format_menu_item(index: int, action: dict[str, Any]) -> str:
    label = action.get("label") if isinstance(action.get("label"), str) else action.get("key") or f"动作 {index}"
    description = action.get("description") if isinstance(action.get("description"), str) else ""
    parts = [f"{index}. {label}"]
    if description:
        parts.append(description)
    task_id = _optional_text(action.get("taskId"))
    run_id = _optional_text(action.get("runId"))
    target_bits = []
    if task_id:
        target_bits.append(f"task={task_id}")
    if run_id:
        target_bits.append(f"run={run_id}")
    if target_bits:
        parts.append(" ".join(target_bits))
    disabled_reason = action.get("disabledReason") if isinstance(action.get("disabledReason"), str) else None
    if action.get("disabled") is True:
        parts.append(f"不可用：{disabled_reason or '当前不可执行'}")
    return " | ".join(parts)


def run_menu(
    *,
    api_base_url: str,
    task_id: str | None,
    timeout_seconds: float,
    fail_on_attention: bool,
) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise OperatorCliError("`menu` 需要交互式终端；脚本集成请改用 `status --json` 或直接执行具体命令。")

    control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
    while True:
        print(format_control_plane(control_plane))
        actions = _action_descriptors(control_plane)
        print("")
        print("菜单:")
        print("0. 刷新状态")
        for index, action in enumerate(actions, start=1):
            print(_format_menu_item(index, action))
        print("q. 退出")

        try:
            choice = input("选择动作 [0 刷新, q 退出]: ").strip().lower()
        except EOFError as exc:
            raise OperatorCliError("`menu` 未检测到可用输入；请在本地交互终端里执行。") from exc
        if choice in {"", "0", "r", "refresh"}:
            control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
            continue
        if choice in {"q", "quit", "exit"}:
            return _status_exit_code(control_plane, fail_on_attention=fail_on_attention)

        try:
            selection = int(choice)
        except ValueError:
            print("输入无效，请输入数字、0 或 q。")
            print("")
            continue

        if selection < 1 or selection > len(actions):
            print("输入超出范围，请重新选择。")
            print("")
            continue

        action = actions[selection - 1]
        if action.get("disabled") is True:
            disabled_reason = action.get("disabledReason") if isinstance(action.get("disabledReason"), str) else "当前不可执行。"
            print(f"动作不可用：{disabled_reason}")
            print("")
            continue

        action_key = _action_key(action)
        if action_key is None:
            print("动作定义不完整，已跳过。")
            print("")
            continue

        response = perform_operator_action(
            api_base_url,
            action=action_key,
            task_id=_optional_text(action.get("taskId")),
            run_id=_optional_text(action.get("runId")),
            timeout_seconds=timeout_seconds,
        )
        summary = response.get("summary") if isinstance(response.get("summary"), str) else "动作已执行。"
        print("")
        print(f"动作结果: {summary}")
        next_control_plane = response.get("controlPlane")
        if isinstance(next_control_plane, dict):
            control_plane = next_control_plane
        else:
            control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
        print("")


def run_status(
    *,
    api_base_url: str,
    task_id: str | None,
    timeout_seconds: float,
    as_json: bool,
    fail_on_attention: bool,
) -> int:
    control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
    if as_json:
        _emit_json(control_plane)
    else:
        print(format_control_plane(control_plane))
    return _status_exit_code(control_plane, fail_on_attention=fail_on_attention)


def run_watch(
    *,
    api_base_url: str,
    task_id: str | None,
    timeout_seconds: float,
    as_json: bool,
    fail_on_attention: bool,
    interval_seconds: float,
    iterations: int,
) -> int:
    completed = 0
    while True:
        control_plane = fetch_control_plane(api_base_url, task_id=task_id, timeout_seconds=timeout_seconds)
        if as_json:
            _emit_json(control_plane)
        else:
            if completed:
                print("")
            print(format_control_plane(control_plane))
        completed += 1
        exit_code = _status_exit_code(control_plane, fail_on_attention=fail_on_attention)
        if exit_code != 0:
            return exit_code
        if iterations > 0 and completed >= iterations:
            return 0
        time.sleep(interval_seconds)


def run_action(
    *,
    api_base_url: str,
    command: str,
    task_id: str | None,
    run_id: str | None,
    timeout_seconds: float,
    as_json: bool,
    fail_on_attention: bool,
) -> int:
    action = _resolve_action(command)
    if action is None:
        raise OperatorCliError(f"未知命令：{command}")
    task_id, run_id = _resolve_action_targets(
        api_base_url=api_base_url,
        command=command,
        task_id=task_id,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
    )
    _validate_action_requirements(command, task_id=task_id, run_id=run_id)
    response = perform_operator_action(
        api_base_url,
        action=action,
        task_id=task_id,
        run_id=run_id,
        timeout_seconds=timeout_seconds,
    )
    if as_json:
        _emit_json(response)
    else:
        summary = response.get("summary") if isinstance(response.get("summary"), str) else "动作已执行。"
        print(f"动作结果: {summary}")
        control_plane = response.get("controlPlane")
        if isinstance(control_plane, dict):
            print("")
            print(format_control_plane(control_plane))
    control_plane = response.get("controlPlane")
    if isinstance(control_plane, dict):
        return _status_exit_code(control_plane, fail_on_attention=fail_on_attention)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query or operate the KAM operator control plane.")
    parser.add_argument(
        "command",
        choices=[STATUS_COMMAND, WATCH_COMMAND, MENU_COMMAND, *sorted(ACTION_ALIASES.keys())],
        help="status/watch/menu or a friendly operator action alias",
    )
    parser.add_argument("--kam-url", default="http://127.0.0.1:8000/api", help="KAM API base URL, defaults to http://127.0.0.1:8000/api")
    parser.add_argument("--task-id", default=None, help="Optional task id for scoped status or task-family actions")
    parser.add_argument("--run-id", default=None, help="Optional run id for adopt/retry/cancel")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of a human summary")
    parser.add_argument("--fail-on-attention", action="store_true", help="Exit 2 when the control plane reports systemStatus=attention")
    parser.add_argument("--interval-seconds", type=float, default=5.0, help="Watch poll interval in seconds, defaults to 5")
    parser.add_argument("--iterations", type=int, default=0, help="Watch loop count; 0 means run forever")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout in seconds, defaults to 10")
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == STATUS_COMMAND:
            return run_status(
                api_base_url=args.kam_url,
                task_id=args.task_id,
                timeout_seconds=args.timeout_seconds,
                as_json=args.json,
                fail_on_attention=args.fail_on_attention,
            )
        if args.command == WATCH_COMMAND:
            return run_watch(
                api_base_url=args.kam_url,
                task_id=args.task_id,
                timeout_seconds=args.timeout_seconds,
                as_json=args.json,
                fail_on_attention=args.fail_on_attention,
                interval_seconds=args.interval_seconds,
                iterations=args.iterations,
            )
        if args.command == MENU_COMMAND:
            if args.json:
                raise OperatorCliError("`menu` 不支持 --json；请改用 `status --json`。")
            return run_menu(
                api_base_url=args.kam_url,
                task_id=args.task_id,
                timeout_seconds=args.timeout_seconds,
                fail_on_attention=args.fail_on_attention,
            )
        return run_action(
            api_base_url=args.kam_url,
            command=args.command,
            task_id=args.task_id,
            run_id=args.run_id,
            timeout_seconds=args.timeout_seconds,
            as_json=args.json,
            fail_on_attention=args.fail_on_attention,
        )
    except OperatorCliError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
