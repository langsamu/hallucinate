import unittest

from basic_test_framework import run_hello_program


class HelloBasProgramTests(unittest.TestCase):
    def test_emulator_runs_loop_and_prints_incrementing_iterations(self) -> None:
        runtime = run_hello_program(stop_after_prints=3)
        self.assertEqual(
            runtime.output,
            ["0 HELLO WORLD", "1 HELLO WORLD", "2 HELLO WORLD"],
        )

    def test_guard_replaces_empty_message(self) -> None:
        runtime = run_hello_program(
            start_line=200,
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
            start_line=50,
            initial_vars={"MESSAGE$": "HELLO WORLD", "ITERATION%": 9999},
            stop_after_prints=2,
        )
        self.assertEqual(runtime.output, ["9999 HELLO WORLD", "0 HELLO WORLD"])

    def test_error_handler_recovers_and_resumes_loop(self) -> None:
        runtime = run_hello_program(
            fault_once_lines={210},
            stop_after_prints=1,
        )
        self.assertEqual(runtime.output, ["0 HELLO WORLD"])
        self.assertEqual(runtime.vars["MESSAGE$"], "HELLO WORLD")


if __name__ == "__main__":
    unittest.main()
