from __future__ import annotations

import argparse
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

from runtime_paths import runtime_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the packaged KAM desktop runtime.")
    parser.add_argument("--bind-host", default="127.0.0.1", help="Backend bind host, defaults to 127.0.0.1")
    parser.add_argument("--port", type=int, default=8000, help="Backend port, defaults to 8000")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser automatically")
    parser.add_argument("--health-timeout-seconds", type=float, default=30.0, help="How long to wait before giving up on auto-opening the browser")
    return parser


def _wait_for_health(url: str, timeout_seconds: float) -> bool:
    deadline = time.time() + max(timeout_seconds, 1.0)
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2.0) as response:
                body = response.read().decode("utf-8", errors="replace")
            if "\"ok\"" in body:
                return True
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1.0)
            continue
    return False


def _open_browser_once(url: str, timeout_seconds: float) -> None:
    if not _wait_for_health(url, timeout_seconds):
        return
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    runtime_dir = runtime_root()
    url = f"http://127.0.0.1:{args.port}"

    print("==================================")
    print("  KAM Harness - Windows Release")
    print("==================================")
    print(f"访问地址: {url}")
    print(f"运行目录: {runtime_dir}")
    print("关闭方式: 在当前窗口按 Ctrl+C")
    print("")

    if not args.no_browser:
        thread = threading.Thread(
            target=_open_browser_once,
            args=(url, args.health_timeout_seconds),
            daemon=True,
        )
        thread.start()

    from main import app

    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host=args.bind_host,
            port=args.port,
            log_level="info",
        )
    )
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
