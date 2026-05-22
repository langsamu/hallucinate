import sys
import unittest

from basic_test_framework import hello_bas_line_coverage, hello_bas_transpiled_javascript


def main() -> int:
    suite = unittest.defaultTestLoader.discover(".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print("hello.bas transpiled JavaScript:")
    print(hello_bas_transpiled_javascript())
    covered, total, percent, missing = hello_bas_line_coverage()
    print(f"hello.bas line coverage: {covered}/{total} ({percent:.1f}%)")
    if missing:
        print(f"Missing hello.bas lines: {', '.join(str(line) for line in missing)}")

    return 0 if result.wasSuccessful() and percent == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
