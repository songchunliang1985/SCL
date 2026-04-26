"""
MCP Server: Utils — 天气、计算器、时间
"""

import json
import math
from datetime import datetime

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如 北京、东京"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "计算数学表达式，如 2+3*4、sqrt(16)、sin(3.14)",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式"}
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "获取当前日期和时间",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def get_weather(city: str) -> str:
    import random
    conditions = ["晴", "多云", "小雨", "阴", "雷阵雨"]
    temp = random.randint(-5, 38)
    cond = random.choice(conditions)
    return json.dumps({"city": city, "temperature": f"{temp}°C", "condition": cond}, ensure_ascii=False)


def calculator(expression: str) -> str:
    safe = {
        "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
        "tan": math.tan, "log": math.log, "pi": math.pi, "e": math.e,
        "abs": abs, "pow": pow, "round": round,
    }
    try:
        result = eval(expression, {"__builtins__": {}}, safe)
        return json.dumps({"expression": expression, "result": str(result)}, ensure_ascii=False)
    except Exception as ex:
        return json.dumps({"error": str(ex)}, ensure_ascii=False)


def get_current_time() -> str:
    return json.dumps({"datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, ensure_ascii=False)


TOOL_MAP = {
    "get_weather": get_weather,
    "calculator": calculator,
    "get_current_time": get_current_time,
}

TOOL_LABELS = {
    "get_weather": "🌤 查询天气",
    "calculator": "🧮 计算",
    "get_current_time": "🕐 获取时间",
}
