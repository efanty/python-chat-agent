"""Calculator skill helper - safe math expression evaluator."""
import math

ALLOWED_NAMES = {
    k: v for k, v in vars(math).items() if not k.startswith("_")
}


def safe_eval(expression: str) -> str:
    """Safely evaluate a mathematical expression."""
    expression = expression.strip()[:500]
    try:
        result = eval(expression, {"__builtins__": {}}, ALLOWED_NAMES)
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"
