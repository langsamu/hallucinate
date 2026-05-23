import unittest

from basic_test_framework import (
    hello_bas_line_coverage,
    hello_bas_transpiled_js_line_coverage,
    hello_bas_transpiled_javascript,
    run_hello_program_transpiled_js,
)


def main() -> int:
    suite = unittest.defaultTestLoader.discover(".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("hello.bas transpiled JavaScript:")
    print(hello_bas_transpiled_javascript())
    print("transpiled JS program output (first 5 iterations):")
    js_output = run_hello_program_transpiled_js(stop_after_prints=5)
    for line in js_output["output"]:
        print(line)
    covered, total, percent, missing = hello_bas_line_coverage()
    js_covered, js_total, js_percent, js_missing = hello_bas_transpiled_js_line_coverage()
    print(f"hello.bas line coverage: {covered}/{total} ({percent:.1f}%)")
    print(f"transpiled JS mapped coverage: {js_covered}/{js_total} ({js_percent:.1f}%)")
    if missing:
        print(f"Missing hello.bas lines (BASIC runtime): {', '.join(str(line) for line in missing)}")
    if js_missing:
        print(f"Missing hello.bas lines (transpiled JS runtime): {', '.join(str(line) for line in js_missing)}")

    return 0 if result.wasSuccessful() and percent == 100.0 and js_percent == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
