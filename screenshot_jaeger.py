"""screenshot_jaeger.py — Capture a screenshot of the Jaeger trace view.

Queries the Jaeger REST API across all known services to find the richest
distributed trace (most spans), then opens that trace in a headless Chromium
browser via Playwright and saves a PNG screenshot to screenshots/jaeger-trace.png.

After the coordinator-to-worker traceparent propagation, the ideal trace has:
  hello-world-transaction (coordinator) ← root span, colour A
    worker-lifecycle (worker-W1)        ← colour B
      worker-register
      worker-round
        worker-get-work
        worker-run-hello
          hello-world-iteration (hello-bas)  ← colour D
            hello-world-guard / hello-world-print / hello-world-advance
        worker-2pc-prepare / worker-2pc-commit
    worker-lifecycle (worker-W2)        ← colour C
      … same structure …

We search across all services (hello-bas, coordinator, worker-W1, worker-W2)
so the multi-span root transaction is found regardless of which service owns
the most spans.  We wait until at least 10 spans appear so the screenshot
captures the full multi-colour distributed trace waterfall.
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
    # Poll Jaeger REST API across all known services for the richest       #
    # distributed trace (most spans).  Coordinator-to-worker propagation  #
    # means the hello-world-transaction trace spans multiple services;     #
    # searching all of them gives us the best chance of finding it.        #
    # ------------------------------------------------------------------ #
    services_to_try = ["coordinator", "worker-W1", "worker-W2", "hello-bas"]
    best_trace: dict | None = None
    deadline = time.time() + 90
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
                    sc = len(t.get("spans", []))
                    if sc > max_spans_seen:
                        max_spans_seen = sc
                        best_trace = t
            except Exception:  # noqa: BLE001
                pass
        print(f"Attempt {attempt}: best trace found has {max_spans_seen} span(s)")
        # Wait for a trace that shows the full distributed structure.
        # With 2 workers (W1 + W2) doing 2 rounds each and 5 hello prints per round:
        #   hello-world-transaction (coordinator, root)         1
        #   worker-round x4 (W1×2 + W2×2, direct children)     4
        #     worker-get-work x4                                4
        #     worker-run-hello x4                               4
        #       hello-world-iteration x4x5=20                  20
        #         hello-world-{guard,print,advance} x60        60
        #     worker-2pc-prepare x4                             4
        #     worker-2pc-commit x4                              4
        # Total: ~101 spans.  Require ≥ 80 to ensure multiple workers' spans
        # are present before the screenshot is taken.
        if max_spans_seen >= 80:
            break
        time.sleep(5)

    if not best_trace:
        print("No multi-span distributed trace found — will screenshot the search page")

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        if best_trace:
            trace_id = best_trace["traceID"]
            span_count = len(best_trace.get("spans", []))
            url = f"{jaeger}/trace/{trace_id}"
            print(f"Opening trace {trace_id} ({span_count} spans): {url}")
        else:
            url = f"{jaeger}/search?service=hello-bas"
            print(f"No traces found; opening search page: {url}")

        try:
            page.goto(url, wait_until="networkidle", timeout=15_000)
        except Exception as exc:  # noqa: BLE001
            print(f"Navigation warning (proceeding anyway): {exc}")

        # Give React time to finish rendering the full span waterfall.
        # Extra time is needed for large distributed traces with many spans.
        page.wait_for_timeout(8_000)

        out = "screenshots/jaeger-trace.png"
        page.screenshot(path=out, full_page=True)
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
    file_path = "screenshots/jaeger-trace.png"

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
    comment_body = (
        "## Jaeger Distributed Trace Visualization\n\n"
        f"![distributed hello-world spans in Jaeger]({image_url})\n\n"
        "*Distributed trace: the coordinator's `hello-world-transaction` root span "
        "(service: **coordinator**) contains `worker-round` spans from W1 and W2 "
        "running **in parallel** (services: **worker-W1**, **worker-W2**), "
        "each doing multiple rounds that nest `worker-get-work` → `worker-run-hello` → "
        "`hello-world-iteration` → `hello-world-guard` / `hello-world-print` / "
        "`hello-world-advance` grandchild spans (service: **hello-bas**).  "
        "W3C traceparent from `/register` links all worker spans back to the "
        "single coordinator-owned root, showing the distributed hello-world "
        "computation — with both workers printing hello world concurrently — "
        "in one unified multi-colour trace waterfall:  \n"
        "`hello-world-transaction` (coordinator)  \n"
        "├── `worker-round` ×2 (worker-W1, 2 rounds)  \n"
        "│   ├── `worker-get-work`  \n"
        "│   ├── `worker-run-hello` → `hello-world-iteration` ×5 (hello-bas)  \n"
        "│   └── `worker-2pc-prepare` / `worker-2pc-commit`  \n"
        "└── `worker-round` ×2 (worker-W2, 2 rounds)  \n"
        "    └── … same structure …*"
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
