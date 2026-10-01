import pytest

from app.math_tools import CalculationError, calculate, extract_arithmetic


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("What is 12 * (5 + 3)?", "96"),
        ("calculate 0.1 + 0.2", "0.3"),
        ("2^10", "1024"),
        ("-7 / 2", "-3.5"),
    ],
)
def test_supported_arithmetic(query: str, expected: str) -> None:
    assert calculate(query) == expected


@pytest.mark.parametrize(
    "query",
    ["__import__('os').system('echo bad')", "2**100000", "1/0", "2//3"],
)
def test_unsafe_or_undefined_arithmetic_is_rejected(query: str) -> None:
    with pytest.raises(CalculationError):
        calculate(query)


def test_prose_is_not_treated_as_a_local_calculation() -> None:
    assert extract_arithmetic("Explain calculus") is None
