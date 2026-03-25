import os
import shutil
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


os.environ["DATABASE_URL"] = "sqlite:///./storage/test-v2-preview.db"
os.environ["AGENT_WORKROOT"] = "./storage/test-v2-runs"
os.environ["OPENAI_API_KEY"] = ""

from app.main import app
from app.core.config import settings
from app.db.base import Base, SessionLocal, engine
from app.services.context_assembler import ContextAssembler


class V2WorkspaceApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)

        self.workroot = Path("./storage/test-v2-runs")
        if self.workroot.exists():
            self._remove_workroot()
        self.workroot.mkdir(parents=True, exist_ok=True)

    def _remove_workroot(self):
        deadline = time.time() + 5
        while True:
            try:
                shutil.rmtree(self.workroot)
                return
            except PermissionError:
                if time.time() >= deadline:
                    raise
                time.sleep(0.25)

    def _wait_run(self, client: TestClient, run_id: str, timeout: float = 20):
        deadline = time.time() + timeout
        last_payload = None
        while time.time() < deadline:
            response = client.get(f"/api/v2/runs/{run_id}")
            self.assertEqual(response.status_code, 200)
            last_payload = response.json()
            if last_payload["status"] in {"passed", "failed", "cancelled"}:
                return last_payload
            time.sleep(0.25)
        self.fail(f"run {run_id} not finished in time, last={last_payload}")

    def _write_fixture(self, path: Path, content: str):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    def _python_script_command(self, script_path: str, *args: str) -> str:
        quoted_python = f"'{sys.executable}'"
        if os.name == "nt":
            return " ".join(["&", quoted_python, script_path, *args])
        return " ".join([quoted_python, script_path, *args])

    def _create_weather_page_fixture(self, repo_root: Path):
        self._write_fixture(
            repo_root / "README.md",
            """
            # Weather Pulse

            This fixture represents a tiny static frontend app.

            - Keep the entrypoints stable: `index.html`, `styles.css`, `app.js`
            - Do not add external dependencies
            - Render a weather dashboard with local mock data
            """,
        )
        self._write_fixture(
            repo_root / "AGENTS.md",
            """
            # Repo Workflow

            - Preserve semantic HTML and accessible button labels
            - Keep the UI in a single static page
            - Support at least three cities: Beijing, Shanghai, Shenzhen
            - Show current weather, quick metrics, and a 3-day forecast
            """,
        )
        self._write_fixture(
            repo_root / "index.html",
            """
            <!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>Starter</title>
                <link rel="stylesheet" href="./styles.css" />
              </head>
              <body>
                <main class="app-shell">
                  <h1>Starter app</h1>
                  <p>Replace this placeholder with a real page.</p>
                </main>
                <script type="module" src="./app.js"></script>
              </body>
            </html>
            """,
        )
        self._write_fixture(
            repo_root / "styles.css",
            """
            :root {
              color-scheme: light;
              font-family: Arial, sans-serif;
            }

            body {
              margin: 0;
              padding: 32px;
              background: #f6f6f6;
            }
            """,
        )
        self._write_fixture(
            repo_root / "app.js",
            """
            console.log("starter");
            """,
        )
        self._write_fixture(
            repo_root / "validate_weather_page.py",
            """
            from pathlib import Path


            root = Path(__file__).resolve().parent
            html = (root / "index.html").read_text(encoding="utf-8")
            css = (root / "styles.css").read_text(encoding="utf-8")
            js = (root / "app.js").read_text(encoding="utf-8")

            errors: list[str] = []

            def expect(text: str, content: str, message: str):
                if text not in content:
                    errors.append(message)


            expect("<title>Weather Pulse</title>", html, "missing weather page title")
            expect('id="city-switcher"', html, "missing city switcher")
            expect('id="current-weather"', html, "missing current weather section")
            expect('id="forecast-list"', html, "missing forecast list")
            expect('id="metric-grid"', html, "missing metric grid")
            expect('<script type="module" src="./app.js"></script>', html, "missing app script")
            expect('weather-shell', css, "missing shell styles")
            expect('forecast-card', css, "missing forecast card styles")
            expect('const weatherByCity', js, "missing weather data map")
            expect('function renderCity', js, "missing render function")
            expect('const citySwitcher = document.querySelector', js, "missing city switcher binding")

            for city in ("Beijing", "Shanghai", "Shenzhen"):
                expect(city, html + js, f"missing city {city}")

            if errors:
                raise SystemExit("\\n".join(errors))

            print("weather page validation ok")
            """,
        )
        self._write_fixture(
            repo_root / "tools" / "generate_weather_page.py",
            """
            from __future__ import annotations

            import argparse
            from pathlib import Path


            HTML = \"\"\"<!DOCTYPE html>
            <html lang="en">
              <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>Weather Pulse</title>
                <link rel="stylesheet" href="./styles.css" />
              </head>
              <body>
                <main class="weather-shell">
                  <section class="hero">
                    <p class="eyebrow">Local mock weather</p>
                    <h1>Weather Pulse</h1>
                    <p class="hero-copy">A compact city weather dashboard with current conditions, quick metrics, and a 3-day forecast.</p>
                  </section>

                  <section class="panel">
                    <div id="city-switcher" class="city-switcher" aria-label="City switcher">
                      <button type="button" class="city-pill is-active" data-city="Beijing">Beijing</button>
                      <button type="button" class="city-pill" data-city="Shanghai">Shanghai</button>
                      <button type="button" class="city-pill" data-city="Shenzhen">Shenzhen</button>
                    </div>

                    <div class="current-layout">
                      <article id="current-weather" class="current-card" aria-live="polite"></article>
                      <div id="metric-grid" class="metric-grid"></div>
                    </div>

                    <section class="forecast-panel">
                      <div class="section-heading">
                        <h2>3-day forecast</h2>
                        <p>Updated from local mock weather snapshots.</p>
                      </div>
                      <div id="forecast-list" class="forecast-list"></div>
                    </section>
                  </section>
                </main>
                <script type="module" src="./app.js"></script>
              </body>
            </html>
            \"\"\"

            CSS = \"\"\":root {
              color-scheme: light;
              font-family: "Segoe UI", Arial, sans-serif;
              --bg: #f4f7fb;
              --panel: rgba(255, 255, 255, 0.82);
              --line: rgba(33, 44, 65, 0.12);
              --text: #172033;
              --muted: #5f6f86;
              --accent: #1d74f5;
              --accent-soft: rgba(29, 116, 245, 0.12);
            }

            * {
              box-sizing: border-box;
            }

            body {
              margin: 0;
              min-height: 100vh;
              background:
                radial-gradient(circle at top left, rgba(29, 116, 245, 0.18), transparent 30%),
                linear-gradient(180deg, #f8fbff 0%, var(--bg) 100%);
              color: var(--text);
            }

            .weather-shell {
              width: min(1120px, calc(100% - 48px));
              margin: 0 auto;
              padding: 48px 0 72px;
            }

            .hero {
              display: grid;
              gap: 10px;
              margin-bottom: 28px;
            }

            .eyebrow {
              margin: 0;
              font-size: 12px;
              letter-spacing: 0.18em;
              text-transform: uppercase;
              color: var(--muted);
            }

            .hero h1 {
              margin: 0;
              font-size: clamp(2.4rem, 4vw, 4rem);
            }

            .hero-copy {
              margin: 0;
              max-width: 62ch;
              line-height: 1.65;
              color: var(--muted);
            }

            .panel {
              border: 1px solid var(--line);
              border-radius: 28px;
              background: var(--panel);
              backdrop-filter: blur(14px);
              box-shadow: 0 24px 70px rgba(20, 33, 61, 0.08);
              padding: 24px;
            }

            .city-switcher {
              display: flex;
              flex-wrap: wrap;
              gap: 12px;
              margin-bottom: 24px;
            }

            .city-pill {
              border: 0;
              border-radius: 999px;
              padding: 10px 16px;
              background: rgba(23, 32, 51, 0.06);
              color: var(--text);
              cursor: pointer;
              font: inherit;
            }

            .city-pill.is-active {
              background: var(--accent);
              color: white;
            }

            .current-layout {
              display: grid;
              gap: 18px;
              grid-template-columns: minmax(0, 1.3fr) minmax(280px, 0.9fr);
              align-items: stretch;
            }

            .current-card,
            .metric-grid,
            .forecast-panel {
              border: 1px solid rgba(23, 32, 51, 0.08);
              border-radius: 22px;
              background: rgba(255, 255, 255, 0.88);
            }

            .current-card {
              padding: 22px;
              display: grid;
              gap: 16px;
            }

            .current-meta {
              display: flex;
              justify-content: space-between;
              gap: 12px;
              color: var(--muted);
              font-size: 14px;
            }

            .current-temp {
              font-size: clamp(3rem, 5vw, 4.8rem);
              line-height: 0.95;
              font-weight: 700;
            }

            .condition-chip {
              display: inline-flex;
              width: fit-content;
              border-radius: 999px;
              padding: 6px 12px;
              background: var(--accent-soft);
              color: var(--accent);
              font-size: 14px;
              font-weight: 600;
            }

            .metric-grid {
              padding: 18px;
              display: grid;
              gap: 12px;
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }

            .metric-card {
              border-radius: 16px;
              background: rgba(23, 32, 51, 0.04);
              padding: 14px;
            }

            .metric-label {
              color: var(--muted);
              font-size: 12px;
              text-transform: uppercase;
              letter-spacing: 0.08em;
            }

            .metric-value {
              margin-top: 8px;
              font-size: 20px;
              font-weight: 700;
            }

            .forecast-panel {
              margin-top: 18px;
              padding: 22px;
            }

            .section-heading {
              display: flex;
              flex-wrap: wrap;
              justify-content: space-between;
              gap: 8px;
              margin-bottom: 16px;
            }

            .section-heading h2,
            .section-heading p {
              margin: 0;
            }

            .section-heading p {
              color: var(--muted);
            }

            .forecast-list {
              display: grid;
              gap: 14px;
              grid-template-columns: repeat(3, minmax(0, 1fr));
            }

            .forecast-card {
              border-radius: 18px;
              background: rgba(23, 32, 51, 0.04);
              padding: 16px;
              display: grid;
              gap: 6px;
            }

            .forecast-day {
              font-weight: 700;
            }

            .forecast-range {
              font-size: 22px;
              font-weight: 700;
            }

            .forecast-note {
              color: var(--muted);
              line-height: 1.5;
            }

            @media (max-width: 860px) {
              .weather-shell {
                width: min(100% - 24px, 100%);
                padding: 24px 0 48px;
              }

              .panel {
                padding: 16px;
              }

              .current-layout,
              .forecast-list {
                grid-template-columns: 1fr;
              }
            }
            \"\"\"

            JS = \"\"\"const weatherByCity = {
              Beijing: {
                updatedAt: "06:30",
                condition: "Sunny",
                temperature: 27,
                high: 31,
                low: 20,
                metrics: [
                  { label: "Humidity", value: "42%" },
                  { label: "Wind", value: "12 km/h" },
                  { label: "UV Index", value: "6 / 10" },
                  { label: "Feels Like", value: "29°C" },
                ],
                forecast: [
                  { day: "Today", range: "31° / 20°", note: "Clear sky with dry afternoon breeze." },
                  { day: "Tomorrow", range: "29° / 19°", note: "Bright morning, light cloud in the evening." },
                  { day: "Friday", range: "28° / 18°", note: "Cooler night and comfortable daytime sun." },
                ],
              },
              Shanghai: {
                updatedAt: "06:35",
                condition: "Cloudy",
                temperature: 24,
                high: 28,
                low: 21,
                metrics: [
                  { label: "Humidity", value: "63%" },
                  { label: "Wind", value: "18 km/h" },
                  { label: "UV Index", value: "4 / 10" },
                  { label: "Feels Like", value: "26°C" },
                ],
                forecast: [
                  { day: "Today", range: "28° / 21°", note: "Soft cloud cover with warm, humid air." },
                  { day: "Tomorrow", range: "27° / 22°", note: "Brief drizzle around noon, calm by sunset." },
                  { day: "Friday", range: "26° / 21°", note: "Thicker morning cloud then brighter afternoon." },
                ],
              },
              Shenzhen: {
                updatedAt: "06:20",
                condition: "Rain Showers",
                temperature: 29,
                high: 32,
                low: 25,
                metrics: [
                  { label: "Humidity", value: "78%" },
                  { label: "Wind", value: "15 km/h" },
                  { label: "UV Index", value: "5 / 10" },
                  { label: "Feels Like", value: "34°C" },
                ],
                forecast: [
                  { day: "Today", range: "32° / 25°", note: "Scattered showers and muggy afternoon heat." },
                  { day: "Tomorrow", range: "31° / 25°", note: "Storm risk after lunch with mild evening rain." },
                  { day: "Friday", range: "30° / 24°", note: "Cloud breaks in the morning, showers later." },
                ],
              },
            };

            const citySwitcher = document.querySelector("#city-switcher");
            const currentWeather = document.querySelector("#current-weather");
            const metricGrid = document.querySelector("#metric-grid");
            const forecastList = document.querySelector("#forecast-list");

            function renderCity(city) {
              const data = weatherByCity[city];
              if (!data) return;

              currentWeather.innerHTML = `
                <div class="current-meta">
                  <span>${city}</span>
                  <span>Updated ${data.updatedAt}</span>
                </div>
                <div class="current-temp">${data.temperature}°C</div>
                <div class="condition-chip">${data.condition}</div>
                <div class="forecast-note">Daily range ${data.high}° / ${data.low}° with local mock weather data.</div>
              `;

              metricGrid.innerHTML = data.metrics
                .map(
                  (metric) => `
                    <article class="metric-card">
                      <div class="metric-label">${metric.label}</div>
                      <div class="metric-value">${metric.value}</div>
                    </article>
                  `,
                )
                .join("");

              forecastList.innerHTML = data.forecast
                .map(
                  (item) => `
                    <article class="forecast-card">
                      <div class="forecast-day">${item.day}</div>
                      <div class="forecast-range">${item.range}</div>
                      <div class="forecast-note">${item.note}</div>
                    </article>
                  `,
                )
                .join("");

              citySwitcher.querySelectorAll("[data-city]").forEach((button) => {
                button.classList.toggle("is-active", button.dataset.city === city);
              });
            }

            citySwitcher.addEventListener("click", (event) => {
              const target = event.target.closest("[data-city]");
              if (!target) return;
              renderCity(target.dataset.city);
            });

            renderCity("Beijing");
            \"\"\"

            def main():
                parser = argparse.ArgumentParser()
                parser.add_argument("--summary", required=True)
                parser.add_argument("--prompt", required=True)
                args = parser.parse_args()

                repo_root = Path.cwd()
                prompt = Path(args.prompt).read_text(encoding="utf-8").strip()

                # Touch the repo instructions so the scenario behaves like a real repository task.
                _ = (repo_root / "README.md").read_text(encoding="utf-8")
                _ = (repo_root / "AGENTS.md").read_text(encoding="utf-8")

                (repo_root / "index.html").write_text(HTML, encoding="utf-8")
                (repo_root / "styles.css").write_text(CSS, encoding="utf-8")
                (repo_root / "app.js").write_text(JS, encoding="utf-8")

                summary = (
                    "Created a Weather Pulse dashboard with a city switcher, current weather card, "
                    "metric grid, and a three-day forecast. "
                    f"Prompt source: {prompt.splitlines()[1] if len(prompt.splitlines()) > 1 else prompt[:80]}"
                )
                Path(args.summary).write_text(summary, encoding="utf-8")
                print("weather page generated")


            if __name__ == "__main__":
                main()
            """,
        )

    def test_project_thread_message_and_run_flow(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={
                    "title": "KAM v2",
                    "description": "workspace project",
                    "checkCommands": ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            )
            self.assertEqual(project.status_code, 200)
            project_payload = project.json()
            self.assertEqual(project_payload["title"], "KAM v2")

            thread = client.post(
                f"/api/v2/projects/{project_payload['id']}/threads",
                json={"title": "继续昨天的工作"},
            )
            self.assertEqual(thread.status_code, 200)
            thread_payload = thread.json()

            command = (
                "if [ -f '{run_dir}/first-pass.flag' ]; then printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'retry fixed' > '{summary_file}'; "
                "else touch '{run_dir}/first-pass.flag'; printf '%s' 'first round' > '{summary_file}'; fi"
                if os.name != "nt"
                else "if (Test-Path -LiteralPath (Join-Path '{run_dir}' 'first-pass.flag')) { Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'retry fixed'; } else { Set-Content -Path (Join-Path '{run_dir}' 'first-pass.flag') -Value '1'; Set-Content -Path '{summary_file}' -Value 'first round'; }"
            )
            created = client.post(
                f"/api/v2/threads/{thread_payload['id']}/runs",
                json={
                    "agent": "custom",
                    "command": command,
                    "prompt": "实现 token refresh",
                    "autoStart": True,
                    "maxRounds": 2,
                },
            )
            self.assertEqual(created.status_code, 200)
            created_payload = created.json()
            self.assertEqual(created_payload["status"], "pending")

            run_payload = self._wait_run(client, created_payload["id"])
            self.assertEqual(run_payload["status"], "passed")
            self.assertEqual(run_payload["round"], 2)

            artifacts = client.get(f"/api/v2/runs/{created_payload['id']}/artifacts")
            self.assertEqual(artifacts.status_code, 200)
            artifact_types = {item["type"] for item in artifacts.json()["artifacts"]}
            self.assertTrue({"prompt", "context", "stdout", "stderr", "summary", "check_result", "feedback"}.issubset(artifact_types))

            thread_detail = client.get(f"/api/v2/threads/{thread_payload['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            thread_payload_detail = thread_detail.json()
            self.assertGreaterEqual(len(thread_payload_detail["runs"]), 1)
            event_types = {item.get("metadata", {}).get("eventType") for item in thread_payload_detail["messages"]}
            self.assertIn("run-created", event_types)
            self.assertIn("run-passed", event_types)

    def test_project_file_tree_endpoint(self):
        with tempfile.TemporaryDirectory() as repo_dir:
            repo_root = Path(repo_dir)
            (repo_root / 'src').mkdir(parents=True, exist_ok=True)
            (repo_root / 'docs').mkdir(parents=True, exist_ok=True)
            (repo_root / 'src' / 'main.ts').write_text('console.log("kam")', encoding='utf-8')
            (repo_root / 'docs' / 'notes.md').write_text('# notes', encoding='utf-8')
            (repo_root / '.secret').write_text('hidden', encoding='utf-8')

            with TestClient(app) as client:
                project = client.post(
                    '/api/v2/projects',
                    json={
                        'title': 'Files project',
                        'repoPath': str(repo_root),
                    },
                ).json()

                root_listing = client.get(f"/api/v2/projects/{project['id']}/files")
                self.assertEqual(root_listing.status_code, 200)
                payload = root_listing.json()
                self.assertEqual(payload['currentPath'], '')
                names = [item['name'] for item in payload['entries']]
                self.assertIn('src', names)
                self.assertIn('docs', names)
                self.assertNotIn('.secret', names)

                nested_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'path': 'src'},
                )
                self.assertEqual(nested_listing.status_code, 200)
                nested_payload = nested_listing.json()
                self.assertEqual(nested_payload['currentPath'], 'src')
                self.assertEqual(nested_payload['parentPath'], '')
                self.assertEqual(nested_payload['entries'][0]['name'], 'main.ts')

                hidden_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'include_hidden': 'true'},
                )
                self.assertEqual(hidden_listing.status_code, 200)
                hidden_names = [item['name'] for item in hidden_listing.json()['entries']]
                self.assertIn('.secret', hidden_names)

                filtered_listing = client.get(
                    f"/api/v2/projects/{project['id']}/files",
                    params={'query': 'src', 'entry_type': 'dir'},
                )
                self.assertEqual(filtered_listing.status_code, 200)
                filtered_payload = filtered_listing.json()
                self.assertEqual(filtered_payload['totalEntries'], 2)
                self.assertEqual(filtered_payload['filteredEntries'], 1)
                self.assertEqual(filtered_payload['entries'][0]['name'], 'src')

    def test_bootstrap_message_real_weather_page_scenario_generates_valid_repo_output(self):
        with tempfile.TemporaryDirectory() as repo_dir:
            repo_root = Path(repo_dir)
            self._create_weather_page_fixture(repo_root)

            command = self._python_script_command(
                "tools/generate_weather_page.py",
                "--summary",
                "'{summary_file}'",
                "--prompt",
                "'{prompt_file}'",
            )
            validate_command = self._python_script_command("validate_weather_page.py")

            with TestClient(app) as client:
                created = client.post(
                    "/api/v2/bootstrap/message",
                    json={
                        "projectTitle": "Weather Pulse workspace",
                        "threadTitle": "Build weather page",
                        "repoPath": str(repo_root),
                        "checkCommands": [validate_command],
                        "content": "生成一个天气页面，支持北京、上海、深圳切换，展示当前天气、关键指标和未来三天预报。",
                        "agent": "custom",
                        "command": command,
                        "createRun": True,
                    },
                )
                self.assertEqual(created.status_code, 200)
                payload = created.json()
                self.assertEqual(payload["project"]["title"], "Weather Pulse workspace")
                self.assertEqual(payload["thread"]["title"], "Build weather page")
                self.assertEqual(len(payload["runs"]), 1)

                run_payload = self._wait_run(client, payload["runs"][0]["id"])
                self.assertEqual(run_payload["status"], "passed")

                html = (repo_root / "index.html").read_text(encoding="utf-8")
                css = (repo_root / "styles.css").read_text(encoding="utf-8")
                js = (repo_root / "app.js").read_text(encoding="utf-8")
                self.assertIn("Weather Pulse", html)
                self.assertIn('id="city-switcher"', html)
                self.assertIn('id="current-weather"', html)
                self.assertIn("forecast-card", css)
                self.assertIn("renderCity", js)
                self.assertIn("Shenzhen", js)

                artifacts = client.get(f"/api/v2/runs/{payload['runs'][0]['id']}/artifacts")
                self.assertEqual(artifacts.status_code, 200)
                artifact_payload = artifacts.json()["artifacts"]
                artifact_types = {item["type"] for item in artifact_payload}
                self.assertTrue({"summary", "stdout", "stderr", "check_result"}.issubset(artifact_types))

                summary_artifact = next(item for item in artifact_payload if item["type"] == "summary")
                self.assertIn("Weather Pulse dashboard", summary_artifact["content"])

                check_artifact = next(item for item in artifact_payload if item["type"] == "check_result")
                self.assertIn("validate_weather_page.py", check_artifact["content"])
                self.assertIn('"passed": true', check_artifact["content"])

                tree = client.get(f"/api/v2/projects/{payload['project']['id']}/files")
                self.assertEqual(tree.status_code, 200)
                names = {item["name"] for item in tree.json()["entries"]}
                self.assertTrue({"index.html", "styles.css", "app.js", "validate_weather_page.py", "tools"}.issubset(names))

    def test_run_events_endpoint_streams_payload(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Events project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "事件流"},
            ).json()

            command = (
                "printf '%s' 'event done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'event done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    "agent": "custom",
                    "command": command,
                    "prompt": "事件流验证",
                    "autoStart": True,
                },
            ).json()
            run_payload = self._wait_run(client, created["id"])
            self.assertEqual(run_payload["status"], "passed")

            with client.stream("GET", f"/api/v2/runs/{created['id']}/events") as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())
            self.assertIn('data: ', body)
            self.assertIn('"status": "passed"', body)
            self.assertIn('summary', body)

    def test_memory_endpoints(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Memory project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "记忆测试"},
            ).json()

            preference = client.post(
                "/api/v2/memory/preferences",
                json={
                    "category": "tool",
                    "key": "package-manager",
                    "value": "pnpm",
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(preference.status_code, 200)

            updated = client.put(
                f"/api/v2/memory/preferences/{preference.json()['id']}",
                json={"value": "pnpm-workspace"},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["value"], "pnpm-workspace")

            decision = client.post(
                "/api/v2/memory/decisions",
                json={
                    "projectId": project["id"],
                    "question": "状态管理选什么？",
                    "decision": "Zustand",
                    "reasoning": "足够轻量",
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(decision.status_code, 200)

            updated_decision = client.put(
                f"/api/v2/memory/decisions/{decision.json()['id']}",
                json={
                    "question": "状态管理最终选什么？",
                    "decision": "Jotai",
                    "reasoning": "这次想要更细粒度",
                },
            )
            self.assertEqual(updated_decision.status_code, 200)
            self.assertEqual(updated_decision.json()["decision"], "Jotai")

            learning = client.post(
                "/api/v2/memory/learnings",
                json={
                    "projectId": project["id"],
                    "content": "OAuth refresh 需要处理 race condition",
                    "embedding": [0.1, 0.2],
                    "sourceThreadId": thread["id"],
                },
            )
            self.assertEqual(learning.status_code, 200)

            updated_learning = client.put(
                f"/api/v2/memory/learnings/{learning.json()['id']}",
                json={
                    "content": "OAuth refresh 还要处理 race condition、并发刷新和 token 覆盖",
                    "embedding": [0.2, 0.3],
                },
            )
            self.assertEqual(updated_learning.status_code, 200)
            self.assertIn("并发刷新", updated_learning.json()["content"])

            listing = client.get(
                "/api/v2/memory/learnings",
                params={"project_id": project["id"]},
            )
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(len(listing.json()["learnings"]), 1)

            search = client.get(
                "/api/v2/memory/search",
                params={"query": "race", "project_id": project["id"]},
            )
            self.assertEqual(search.status_code, 200)
            self.assertEqual(len(search.json()["learnings"]), 1)

    def test_learning_auto_generates_embedding_when_key_available(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [0.11, 0.22, 0.33],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Embedding project"},
                    ).json()

                    learning = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "OAuth refresh 需要处理 race condition 和并发刷新覆盖",
                        },
                    )
                    self.assertEqual(learning.status_code, 200)
                    self.assertEqual(learning.json()["embedding"], [0.11, 0.22, 0.33])
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_memory_search_prefers_semantic_learning_matches(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [1.0, 0.0],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Semantic search project"},
                    ).json()

                    first = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "处理 OAuth refresh token 的并发覆盖",
                            "embedding": [1.0, 0.0],
                        },
                    )
                    second = client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "构建发布脚本要处理环境变量模板",
                            "embedding": [0.0, 1.0],
                        },
                    )
                    self.assertEqual(first.status_code, 200)
                    self.assertEqual(second.status_code, 200)

                    result = client.get(
                        "/api/v2/memory/search",
                        params={"query": "怎么避免 refresh token 竞态", "project_id": project["id"]},
                    )
                    self.assertEqual(result.status_code, 200)
                    learnings = result.json()["learnings"]
                    self.assertGreaterEqual(len(learnings), 1)
                    self.assertEqual(learnings[0]["content"], "处理 OAuth refresh token 的并发覆盖")
                    self.assertIn("semanticScore", learnings[0])
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_memory_search_returns_semantic_matches_for_preferences_and_decisions(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [1.0, 0.0],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Semantic search memory project"},
                    ).json()
                    thread = client.post(
                        f"/api/v2/projects/{project['id']}/threads",
                        json={"title": "记忆搜索"},
                    ).json()

                    preference = client.post(
                        "/api/v2/memory/preferences",
                        json={
                            "category": "tool",
                            "key": "package-manager",
                            "value": "pnpm workspace",
                            "sourceThreadId": thread["id"],
                        },
                    )
                    unrelated_preference = client.post(
                        "/api/v2/memory/preferences",
                        json={
                            "category": "tool",
                            "key": "formatter",
                            "value": "ruff format",
                            "embedding": [0.0, 1.0],
                            "sourceThreadId": thread["id"],
                        },
                    )
                    decision = client.post(
                        "/api/v2/memory/decisions",
                        json={
                            "projectId": project["id"],
                            "question": "monorepo 默认用哪个包管理器？",
                            "decision": "pnpm workspace",
                            "reasoning": "workspace 依赖管理更稳定",
                            "sourceThreadId": thread["id"],
                        },
                    )
                    unrelated_decision = client.post(
                        "/api/v2/memory/decisions",
                        json={
                            "projectId": project["id"],
                            "question": "代码格式工具选什么？",
                            "decision": "ruff format",
                            "reasoning": "速度更快",
                            "embedding": [0.0, 1.0],
                            "sourceThreadId": thread["id"],
                        },
                    )
                    self.assertEqual(preference.status_code, 200)
                    self.assertEqual(unrelated_preference.status_code, 200)
                    self.assertEqual(decision.status_code, 200)
                    self.assertEqual(unrelated_decision.status_code, 200)

                    result = client.get(
                        "/api/v2/memory/search",
                        params={"query": "monorepo 默认用什么包管理器", "project_id": project["id"]},
                    )
                    self.assertEqual(result.status_code, 200)
                    payload = result.json()

                    preferences = payload["preferences"]
                    decisions = payload["decisions"]
                    self.assertGreaterEqual(len(preferences), 1)
                    self.assertGreaterEqual(len(decisions), 1)
                    self.assertEqual(preferences[0]["key"], "package-manager")
                    self.assertEqual(preferences[0]["value"], "pnpm workspace")
                    self.assertIn("semanticScore", preferences[0])
                    self.assertIn("searchScore", preferences[0])
                    self.assertIn(preferences[0]["matchType"], {"semantic", "hybrid"})
                    self.assertEqual(decisions[0]["decision"], "pnpm workspace")
                    self.assertIn("semanticScore", decisions[0])
                    self.assertIn("searchScore", decisions[0])
                    self.assertIn(decisions[0]["matchType"], {"semantic", "hybrid"})
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_context_assembler_prioritizes_semantic_memories_for_current_thread(self):
        class FakeEmbeddingResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'data': [
                        {
                            'embedding': [1.0, 0.0],
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.memory_service.httpx.post', return_value=FakeEmbeddingResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        "/api/v2/projects",
                        json={"title": "Assembler memory project"},
                    ).json()
                    thread = client.post(
                        f"/api/v2/projects/{project['id']}/threads",
                        json={"title": "Monorepo 包管理方案"},
                    ).json()

                    client.post(
                        "/api/v2/memory/preferences",
                        json={
                            "category": "tool",
                            "key": "package-manager",
                            "value": "pnpm workspace",
                            "sourceThreadId": thread["id"],
                        },
                    )
                    client.post(
                        "/api/v2/memory/decisions",
                        json={
                            "projectId": project["id"],
                            "question": "monorepo 默认用哪个包管理器？",
                            "decision": "pnpm workspace",
                            "reasoning": "workspace 依赖管理更稳定",
                            "sourceThreadId": thread["id"],
                        },
                    )
                    client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "Monorepo 环境里 pnpm workspace 对依赖链接和安装速度更稳定。",
                        },
                    )

                    client.post(
                        "/api/v2/memory/preferences",
                        json={
                            "category": "tool",
                            "key": "formatter",
                            "value": "ruff format",
                            "embedding": [0.0, 1.0],
                            "sourceThreadId": thread["id"],
                        },
                    )
                    client.post(
                        "/api/v2/memory/decisions",
                        json={
                            "projectId": project["id"],
                            "question": "代码格式工具选什么？",
                            "decision": "ruff format",
                            "reasoning": "速度更快",
                            "embedding": [0.0, 1.0],
                            "sourceThreadId": thread["id"],
                        },
                    )
                    client.post(
                        "/api/v2/memory/learnings",
                        json={
                            "projectId": project["id"],
                            "content": "Ruff format 适合统一 Python 代码风格。",
                            "embedding": [0.0, 1.0],
                        },
                    )

                    posted = client.post(
                        f"/api/v2/threads/{thread['id']}/messages",
                        json={
                            "content": "继续整理 monorepo 的包管理器方案，这轮先不要执行。",
                            "createRun": False,
                        },
                    )
                    self.assertEqual(posted.status_code, 200)

                    db = SessionLocal()
                    try:
                        context = ContextAssembler(db).assemble(thread["id"])
                    finally:
                        db.close()

                    self.assertIsNotNone(context)
                    self.assertEqual(context["preferences"][0]["key"], "package-manager")
                    self.assertEqual(context["decisions"][0]["decision"], "pnpm workspace")
                    self.assertIn("pnpm workspace", context["learnings"][0]["content"])
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_compare_endpoint_creates_grouped_runs(self):
        with TestClient(app) as client:
            project = client.post(
                "/api/v2/projects",
                json={"title": "Compare project"},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={"title": "并发对比"},
            ).json()

            command_a = (
                "printf '%s' 'A done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'A done'"
            )
            command_b = (
                "printf '%s' 'B done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'B done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/compare",
                json={
                    "prompt": "分别实现 refresh token 流程并对比",
                    "agents": [
                        {"agent": "custom", "label": "方案 A", "command": command_a},
                        {"agent": "custom", "label": "方案 B", "command": command_b},
                    ],
                    "autoStart": True,
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertTrue(payload["compareId"])
            self.assertEqual(len(payload["runs"]), 2)
            self.assertEqual(payload["message"]["role"], "system")

            first = self._wait_run(client, payload["runs"][0]["id"])
            second = self._wait_run(client, payload["runs"][1]["id"])
            self.assertEqual(first["status"], "passed")
            self.assertEqual(second["status"], "passed")
            self.assertEqual(first["metadata"]["compareGroupId"], payload["compareId"])
            self.assertEqual(second["metadata"]["compareGroupId"], payload["compareId"])

            thread_detail = client.get(f"/api/v2/threads/{thread['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            runs = thread_detail.json()["runs"]
            compare_runs = [item for item in runs if item["metadata"].get("compareGroupId") == payload["compareId"]]
            self.assertEqual(len(compare_runs), 2)

    def test_message_router_auto_creates_run_and_extracts_preference(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={
                    'title': 'Router project',
                    'checkCommands': ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Router thread'},
            ).json()

            command = (
                "printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'router fixed' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'router fixed'"
            )
            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '以后默认用 pnpm，继续修复登录模块',
                    'agent': 'custom',
                    'command': command,
                },
            )
            self.assertEqual(posted.status_code, 200)
            payload = posted.json()
            self.assertEqual(len(payload['runs']), 1)
            self.assertEqual(payload['preferences'][0]['key'], 'package-manager')
            self.assertIsNotNone(payload['reply'])
            self.assertIn('自动创建 1 个 custom run', payload['reply']['content'])
            self.assertEqual(payload['routerMode'], 'heuristic')

            run_payload = self._wait_run(client, payload['runs'][0]['id'])
            self.assertEqual(run_payload['status'], 'passed')

            preferences = client.get('/api/v2/memory/preferences')
            self.assertEqual(preferences.status_code, 200)
            self.assertEqual(preferences.json()['preferences'][0]['value'], 'pnpm')

    def test_bootstrap_message_creates_project_thread_and_run(self):
        with TestClient(app) as client:
            command = (
                "printf '%s' 'ok' > '{run_dir}/done.txt'; printf '%s' 'bootstrap done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path (Join-Path '{run_dir}' 'done.txt') -Value 'ok'; Set-Content -Path '{summary_file}' -Value 'bootstrap done'"
            )
            created = client.post(
                '/api/v2/bootstrap/message',
                json={
                    'projectTitle': '认证模块重构',
                    'threadTitle': '首轮分析',
                    'content': '以后默认用 pnpm，继续修复登录模块',
                    'agent': 'custom',
                    'command': command,
                    'checkCommands': ["test -f '{run_dir}/done.txt'" if os.name != "nt" else "if (!(Test-Path -LiteralPath (Join-Path '{run_dir}' 'done.txt'))) { throw 'missing done.txt'; }"],
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()
            self.assertEqual(payload['project']['title'], '认证模块重构')
            self.assertEqual(payload['thread']['title'], '首轮分析')
            self.assertEqual(payload['message']['role'], 'user')
            self.assertEqual(payload['reply']['role'], 'assistant')
            self.assertEqual(len(payload['runs']), 1)
            self.assertEqual(payload['preferences'][0]['key'], 'package-manager')

            run_payload = self._wait_run(client, payload['runs'][0]['id'])
            self.assertEqual(run_payload['status'], 'passed')

            thread_detail = client.get(f"/api/v2/threads/{payload['thread']['id']}")
            self.assertEqual(thread_detail.status_code, 200)
            self.assertGreaterEqual(len(thread_detail.json()['messages']), 2)

    def test_user_message_auto_extracts_resources_to_project(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Resources project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '资源抽取'},
            ).json()

            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '请参考 https://example.com/spec ，并查看 src/auth/refresh.py 和 docs/design/auth-flow.md',
                    'createRun': False,
                },
            )
            self.assertEqual(posted.status_code, 200)

            project_detail = client.get(f"/api/v2/projects/{project['id']}")
            self.assertEqual(project_detail.status_code, 200)
            resources = project_detail.json()['resources']
            uris = {item['uri'] for item in resources}
            self.assertIn('https://example.com/spec', uris)
            self.assertIn('src/auth/refresh.py', uris)
            self.assertIn('docs/design/auth-flow.md', uris)
            self.assertTrue(all(item['metadata'].get('autoExtracted') for item in resources))

    def test_router_reply_references_history_preferences_and_decisions(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Memory reply project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Memory reply thread'},
            ).json()

            preference = client.post(
                '/api/v2/memory/preferences',
                json={
                    'category': 'tool',
                    'key': 'package-manager',
                    'value': 'pnpm',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(preference.status_code, 200)

            decision = client.post(
                '/api/v2/memory/decisions',
                json={
                    'projectId': project['id'],
                    'question': '状态管理选什么？',
                    'decision': 'Zustand',
                    'reasoning': '足够轻量',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(decision.status_code, 200)

            learning = client.post(
                '/api/v2/memory/learnings',
                json={
                    'projectId': project['id'],
                    'content': 'OAuth refresh 要处理 race condition 与并发刷新覆盖。',
                    'sourceThreadId': thread['id'],
                },
            )
            self.assertEqual(learning.status_code, 200)

            posted = client.post(
                f"/api/v2/threads/{thread['id']}/messages",
                json={
                    'content': '先聊聊这个项目下一步',
                    'createRun': False,
                },
            )
            self.assertEqual(posted.status_code, 200)
            payload = posted.json()
            self.assertIn('package-manager=pnpm', payload['reply']['content'])
            self.assertIn('状态管理选什么？ → Zustand', payload['reply']['content'])
            self.assertIn('OAuth refresh 要处理 race condition', payload['reply']['content'])

    def test_thread_events_endpoint_streams_payload(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Thread events project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '事件流线程'},
            ).json()

            command = (
                "printf '%s' 'thread event done' > '{summary_file}'"
                if os.name != "nt"
                else "Set-Content -Path '{summary_file}' -Value 'thread event done'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    'agent': 'custom',
                    'command': command,
                    'prompt': '线程事件流验证',
                    'autoStart': True,
                },
            ).json()
            run_payload = self._wait_run(client, created['id'])
            self.assertEqual(run_payload['status'], 'passed')

            with client.stream('GET', f"/api/v2/threads/{thread['id']}/events") as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())
            self.assertIn('data: ', body)
            self.assertIn('"thread"', body)
            self.assertIn('"runs"', body)

    def test_message_endpoint_supports_sse_via_accept_header(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Message accept stream project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Accept SSE 线程'},
            ).json()

            with client.stream(
                'POST',
                f"/api/v2/threads/{thread['id']}/messages",
                headers={'Accept': 'text/event-stream'},
                json={
                    'content': '只通过主入口接收 SSE',
                    'createRun': False,
                },
            ) as response:
                self.assertEqual(response.status_code, 200)
                body = ''.join(response.iter_text())

            self.assertIn('event: message-saved', body)
            self.assertIn('event: assistant-reply-delta', body)
            self.assertIn('event: assistant-reply-complete', body)
            self.assertIn('event: result', body)
            self.assertIn('event: done', body)
            self.assertIn('我已把这条消息记入当前 Thread', body)

    def test_llm_router_function_call_records_decision_without_run(self):
        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    'choices': [
                        {
                            'message': {
                                'tool_calls': [
                                    {
                                        'type': 'function',
                                        'function': {
                                            'name': 'plan_kam_response',
                                            'arguments': (
                                                '{'
                                                '"should_run": false, '
                                                '"mode": "chat", '
                                                '"agents": [], '
                                                '"preferences": [], '
                                                '"decisions": ['
                                                '{"question": "状态管理方案选哪个？", "decision": "Zustand", "reasoning": "足够轻量"}'
                                                '], '
                                                '"learnings": [], '
                                                '"summary": "已记录你的决策，本轮先不执行。"}'
                                            ),
                                        },
                                    }
                                ],
                            },
                        }
                    ]
                }

        previous_key = settings.OPENAI_API_KEY
        settings.OPENAI_API_KEY = 'test-key'
        try:
            with patch('app.services.conversation_router.httpx.post', return_value=FakeResponse()):
                with TestClient(app) as client:
                    project = client.post(
                        '/api/v2/projects',
                        json={'title': 'LLM router project'},
                    ).json()
                    thread = client.post(
                        f"/api/v2/projects/{project['id']}/threads",
                        json={'title': 'LLM router thread'},
                    ).json()

                    posted = client.post(
                        f"/api/v2/threads/{thread['id']}/messages",
                        json={
                            'content': '状态管理就定 Zustand，先不要执行。',
                        },
                    )
                    self.assertEqual(posted.status_code, 200)
                    payload = posted.json()
                    self.assertEqual(payload['routerMode'], 'llm')
                    self.assertEqual(payload['runs'], [])
                    self.assertIn('已记录你的决策', payload['reply']['content'])

                    decisions = client.get(
                        '/api/v2/memory/decisions',
                        params={'project_id': project['id']},
                    )
                    self.assertEqual(decisions.status_code, 200)
                    self.assertEqual(len(decisions.json()['decisions']), 1)
                    self.assertEqual(decisions.json()['decisions'][0]['decision'], 'Zustand')
        finally:
            settings.OPENAI_API_KEY = previous_key

    def test_passed_run_auto_creates_project_learning(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Auto learning project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': '自动 learning'},
            ).json()

            command = (
                "printf '%s' '实现了 token refresh，并处理 race condition 和并发覆盖。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '实现了 token refresh，并处理 race condition 和并发覆盖。'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/runs",
                json={
                    'agent': 'custom',
                    'command': command,
                    'prompt': '实现 refresh token',
                    'autoStart': True,
                },
            ).json()
            run_payload = self._wait_run(client, created['id'])
            self.assertEqual(run_payload['status'], 'passed')

            learnings = client.get('/api/v2/memory/learnings', params={'project_id': project['id']})
            self.assertEqual(learnings.status_code, 200)
            contents = [item['content'] for item in learnings.json()['learnings']]
            self.assertTrue(any('race condition' in content for content in contents))

    def test_adopt_compare_run_records_decision_memory(self):
        with TestClient(app) as client:
            project = client.post(
                '/api/v2/projects',
                json={'title': 'Adopt compare project'},
            ).json()
            thread = client.post(
                f"/api/v2/projects/{project['id']}/threads",
                json={'title': 'Compare adopt'},
            ).json()

            command_a = (
                "printf '%s' '方案 A：实现 refresh token，并增加 race condition 保护。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '方案 A：实现 refresh token，并增加 race condition 保护。'"
            )
            command_b = (
                "printf '%s' '方案 B：实现 refresh token，并增加缓存。' > '{summary_file}'"
                if os.name != 'nt'
                else "Set-Content -Path '{summary_file}' -Value '方案 B：实现 refresh token，并增加缓存。'"
            )
            created = client.post(
                f"/api/v2/threads/{thread['id']}/compare",
                json={
                    'prompt': '分别实现 refresh token 流程并对比',
                    'agents': [
                        {'agent': 'custom', 'label': '方案 A', 'command': command_a},
                        {'agent': 'custom', 'label': '方案 B', 'command': command_b},
                    ],
                    'autoStart': True,
                },
            )
            self.assertEqual(created.status_code, 200)
            payload = created.json()

            first = self._wait_run(client, payload['runs'][0]['id'])
            second = self._wait_run(client, payload['runs'][1]['id'])
            self.assertEqual(first['status'], 'passed')
            self.assertEqual(second['status'], 'passed')

            adopted = client.post(f"/api/v2/runs/{payload['runs'][0]['id']}/adopt")
            self.assertEqual(adopted.status_code, 200)

            decisions = client.get('/api/v2/memory/decisions', params={'project_id': project['id']})
            self.assertEqual(decisions.status_code, 200)
            rows = decisions.json()['decisions']
            self.assertTrue(any(item['question'] == '分别实现 refresh token 流程并对比' for item in rows))
            self.assertTrue(any(item['decision'] == '方案 A' for item in rows))


if __name__ == "__main__":
    unittest.main()
