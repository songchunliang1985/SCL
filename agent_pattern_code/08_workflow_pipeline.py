"""
工作流编排范式（Workflow Pipeline）
=====================================

场景：代码 PR 自动审查流水线
流程：结构解析 → 安全扫描 → 质量审查 → 汇总报告

与 ReAct/Plan&Execute 的动态循环不同，Workflow 的控制流
完全由宿主程序决定，LLM 只是各 Stage 里的叶子调用：
  · 每个 Stage 是纯函数  state_in → state_out
  · Pipeline 按固定顺序执行，Stage 可附 skip_if 条件
  · critical 风险时质量审查自动跳过，报告始终生成
"""

import json
import anthropic
from dataclasses import dataclass, field
from typing import Callable

client = anthropic.Anthropic()


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ReviewState:
    """全局状态：贯穿所有 Stage"""
    code: str
    filename: str = "code.py"
    structure: dict = field(default_factory=dict)
    security_issues: list[str] = field(default_factory=list)
    quality_issues: list[str] = field(default_factory=list)
    security_risk: str = "none"
    quality_score: int = 0
    final_report: str = ""
    critical_risk: bool = False      # 控制后续 Stage 的 skip_if


@dataclass
class WorkflowStep:
    name: str
    handler: Callable[[ReviewState], ReviewState]
    skip_if: Callable[[ReviewState], bool] = field(default=lambda _: False)


# ============================================================
# Prompts
# ============================================================

STRUCTURE_PROMPT = """你是一个代码分析专家。
分析给定代码的结构，输出 JSON：
{
  "language": "语言",
  "functions": ["函数名1", ...],
  "complexity": "low/medium/high",
  "summary": "一句话概括代码功能"
}
只输出 JSON。"""

SECURITY_PROMPT = """你是一个代码安全专家。
审查代码安全漏洞：SQL注入、命令注入、硬编码凭证、不安全反序列化、路径穿越。
输出 JSON：
{
  "risk_level": "none/low/medium/high/critical",
  "issues": ["问题描述（位置+原因+修复建议）", ...]
}
只输出 JSON。"""

QUALITY_PROMPT = """你是一个代码质量专家。
审查命名规范、函数职责、错误处理、重复代码、性能隐患。
输出 JSON：
{
  "score": 1-10,
  "issues": ["问题描述（位置+原因+建议）", ...],
  "strengths": ["优点"]
}
只输出 JSON。"""

REPORT_PROMPT = """你是技术评审专家。根据各阶段分析结果生成代码审查报告（Markdown）：

## 代码审查报告
**文件**：{filename}
**总体评级**：安全[风险等级] / 质量[X/10]

### 结构概览
### 安全问题（无则写"无安全风险"）
### 质量建议（Top 3）
### 结论（一句话：是否建议合并）"""


# ============================================================
# 公共调用（叶子节点，不感知流程）
# ============================================================

def llm(system: str, user: str, max_tokens: int = 600) -> str:
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def parse_json(text: str) -> dict:
    cleaned = text.strip().removeprefix("```json").removeprefix("```")
    cleaned = cleaned.removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return {}


# ============================================================
# Stage 实现（纯函数：state_in → state_out）
# ============================================================

def stage_structure(state: ReviewState) -> ReviewState:
    print("  [Stage 1] 解析代码结构…")
    r = parse_json(llm(STRUCTURE_PROMPT, state.filename + "\n\n" + state.code))
    state.structure = r
    print(f"    {r.get('summary', '')}  复杂度={r.get('complexity', '?')}")
    return state


def stage_security(state: ReviewState) -> ReviewState:
    print("  [Stage 2] 安全扫描…")
    r = parse_json(llm(SECURITY_PROMPT, state.filename + "\n\n" + state.code))
    state.security_issues = r.get("issues", [])
    state.security_risk   = r.get("risk_level", "unknown")
    print(f"    风险={state.security_risk}  问题数={len(state.security_issues)}")
    for issue in state.security_issues:
        print("      ⚠ " + issue)
    if state.security_risk == "critical":
        print("    ❌ Critical 风险，质量审查将跳过")
        state.critical_risk = True
    return state


def stage_quality(state: ReviewState) -> ReviewState:
    print("  [Stage 3] 质量审查…")
    r = parse_json(llm(QUALITY_PROMPT, state.filename + "\n\n" + state.code))
    state.quality_issues = r.get("issues", [])
    state.quality_score  = r.get("score", 0)
    print(f"    质量评分={state.quality_score}/10  问题数={len(state.quality_issues)}")
    return state


def stage_report(state: ReviewState) -> ReviewState:
    print("  [Stage 4] 生成审查报告…")
    sec = "\n".join("- " + i for i in state.security_issues) or "无"
    qua = "\n".join("- " + i for i in state.quality_issues) or "跳过"
    context = (
        "文件：" + state.filename + "\n\n"
        "结构：\n" + json.dumps(state.structure, ensure_ascii=False) + "\n\n"
        "安全（" + state.security_risk + "）：\n" + sec + "\n\n"
        "质量（" + str(state.quality_score) + "/10）：\n" + qua
    )
    state.final_report = llm(
        REPORT_PROMPT.format(filename=state.filename),
        context,
        max_tokens=800,
    )
    return state


# ============================================================
# Pipeline 定义与执行器
# ============================================================

PIPELINE: list[WorkflowStep] = [
    WorkflowStep("structure", stage_structure),
    WorkflowStep("security",  stage_security),
    WorkflowStep("quality",   stage_quality,
                 skip_if=lambda s: s.critical_risk),   # critical 时跳过
    WorkflowStep("report",    stage_report),            # 始终执行
]


def run_pipeline(code: str, filename: str = "code.py") -> str:
    """执行代码审查流水线，返回最终报告"""
    state = ReviewState(code=code, filename=filename)

    print("\n" + "=" * 60)
    print("▶ 代码审查流水线：" + filename)
    print("=" * 60)

    for step in PIPELINE:
        if step.skip_if(state):
            print("  [跳过] " + step.name)
            continue
        state = step.handler(state)

    print("\n" + "=" * 60)
    print(state.final_report)
    return state.final_report


# ============================================================
# 测试：含多种安全漏洞的代码
# ============================================================

SAMPLE_CODE = '''
import subprocess, pickle

def query_user(name):
    sql = "SELECT * FROM users WHERE name = '" + name + "'"
    return db.execute(sql)            # SQL 注入

def load_config(path):
    with open(path, "rb") as f:
        return pickle.load(f)         # 不安全的反序列化

SECRET = "hardcoded_secret_abc123"    # 硬编码凭证

def run_cmd(user_input):
    subprocess.call(user_input, shell=True)  # 命令注入
'''

if __name__ == "__main__":
    run_pipeline(SAMPLE_CODE, "legacy_utils.py")
