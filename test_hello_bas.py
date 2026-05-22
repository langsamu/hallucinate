import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
HELLO_BAS = REPO_ROOT / "hello.bas"


def parse_basic_lines(path: Path) -> dict[int, str]:
    program = {}
    for raw_line in path.read_text().splitlines():
        if not raw_line.strip():
            continue
        line_no_text, statement = raw_line.strip().split(" ", 1)
        program[int(line_no_text)] = statement.strip()
    return program


class HelloBasProgramTests(unittest.TestCase):
    def test_program_has_expected_line_numbers(self) -> None:
        program = parse_basic_lines(HELLO_BAS)
        self.assertEqual(
            sorted(program.keys()),
            [10, 20, 30, 40, 50, 60, 200, 210, 220, 230, 240, 900, 910],
        )

    def test_main_loop_initializes_and_loops(self) -> None:
        program = parse_basic_lines(HELLO_BAS)
        self.assertEqual(program[20], "ON ERROR GOTO 900")
        self.assertEqual(program[30], 'MESSAGE$ = "HELLO WORLD"')
        self.assertEqual(program[40], "ITERATION% = 0")
        self.assertEqual(program[50], "GOSUB 200")
        self.assertEqual(program[60], "GOTO 50")

    def test_subroutine_prints_and_resets_counter(self) -> None:
        program = parse_basic_lines(HELLO_BAS)
        self.assertEqual(
            program[200],
            'IF LEN(MESSAGE$) = 0 THEN MESSAGE$ = "HELLO WORLD"',
        )
        self.assertEqual(program[210], 'PRINT ITERATION%; " "; MESSAGE$')
        self.assertEqual(program[220], "ITERATION% = ITERATION% + 1")
        self.assertEqual(program[230], "IF ITERATION% > 9999 THEN ITERATION% = 0")
        self.assertEqual(program[240], "RETURN")

    def test_error_handler_recovers_to_loop(self) -> None:
        program = parse_basic_lines(HELLO_BAS)
        self.assertEqual(program[900], 'MESSAGE$ = "HELLO WORLD"')
        self.assertEqual(program[910], "RESUME 50")


if __name__ == "__main__":
    unittest.main()
