"""LangChain routing for arithmetic, conceptual math, and general queries."""

from __future__ import annotations

import re
from typing import Any

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableBranch, RunnableLambda

from app.math_tools import CalculationError, calculate, extract_arithmetic

_MATH_TERMS = re.compile(
    r"\b(?:math|mathematics|arithmetic|algebra|calculus|derivatives?|integrals?|"
    r"equations?|quadratics?|geometry|trigonometry|probability|statistics|"
    r"fractions?|percentages?|logarithms?|matrices|matrix|vectors?|theorems?|"
    r"prime\s+numbers?|square\s+roots?|limits?|formulas?)\b",
    re.IGNORECASE,
)
_MATH_WORDS = re.compile(
    r"\b(?:calculate|compute|multiply|divide|subtract|add|plus|minus|times|"
    r"product|quotient|sum|solve|simplify)\b",
    re.IGNORECASE,
)
_NUMBER_WORDS = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|hundred|thousand|million)\b",
    re.IGNORECASE,
)
_NUMERIC_OPERATOR = re.compile(r"\d\s*(?:[+*/×÷^]|-(?=\s*\d))\s*\d")


def is_math_query(payload: dict[str, str]) -> bool:
    query = payload["query"]
    return bool(
        extract_arithmetic(query)
        or _MATH_TERMS.search(query)
        or (_MATH_WORDS.search(query) and (re.search(r"\d", query) or _NUMBER_WORDS.search(query)))
        or _NUMERIC_OPERATOR.search(query)
    )


def is_direct_calculation(payload: dict[str, str]) -> bool:
    return extract_arithmetic(payload["query"]) is not None


def _calculate(payload: dict[str, str]) -> str:
    try:
        return calculate(payload["query"])
    except CalculationError as exc:
        return str(exc)


def build_router(model: Runnable[Any, Any]) -> RunnableBranch:
    """Build one reusable router; both LLM paths share the same model."""
    math_prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a precise mathematics tutor. Explain concepts clearly and "
                "show short, useful steps when needed. State uncertainty rather "
                "than inventing a result.",
            ),
            ("human", "{query}"),
        ]
    )
    general_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "Answer the user's question clearly and concisely."),
            ("human", "{query}"),
        ]
    )
    math_chain = RunnableBranch(
        (is_direct_calculation, RunnableLambda(_calculate)),
        math_prompt | model | StrOutputParser(),
    )
    return RunnableBranch(
        (is_math_query, math_chain),
        general_prompt | model | StrOutputParser(),
    )
