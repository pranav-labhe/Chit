"""Conservative, deterministic symbolic calculator tool with zero eval/exec."""
from __future__ import annotations

import re


def _tokenize_math_text(text: str) -> list[str] | None:
    """Normalize and tokenize text into numbers and operators if it matches safe arithmetic."""
    clean = text.strip().lower()

    # Reject hypotheticals and conditionals
    if re.search(r"\b(if|suppose|what if|assuming|imagine)\b", clean):
        return None

    # Reject dates (e.g. 2026-10-12, 10/12/2026)
    if re.search(r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b", clean) or re.search(r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b", clean):
        return None

    # Reject version strings (e.g. v1.2, version 2.0)
    if re.search(r"\bv?\d+\.\d+\.\d+\b", clean) or re.search(r"\bv\d+\.\d+\b", clean):
        return None

    # Reject phone numbers (e.g. +1-800-555-1212)
    if re.search(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b", clean):
        return None

    # Strip conversational prefixes
    clean = re.sub(
        r"^(?:what\s+is|calculate|compute|solve|tell\s+me|show\s+me(?:\s+the\s+result\s+of)?|evaluate)\s+",
        "",
        clean,
    )
    # Strip trailing punctuation / phrases
    clean = re.sub(r"(?:\s+and\s+show\s+the\s+result)?[\?\.\!\s]*$", "", clean).strip()

    # Strip wrapping parentheses e.g. "(14 + 28)" -> "14 + 28"
    while clean.startswith("(") and clean.endswith(")"):
        clean = clean[1:-1].strip()

    # Normalize word operators
    clean = re.sub(r"\bmultiplied\s+by\b", "*", clean)
    clean = re.sub(r"\bdivided\s+by\b", "/", clean)
    clean = re.sub(r"\btimes\b", "*", clean)
    clean = re.sub(r"\bplus\b", "+", clean)
    clean = re.sub(r"\bminus\b", "-", clean)
    clean = re.sub(r"\bx\b", "*", clean)

    # Must contain only digits, decimal dots, operators, parentheses, whitespace
    if not re.fullmatch(r"[\d\s\+\-\*\/\(\)\.]+", clean):
        return None

    # Extract tokens: numbers and operators
    raw_tokens = re.findall(r"\d+(?:\.\d+)?|[\+\-\*\/\(\)]", clean)
    if not raw_tokens:
        return None

    # Check bounds on operands
    for tok in raw_tokens:
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            val = float(tok)
            if abs(val) > 10**7:
                return None

    return raw_tokens


def evaluate_expression(tokens: list[str]) -> tuple[bool, str]:
    """Safely evaluate binary or ternary arithmetic expressions without eval/exec."""
    # We support binary (e.g. [A, op, B]) and ternary (e.g. [A, op, B, op, C])
    numbers: list[float] = []
    ops: list[str] = []

    # Simple parsing: expect number op number (op number)?
    # Handle optional leading unary minus
    idx = 0
    if tokens and tokens[0] == "-":
        if len(tokens) >= 2 and re.fullmatch(r"\d+(?:\.\d+)?", tokens[1]):
            numbers.append(-float(tokens[1]))
            idx = 2
        else:
            return False, ""

    while idx < len(tokens):
        tok = tokens[idx]
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            numbers.append(float(tok))
        elif tok in ("+", "-", "*", "/"):
            ops.append(tok)
        else:
            return False, ""
        idx += 1

    # Check structure: binary needs 2 numbers and 1 op; ternary needs 3 numbers and 2 ops
    if len(numbers) == 2 and len(ops) == 1:
        a, b = numbers
        op = ops[0]
        if op == "+":
            res = a + b
        elif op == "-":
            res = a - b
        elif op == "*":
            res = a * b
        elif op == "/":
            if b == 0:
                return True, "Error: Division by zero is undefined."
            res = a / b
        else:
            return False, ""
        return True, _format_result(res)

    if len(numbers) == 3 and len(ops) == 2:
        a, b, c = numbers
        op1, op2 = ops
        # Standard operator precedence: * and / before + and -
        if op2 in ("*", "/") and op1 in ("+", "-"):
            # Compute b op2 c first
            if op2 == "*":
                sub = b * c
            else:
                if c == 0:
                    return True, "Error: Division by zero is undefined."
                sub = b / c
            if op1 == "+":
                res = a + sub
            else:
                res = a - sub
        else:
            # Compute a op1 b first
            if op1 == "+":
                sub = a + b
            elif op1 == "-":
                sub = a - b
            elif op1 == "*":
                sub = a * b
            else:
                if b == 0:
                    return True, "Error: Division by zero is undefined."
                sub = a / b

            if op2 == "+":
                res = sub + c
            elif op2 == "-":
                res = sub - c
            elif op2 == "*":
                res = sub * c
            else:
                if c == 0:
                    return True, "Error: Division by zero is undefined."
                res = sub / c
        return True, _format_result(res)

    return False, ""


def _format_result(val: float) -> str:
    if val.is_integer():
        return str(int(val))
    return f"{val:.6g}"


def try_calculate(query: str) -> str | None:
    """Attempts conservative symbolic arithmetic calculation on the query.

    Returns string result if successfully evaluated, or None otherwise.
    """
    tokens = _tokenize_math_text(query)
    if tokens is None:
        return None
    success, result = evaluate_expression(tokens)
    if success:
        return result
    return None
