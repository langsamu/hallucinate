"""screenshot_jaeger.py — Capture a screenshot of the Jaeger trace view.

Queries the Jaeger REST API for the hello-bas service, finds the richest
trace (most spans — the one that best shows the nested span hierarchy),
then opens that trace in a headless Chromium browser via Playwright and
saves a PNG screenshot to screenshots/jaeger-trace.png.

Run from CI after tests have emitted OTel traces and the collector has
forwarded them to Jaeger.  Requires:
  pip install playwright requests
  playwright install chromium --with-deps
"""
import os
import sys
import time


def main() -> None:
    os.makedirs("screenshots", exist_ok=True)

    try:
        import requests  # noqa: PLC0415
    except ImportError:
        print("requests not available — skipping Jaeger screenshot")
        sys.exit(0)

    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except ImportError:
        print("playwright not available — skipping Jaeger screenshot")
        sys.exit(0)

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


if __name__ == "__main__":
    main()
