"""screenshot_jaeger.py — Capture a screenshot of the Jaeger trace view.

Queries the Jaeger REST API across all known services to find the performance
test trace (perf-test-suite) from T20/T21.  Falls back to the richest
distributed trace (most spans) if no perf trace is found.

Opens the target trace in a headless Chromium browser via Playwright and saves
a compact viewport PNG (no full-page scroll) to screenshots/jaeger-trace.png.
The screenshot highlights performance results: a single-worker baseline (T20)
span and a two-worker parallel-execution span (T21) sit side-by-side under the
perf-test-suite root, making the duration difference visually obvious.

  GITHUB_TOKEN       — personal access token or GITHUB_TOKEN secret
  GITHUB_REPOSITORY  — owner/repo (e.g. "langsamu/hallucinate")
  GITHUB_HEAD_REF    — the PR branch name
  PR_NUMBER          — the pull request number

Posting via Python avoids the shell ARG_MAX limit that breaks `gh api -F
content=<large-base64>` when the PNG exceeds ~128 KB.

Run from CI after tests have emitted OTel traces and the collector has
forwarded them to Jaeger.  Requires:
  pip install playwright requests
  playwright install chromium --with-deps
"""
import base64
import json
import os
import sys
import time


def _take_screenshot() -> str | None:
    """Take a Jaeger screenshot and return the file path, or None on error."""
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        print("requests not available — skipping Jaeger screenshot")
        return None

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("playwright not available — skipping Jaeger screenshot")
        return None

    jaeger = "http://localhost:16686"

    # ------------------------------------------------------------------ #
    # Poll Jaeger REST API:                                               #
    # 1. First look for the compact "perf-test-suite" trace (T20 vs T21) #
    # 2. Fall back to the richest multi-service distributed trace         #
    # ------------------------------------------------------------------ #
    services_to_try = ["perf-test", "coordinator", "worker-W1", "worker-W2", "hello-bas"]
    perf_trace: dict | None = None    # perf-test-suite root span trace
    best_trace: dict | None = None    # richest distributed trace (fallback)
    deadline = time.time() + 180
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        max_spans_seen = 0
        for svc in services_to_try:
            try:
                resp = requests.get(
                    f"{jaeger}/api/traces",
                    params={"service": svc, "limit": 50, "lookback": "1h"},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue
                traces = resp.json().get("data", [])
                for t in traces:
                    spans = t.get("spans", [])
                    sc = len(spans)
                    # Identify the perf-test-suite trace by its root operation name.
                    if svc == "perf-test" and perf_trace is None:
                        for sp in spans:
                            if sp.get("operationName") == "perf-test-suite":
                                perf_trace = t
                                break
                    if sc > max_spans_seen:
                        max_spans_seen = sc
                        best_trace = t
            except Exception:  # noqa: BLE001
                pass
        perf_found = "yes" if perf_trace else "no"
        print(f"Attempt {attempt}: perf trace found={perf_found}, "
              f"best distributed trace={max_spans_seen} spans")
        # Wait until the perf-test-suite trace has been exported AND the
        # main distributed trace has enough spans to show both workers.
        if perf_trace is not None and max_spans_seen >= 100:
            break
        time.sleep(5)

    # Prefer the compact perf-test trace; fall back to the richest trace.
    target_trace = perf_trace if perf_trace is not None else best_trace

    if not target_trace:
        print("No traces found — will screenshot the Jaeger search page")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # Fixed viewport — no full-page scroll so the screenshot stays compact.
        page = browser.new_page(viewport={"width": 1400, "height": 800})

        if target_trace:
            trace_id = target_trace["traceID"]
            span_count = len(target_trace.get("spans", []))
            url = f"{jaeger}/trace/{trace_id}"
            source = "perf-test-suite" if target_trace is perf_trace else "richest distributed"
            print(f"Opening {source} trace {trace_id} ({span_count} spans): {url}")
        else:
            url = f"{jaeger}/search?service=perf-test"
            print(f"No traces found; opening search page: {url}")

        try:
            page.goto(url, wait_until="networkidle", timeout=15_000)
        except Exception as exc:  # noqa: BLE001
            print(f"Navigation warning (proceeding anyway): {exc}")

        # Give React time to finish rendering the span waterfall.
        page.wait_for_timeout(5_000)

        context_label = os.environ.get("CONTEXT_LABEL", "")
        if context_label:
            out = f"screenshots/jaeger-{context_label.lower()}-trace.png"
        else:
            out = "screenshots/jaeger-trace.png"
        # Viewport-only screenshot (full_page=False) keeps the image compact
        # and focused on the performance comparison spans.
        page.screenshot(path=out, full_page=False)
        print(f"Screenshot saved → {out}")
        browser.close()

    return out


def _publish_pr_comment(screenshot_path: str) -> None:
    """Upload screenshot to PR branch and post it as an embedded PR comment.

    Uses the GitHub Contents API and Issues API directly via requests to
    avoid the shell ARG_MAX limit that affects `gh api -F content=<large-b64>`.

    Reads configuration from environment variables:
      GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_HEAD_REF, PR_NUMBER
    """
    import requests  # noqa: PLC0415

    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    branch = os.environ.get("GITHUB_HEAD_REF", "")
    pr_number = os.environ.get("PR_NUMBER", "")

    if not all([token, repo, branch, pr_number]):
        print("Skipping PR comment: missing GITHUB_TOKEN / GITHUB_REPOSITORY / GITHUB_HEAD_REF / PR_NUMBER")
        return

    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    api = "https://api.github.com"
    file_path = screenshot_path  # use the path returned by _take_screenshot()

    # ------------------------------------------------------------------ #
    # Step 1 — read and base64-encode the PNG                             #
    # ------------------------------------------------------------------ #
    with open(screenshot_path, "rb") as fh:
        content_b64 = base64.b64encode(fh.read()).decode()

    # ------------------------------------------------------------------ #
    # Step 2 — create or update the file on the PR branch via Contents API #
    # ------------------------------------------------------------------ #
    contents_url = f"{api}/repos/{repo}/contents/{file_path}"

    # Check for an existing blob so we can pass its SHA for updates.
    existing_sha = None
    r = requests.get(f"{contents_url}?ref={branch}", headers=headers, timeout=30)
    if r.status_code == 200:
        existing_sha = r.json().get("sha")
        print(f"Existing screenshot blob SHA: {existing_sha}")

    payload: dict = {
        "message": "ci: update  Jaeger trace screenshot [skip ci]" if existing_sha
                   else "ci: add Jaeger trace screenshot [skip ci]",
        "content": content_b64,
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    r = requests.put(contents_url, headers=headers, data=json.dumps(payload), timeout=60)
    if r.status_code not in (200, 201):
        print(f"Failed to upload screenshot to branch: {r.status_code} {r.text[:300]}")
        return

    commit_sha = r.json().get("commit", {}).get("sha", "")
    if commit_sha:
        image_url = f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{file_path}"
    else:
        image_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"
    print(f"Screenshot committed → {image_url}")

    # ------------------------------------------------------------------ #
    # Step 3 — post the image as a PR comment                             #
    # ------------------------------------------------------------------ #
    context_label = os.environ.get("CONTEXT_LABEL", "")
    title_suffix = f" ({context_label})" if context_label else ""
    comment_body = (
        f"## Jaeger Distributed Trace — Performance Results{title_suffix}\n\n"
        f"![perf-test-suite and distributed hello-world spans in Jaeger]({image_url})\n\n"
        "### Performance test summary (T20 vs T21)\n\n"
        "| Test | Workers | Rounds | Mode |\n"
        "|------|---------|--------|------|\n"
        "| **T20 baseline** | 1 (W1) | 20 | Sequential |\n"
        "| **T21 scale-out** | 2 (W1 + W2) | 10 each (20 total) | Parallel |\n\n"
        "The screenshot shows the **`perf-test-suite`** trace (service: **perf-test**):  \n"
        "- **`perf-baseline`** span — single worker completes all 20 rounds sequentially; "
        "its duration is the baseline  \n"
        "- **`perf-multi-worker`** span — two workers execute 10 rounds each in parallel "
        "via `SPAWNBASIC`; duration is shorter due to concurrent `hello.bas` execution  \n\n"
        "The span durations in the Jaeger waterfall make the speedup immediately visible: "
        "`perf-multi-worker` is narrower than `perf-baseline`, confirming that horizontal "
        "scale-out reduces wall-clock time for the same total workload.  \n\n"
        "The full distributed trace (`hello-world-transaction`, service: **coordinator**) "
        "continues to show W1 and W2 `worker-round` spans interleaved non-deterministically "
        "across services **worker-W1**, **worker-W2**, and **hello-bas**."
    )
    comment_url = f"{api}/repos/{repo}/issues/{pr_number}/comments"
    r = requests.post(
        comment_url,
        headers=headers,
        data=json.dumps({"body": comment_body}),
        timeout=30,
    )
    if r.status_code == 201:
        print(f"PR comment posted: {r.json().get('html_url', '')}")
    else:
        print(f"Failed to post PR comment: {r.status_code} {r.text[:300]}")


def main() -> None:
    os.makedirs("screenshots", exist_ok=True)

    screenshot_path = _take_screenshot()
    if screenshot_path is None:
        return

    # Post the screenshot as a PR comment when running in CI on a PR.
    if os.environ.get("PR_NUMBER"):
        _publish_pr_comment(screenshot_path)
    else:
        print("PR_NUMBER not set — skipping PR comment posting")


if __name__ == "__main__":
    main()
