import unittest

from basic_test_framework import hello_bas_line_coverage, run_hello_program


class HelloBasProgramTests(unittest.TestCase):
    def test_emulator_runs_loop_and_prints_incrementing_iterations(self) -> None:
        runtime = run_hello_program(stop_after_prints=3)
        self.assertEqual(
            runtime.output,
            ["0 HELLO WORLD", "1 HELLO WORLD", "2 HELLO WORLD"],
        )

    def test_guard_replaces_empty_message(self) -> None:
        runtime = run_hello_program(
            start_line=40,
            initial_vars={"MESSAGE$": "", "ITERATION%": 7},
            stop_after_prints=1,
        )
        self.assertEqual(
            runtime.output,
            ["7 HELLO WORLD"],
        )
        self.assertEqual(runtime.vars["MESSAGE$"], "HELLO WORLD")

    def test_counter_wraps_after_9999(self) -> None:
        runtime = run_hello_program(
            start_line=40,
            initial_vars={"MESSAGE$": "HELLO WORLD", "ITERATION%": 9999},
            stop_after_prints=2,
        )
        self.assertEqual(runtime.output, ["9999 HELLO WORLD", "0 HELLO WORLD"])

    def test_error_handler_recovers_and_resumes_loop(self) -> None:
        runtime = run_hello_program(
            fault_once_lines={2100},
            stop_after_prints=1,
        )
        self.assertEqual(runtime.output, ["0 HELLO WORLD"])
        self.assertEqual(runtime.vars["MESSAGE$"], "HELLO WORLD")

    def test_hello_bas_has_full_line_coverage(self) -> None:
        covered, total, percent, missing = hello_bas_line_coverage()
        self.assertEqual(covered, total)
        self.assertEqual(percent, 100.0)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
