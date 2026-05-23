"""screenshot_jaeger.py — Capture a screenshot of the Jaeger trace view.

Queries the Jaeger REST API for the hello-bas service, finds the richest
trace (most spans — the one that best shows the nested span hierarchy),
then opens that trace in a headless Chromium browser via Playwright and
saves a PNG screenshot to screenshots/jaeger-trace.png.

If the following environment variables are set, the screenshot is also
uploaded to the PR branch and posted as an embedded-image PR comment:
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
    # Poll Jaeger REST API for hello-bas traces, with retries.            #
    # Traces may take several seconds to be forwarded from the OTel       #
    # Collector to Jaeger after the test run completes.                   #
    # Poll for up to 60 seconds so we don't screenshot an empty UI.       #
    # ------------------------------------------------------------------ #
    traces: list = []
    deadline = time.time() + 60
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            resp = requests.get(
                f"{jaeger}/api/traces",
                params={"service": "hello-bas", "limit": 20, "lookback": "1h"},
                timeout=10,
            )
            resp.raise_for_status()
            traces = resp.json().get("data", [])
            print(f"Attempt {attempt}: Jaeger returned {len(traces)} trace(s) for hello-bas")
            if traces:
                break
        except Exception as exc:  # noqa: BLE001
            print(f"Attempt {attempt}: Could not reach Jaeger API: {exc}")
        time.sleep(3)

    if not traces:
        print("No traces found in Jaeger after polling — will screenshot the search page")

    # Prefer the trace that has the most spans (best shows nesting).
    best = max(traces, key=lambda t: len(t.get("spans", [])), default=None)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 900})

        if best:
            trace_id = best["traceID"]
            span_count = len(best.get("spans", []))
            url = f"{jaeger}/trace/{trace_id}"
            print(f"Opening trace {trace_id} ({span_count} spans): {url}")
        else:
            url = f"{jaeger}/search?service=hello-bas"
            print(f"No traces found; opening search page: {url}")

        try:
            page.goto(url, wait_until="networkidle", timeout=15_000)
        except Exception as exc:  # noqa: BLE001
            print(f"Navigation warning (proceeding anyway): {exc}")

        # Give React time to finish rendering the span waterfall.
        page.wait_for_timeout(5_000)

        out = "screenshots/jaeger-trace.png"
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
        "message": "ci: update Jaeger trace screenshot [skip ci]" if existing_sha
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
        "## Jaeger Trace Visualization\n\n"
        f"![hello-world nested spans in Jaeger]({image_url})\n\n"
        "*Trace showing `hello-world-iteration` as the root span with "
        "`hello-world-initialize`, `hello-world-guard`, `hello-world-print`, "
        "and `hello-world-advance` as nested child spans.*"
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
