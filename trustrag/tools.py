"""Agent tools. The calculator uses an AST whitelist - never eval() - so it is safe on user input."""
from __future__ import annotations

import ast
import operator as op
import re

_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Pow: op.pow, ast.Mod: op.mod, ast.USub: op.neg, ast.UAdd: op.pos}


def safe_eval(expr: str) -> float:
    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("unsupported expression")

    if len(expr) > 200:
        raise ValueError("expression too long")
    return ev(ast.parse(expr, mode="eval"))


_CALC_INTENT = re.compile(r"\b(calculate|compute|evaluate|solve|what is|what's|how much is)\b", re.I)
_PERCENT_OF = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s*\$?(\d+(?:\.\d+)?)", re.I)
_EXPR = re.compile(r"\(?-?\$?\d+(?:\.\d+)?\)?(?:\s*[-+*/x×^%]\s*\(?-?\$?\d+(?:\.\d+)?\)?)+")


def extract_expression(question: str) -> str | None:
    """Pull an arithmetic expression out of natural language, or None if there isn't a clear one."""
    if not _CALC_INTENT.search(question):
        return None
    m = _PERCENT_OF.search(question)
    if m:
        return f"{m.group(1)}/100*{m.group(2)}"
    m = _EXPR.search(question.replace(",", ""))
    if not m:
        return None
    expr = m.group(0).replace("$", "").replace("x", "*").replace("×", "*").replace("^", "**")
    return expr if re.search(r"[-+*/%]", expr) else None


def fmt_number(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.6g}"
