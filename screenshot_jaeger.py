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

    # Allow Jaeger time to receive and index all forwarded spans before querying.
    time.sleep(5)

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
    # Query Jaeger REST API for hello-bas traces.                         #
    # Pick the trace with the most spans so the nesting is clearly shown. #
    # ------------------------------------------------------------------ #
    traces: list = []
    try:
        resp = requests.get(
            f"{jaeger}/api/traces",
            params={"service": "hello-bas", "limit": 20, "lookback": "1h"},
            timeout=10,
        )
        resp.raise_for_status()
        traces = resp.json().get("data", [])
        print(f"Jaeger returned {len(traces)} trace(s) for hello-bas")
    except Exception as exc:  # noqa: BLE001
        print(f"Could not reach Jaeger API: {exc}")

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
        page.wait_for_timeout(3_000)

        out = "screenshots/jaeger-trace.png"
        page.screenshot(path=out, full_page=False)
        print(f"Screenshot saved → {out}")
        browser.close()


if __name__ == "__main__":
    main()
