import sys
import unittest

from basic_test_framework import hello_bas_line_coverage


def main() -> int:
    suite = unittest.defaultTestLoader.discover(".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    covered, total, percent, missing = hello_bas_line_coverage()
    print(f"hello.bas line coverage: {covered}/{total} ({percent:.1f}%)")
    if missing:
        print(f"Missing hello.bas lines: {', '.join(str(line) for line in missing)}")

    return 0 if result.wasSuccessful() and percent == 100.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
