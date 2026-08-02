"""五語言基準（FR-037、FR-045）。

每種語言各一組「正常執行」與「編譯／語法錯誤」測試，斷言 `COMPLETED`
與 `COMPILE_ERROR` 的判定正確（contracts/sandbox-runner.md「五語言基準」）。

編譯錯誤不得被當成系統故障——它是應徵者可修正的一般結果（FR-045）。
"""

from __future__ import annotations

import pytest

from backend.src.models.question import Language
from backend.src.models.report import TerminationReason

pytestmark = pytest.mark.security

# 每組：語言、可正常執行的程式、預期輸出、語法／編譯錯誤的程式
CASES = [
    (
        Language.PYTHON,
        "a, b = map(int, input().split())\nprint(a + b)\n",
        "8",
        "def broken(\n",
    ),
    (
        Language.JAVASCRIPT,
        """
const data = require('fs').readFileSync(0, 'utf8').trim().split(/\\s+/);
console.log(Number(data[0]) + Number(data[1]));
""",
        "8",
        "function broken( {",
    ),
    (
        Language.GO,
        """
package main

import "fmt"

func main() {
    var a, b int
    fmt.Scan(&a, &b)
    fmt.Println(a + b)
}
""",
        "8",
        "package main\nfunc main() { this is not go }",
    ),
    (
        Language.JAVA,
        """
import java.util.Scanner;

public class Main {
    public static void main(String[] args) {
        Scanner scanner = new Scanner(System.in);
        System.out.println(scanner.nextInt() + scanner.nextInt());
    }
}
""",
        "8",
        "public class Main { void main( }",
    ),
    (
        Language.CPP,
        """
#include <iostream>
int main() {
    int a, b;
    std::cin >> a >> b;
    std::cout << a + b << std::endl;
    return 0;
}
""",
        "8",
        "int main( { return }",
    ),
]


@pytest.mark.parametrize(
    ("language", "code", "expected", "_broken"), CASES, ids=[str(c[0]) for c in CASES]
)
async def test_normal_execution_completes(run, language, code, expected, _broken):
    result = await run(code, language, stdin="3 5\n")
    assert result.termination_reason is TerminationReason.COMPLETED, result.stderr
    assert result.stdout.strip() == expected
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("language", "_code", "_expected", "broken"), CASES, ids=[str(c[0]) for c in CASES]
)
async def test_syntax_error_is_reported_as_compile_error(run, language, _code, _expected, broken):
    result = await run(broken, language, stdin="3 5\n")
    assert (
        result.termination_reason is TerminationReason.COMPILE_ERROR
    ), f"{language} 的語法錯誤應判定為 COMPILE_ERROR，實際為 {result.termination_reason}"
    assert result.stderr.strip() != "", "編譯錯誤訊息必須回傳給應徵者（FR-045）"


@pytest.mark.parametrize("language", [case[0] for case in CASES])
async def test_language_version_is_reported(runner, language):
    """語言版本必須明確固定並對應徵者顯示（FR-037）。"""
    version = runner.language_version(language)
    assert version, f"{language} 必須有固定的版本標示"


@pytest.mark.parametrize(
    ("language", "code", "expected", "_broken"), CASES, ids=[str(c[0]) for c in CASES]
)
async def test_runtime_error_is_not_a_compile_error(run, language, code, expected, _broken):
    """非零退出碼仍屬 COMPLETED——那是應徵者的程式行為，不是系統故障（FR-044）。"""
    result = await run(code, language, stdin="not-a-number\n")
    assert result.termination_reason in (
        TerminationReason.COMPLETED,
        TerminationReason.TIMEOUT,
    )
