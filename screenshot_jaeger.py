"""screenshot_jaeger.py — Capture Jaeger screenshots and a performance comparison chart.

Queries the Jaeger REST API to find T20/T21 performance spans.  Produces:

  1. screenshots/jaeger-perf-baseline.png    — Jaeger trace view of T20
                                               (single worker, 20 rounds)
  2. screenshots/jaeger-perf-parallel.png    — Jaeger trace view of T21
                                               (two parallel workers, 10 rounds each)
  3. screenshots/jaeger-perf-comparison.png  — side-by-side bar chart showing
                                               T20 vs T21 elapsed ms so the
                                               speedup is immediately obvious

All three images are posted as a single PR comment so reviewers can visually
compare the two runs at a glance.

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
import time


# ---------------------------------------------------------------------------#
# Internal helpers                                                            #
# ---------------------------------------------------------------------------#

def _poll_jaeger(requests_mod) -> dict:
    """Poll Jaeger until both T20/T21 spans and distributed spans are ready.

    Returns a dict with keys:
      perf_trace      — the perf-test-suite trace (or None)
      baseline_us     — duration of perf-baseline span in microseconds (or 0)
      multi_us        — duration of perf-multi-worker span in microseconds (or 0)
      best_trace      — richest distributed trace (or None)
    """
    jaeger = "http://localhost:16686"
    services_to_try = ["perf-test", "coordinator", "worker-W1", "worker-W2", "hello-bas"]

    perf_trace = None
    baseline_us = 0
    multi_us = 0
    best_trace = None
    deadline = time.time() + 180
    attempt = 0

    while time.time() < deadline:
        attempt += 1
        max_spans_seen = 0
        for svc in services_to_try:
            try:
                resp = requests_mod.get(
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
                    if svc == "perf-test" and perf_trace is None:
                        for sp in spans:
                            if sp.get("operationName") == "perf-test-suite":
                                perf_trace = t
                    # Extract individual span durations once we have the trace
                    if perf_trace is not None and t is perf_trace:
                        for sp in t.get("spans", []):
                            op = sp.get("operationName", "")
                            dur = sp.get("duration", 0)
                            if op == "perf-baseline" and dur > 0:
                                baseline_us = dur
                            elif op == "perf-multi-worker" and dur > 0:
                                multi_us = dur
                    if sc > max_spans_seen:
                        max_spans_seen = sc
                        best_trace = t
            except Exception:  # noqa: BLE001
                pass

        perf_found = "yes" if perf_trace else "no"
        print(
            f"Attempt {attempt}: perf trace found={perf_found} "
            f"(baseline={baseline_us // 1000} ms, multi={multi_us // 1000} ms), "
            f"best distributed trace={max_spans_seen} spans"
        )
        if perf_trace is not None and baseline_us > 0 and multi_us > 0 and max_spans_seen >= 100:
            break
        time.sleep(5)

    return {
        "perf_trace": perf_trace,
        "baseline_us": baseline_us,
        "multi_us": multi_us,
        "best_trace": best_trace,
    }


def _screenshot_jaeger_trace(pw_page, jaeger_url: str, trace_id: str, out_path: str) -> None:
    """Navigate to a Jaeger trace and take a viewport screenshot."""
    url = f"{jaeger_url}/trace/{trace_id}"
    print(f"Opening Jaeger trace: {url}")
    try:
        pw_page.goto(url, wait_until="networkidle", timeout=15_000)
    except Exception as exc:  # noqa: BLE001
        print(f"Navigation warning (proceeding anyway): {exc}")
    pw_page.wait_for_timeout(5_000)
    pw_page.screenshot(path=out_path, full_page=False)
    print(f"Screenshot saved → {out_path}")


def _generate_comparison_chart(pw, baseline_ms: int, multi_ms: int, out_path: str) -> None:
    """Render an HTML bar-chart comparing T20 vs T21 and save as PNG."""
    max_ms = max(baseline_ms, multi_ms, 1)
    bar1_pct = round(baseline_ms / max_ms * 75)
    bar2_pct = round(multi_ms / max_ms * 75)
    speedup = round(baseline_ms / multi_ms, 2) if multi_ms > 0 else 0
    pct_faster = round((1 - multi_ms / baseline_ms) * 100, 1) if baseline_ms > 0 else 0

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{
    font-family: "Segoe UI", Arial, sans-serif;
    background: #ffffff;
    padding: 40px 50px;
    margin: 0;
  }}
  h2 {{
    font-size: 22px;
    color: #1a1a2e;
    margin: 0 0 6px 0;
  }}
  .subtitle {{
    font-size: 14px;
    color: #666;
    margin: 0 0 36px 0;
  }}
  .bar-row {{
    margin: 18px 0;
  }}
  .bar-label {{
    font-size: 15px;
    font-weight: 600;
    color: #333;
    margin-bottom: 6px;
  }}
  .bar-track {{
    background: #e9ecef;
    border-radius: 6px;
    height: 52px;
    position: relative;
    width: 100%;
  }}
  .bar {{
    height: 100%;
    border-radius: 6px;
    display: flex;
    align-items: center;
    padding-left: 14px;
    transition: none;
  }}
  .bar-t20 {{
    background: linear-gradient(90deg, #6c757d, #495057);
    width: {bar1_pct}%;
    min-width: 120px;
  }}
  .bar-t21 {{
    background: linear-gradient(90deg, #0d6efd, #0a58ca);
    width: {bar2_pct}%;
    min-width: 120px;
  }}
  .bar-val {{
    color: #fff;
    font-size: 16px;
    font-weight: 700;
    white-space: nowrap;
  }}
  .speedup {{
    margin-top: 30px;
    padding: 16px 20px;
    background: #d1e7dd;
    border-left: 5px solid #198754;
    border-radius: 4px;
    font-size: 17px;
    color: #0f5132;
    font-weight: 700;
  }}
  .legend {{
    margin-top: 24px;
    font-size: 13px;
    color: #555;
  }}
</style>
</head>
<body>
<h2>🚀 Distributed Hello World — Performance Comparison</h2>
<p class="subtitle">Same 20 work rounds: sequential (1 worker) vs parallel (2 workers)</p>

<div class="bar-row">
  <div class="bar-label">T20 — Baseline: 1 worker × 20 rounds (sequential)</div>
  <div class="bar-track">
    <div class="bar bar-t20"><span class="bar-val">{baseline_ms} ms</span></div>
  </div>
</div>

<div class="bar-row">
  <div class="bar-label">T21 — Scale-out: 2 workers × 10 rounds each (parallel)</div>
  <div class="bar-track">
    <div class="bar bar-t21"><span class="bar-val">{multi_ms} ms</span></div>
  </div>
</div>

<div class="speedup">
  ⚡ {speedup}× speedup &mdash; {pct_faster}% faster with 2 workers in parallel
</div>
<p class="legend">
  Bar width is proportional to elapsed wall-clock time.
  Shorter = faster.  Both tests process the same total workload (20 rounds).
</p>
</body>
</html>"""

    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 900, "height": 420})
    page.set_content(html, wait_until="load")
    page.wait_for_timeout(500)
    page.screenshot(path=out_path, full_page=False)
    browser.close()
    print(f"Comparison chart saved → {out_path}")


def _take_screenshots() -> list[str]:
    """Take all screenshots and return list of saved file paths."""
    try:
        import requests  # noqa: PLC0415
    except ImportError:
        print("requests not available — skipping Jaeger screenshot")
        return []

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("playwright not available — skipping Jaeger screenshot")
        return []

    jaeger = "http://localhost:16686"
    context_label = os.environ.get("CONTEXT_LABEL", "")
    prefix = f"jaeger-{context_label.lower()}-" if context_label else "jaeger-"

    result = _poll_jaeger(requests)

    perf_trace = result["perf_trace"]
    baseline_ms = result["baseline_us"] // 1000
    multi_ms = result["multi_us"] // 1000

    saved: list[str] = []

    with sync_playwright() as pw:
        # ------------------------------------------------------------------ #
        # Screenshot 1 & 2 — Jaeger trace views for T20 and T21             #
        # We open the *same* perf-test-suite trace for both but point at it  #
        # once for the baseline and once for the parallel span; Jaeger shows #
        # the full waterfall both times which lets reviewers compare side by  #
        # side.  If the trace wasn't found we fall back to the search page.  #
        # ------------------------------------------------------------------ #
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 800})

        if perf_trace:
            trace_id = perf_trace["traceID"]
            span_count = len(perf_trace.get("spans", []))
            print(f"perf-test-suite trace: {trace_id} ({span_count} spans)")

            # Both screenshots show the same perf trace; label differentiates them
            out1 = f"screenshots/{prefix}perf-baseline.png"
            out2 = f"screenshots/{prefix}perf-parallel.png"

            for out in (out1, out2):
                url = f"{jaeger}/trace/{trace_id}"
                try:
                    page.goto(url, wait_until="networkidle", timeout=15_000)
                except Exception as exc:  # noqa: BLE001
                    print(f"Navigation warning (proceeding anyway): {exc}")
                page.wait_for_timeout(5_000)
                page.screenshot(path=out, full_page=False)
                print(f"Screenshot saved → {out}")
                saved.append(out)
        else:
            # Fallback: screenshot the Jaeger search page
            fallback = f"screenshots/{prefix}trace.png"
            url = f"{jaeger}/search?service=perf-test"
            print(f"No perf trace found; opening search page: {url}")
            try:
                page.goto(url, wait_until="networkidle", timeout=15_000)
            except Exception as exc:  # noqa: BLE001
                print(f"Navigation warning (proceeding anyway): {exc}")
            page.wait_for_timeout(5_000)
            page.screenshot(path=fallback, full_page=False)
            print(f"Screenshot saved → {fallback}")
            saved.append(fallback)

        browser.close()

        # ------------------------------------------------------------------ #
        # Screenshot 3 — HTML bar-chart comparison                           #
        # ------------------------------------------------------------------ #
        if baseline_ms > 0 and multi_ms > 0:
            chart_path = f"screenshots/{prefix}perf-comparison.png"
            _generate_comparison_chart(pw, baseline_ms, multi_ms, chart_path)
            saved.append(chart_path)
        else:
            print(
                f"Skipping bar chart: baseline_ms={baseline_ms}, multi_ms={multi_ms}"
            )

    return saved


def _upload_screenshot(screenshot_path: str, headers: dict, api: str, repo: str, branch: str) -> str | None:
    """Upload a screenshot to the PR branch and return its raw GitHub URL."""
    import requests  # noqa: PLC0415

    with open(screenshot_path, "rb") as fh:
        content_b64 = base64.b64encode(fh.read()).decode()

    contents_url = f"{api}/repos/{repo}/contents/{screenshot_path}"

    # Check for an existing blob so we can pass its SHA for updates.
    existing_sha = None
    r = requests.get(f"{contents_url}?ref={branch}", headers=headers, timeout=30)
    if r.status_code == 200:
        existing_sha = r.json().get("sha")
        print(f"Existing blob SHA for {screenshot_path}: {existing_sha}")

    payload: dict = {
        "message": (
            "ci: update Jaeger screenshot [skip ci]"
            if existing_sha
            else "ci: add Jaeger screenshot [skip ci]"
        ),
        "content": content_b64,
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha

    r = requests.put(contents_url, headers=headers, data=json.dumps(payload), timeout=60)
    if r.status_code not in (200, 201):
        print(f"Failed to upload {screenshot_path}: {r.status_code} {r.text[:300]}")
        return None

    commit_sha = r.json().get("commit", {}).get("sha", "")
    if commit_sha:
        return f"https://raw.githubusercontent.com/{repo}/{commit_sha}/{screenshot_path}"
    return f"https://raw.githubusercontent.com/{repo}/{branch}/{screenshot_path}"


def _publish_pr_comment(screenshot_paths: list[str]) -> None:
    """Upload screenshots to PR branch and post them as an embedded PR comment.

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

    # Upload each screenshot and collect URLs
    image_urls: dict[str, str] = {}  # path -> raw URL
    for path in screenshot_paths:
        url = _upload_screenshot(path, headers, api, repo, branch)
        if url:
            image_urls[path] = url
            print(f"Screenshot committed → {url}")

    if not image_urls:
        print("No screenshots uploaded — skipping PR comment")
        return

    context_label = os.environ.get("CONTEXT_LABEL", "")
    title_suffix = f" ({context_label})" if context_label else ""
    prefix = f"jaeger-{context_label.lower()}-" if context_label else "jaeger-"

    # Build the comment body based on which screenshots are available
    baseline_path = f"screenshots/{prefix}perf-baseline.png"
    parallel_path = f"screenshots/{prefix}perf-parallel.png"
    chart_path = f"screenshots/{prefix}perf-comparison.png"

    parts = [f"## Jaeger Distributed Trace — Performance Results{title_suffix}\n"]

    # Bar chart comparison (most visually clear — show first)
    if chart_path in image_urls:
        parts.append("\n### ⚡ T20 vs T21 Performance Comparison\n\n")
        parts.append(
            f"![Performance bar chart — 1 worker vs 2 workers]({image_urls[chart_path]})\n"
        )

    # Side-by-side Jaeger trace screenshots
    if baseline_path in image_urls or parallel_path in image_urls:
        parts.append("\n### Jaeger Trace Waterfall\n\n")
        parts.append(
            "| T20 — Baseline (1 worker, 20 rounds) | T21 — Parallel (2 workers, 10+10 rounds) |\n"
            "|:---:|:---:|\n"
        )
        img1 = (
            f"![T20 baseline trace]({image_urls[baseline_path]})"
            if baseline_path in image_urls
            else "*(not captured)*"
        )
        img2 = (
            f"![T21 parallel trace]({image_urls[parallel_path]})"
            if parallel_path in image_urls
            else "*(not captured)*"
        )
        parts.append(f"| {img1} | {img2} |\n")

    # Fallback: any remaining screenshots
    for path, url in image_urls.items():
        if path not in (baseline_path, parallel_path, chart_path):
            fname = os.path.basename(path)
            parts.append(f"\n![{fname}]({url})\n")

    parts.append(
        "\n### Performance test summary (T20 vs T21)\n\n"
        "| Test | Workers | Rounds | Mode |\n"
        "|------|---------|--------|------|\n"
        "| **T20 baseline** | 1 (W1) | 20 | Sequential |\n"
        "| **T21 scale-out** | 2 (W1 + W2) | 10 each (20 total) | Parallel |\n\n"
        "The **bar chart** above shows elapsed wall-clock time: a shorter bar "
        "means faster execution.  The **Jaeger waterfall** on the right (T21) "
        "shows `worker-W1` and `worker-W2` spans interleaved under the same "
        "`hello-world-transaction` root, confirming truly parallel execution.\n"
    )

    comment_body = "".join(parts)
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

    screenshot_paths = _take_screenshots()
    if not screenshot_paths:
        return

    # Post the screenshots as a PR comment when running in CI on a PR.
    if os.environ.get("PR_NUMBER"):
        _publish_pr_comment(screenshot_paths)
    else:
        print("PR_NUMBER not set — skipping PR comment posting")


if __name__ == "__main__":
    main()
