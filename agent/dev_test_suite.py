#!/usr/bin/env python3
"""
日常开发能力对比测试套件
专门测试 DeepSeek 是否能替代 Claude 进行日常开发工作

测试覆盖开发全流程：
1. 代码编写与重构
2. 调试与问题解决
3. 代码审查与优化
4. 文档编写
5. 架构设计
6. 工具使用指导
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# 开发专用测试用例
DEV_TEST_CASES = [
    # ==================== 代码编写 ====================
    {
        "id": "dev_code_01",
        "category": "代码编写",
        "subcategory": "API实现",
        "prompt": """实现一个完整的RESTful API端点，用于用户管理：
要求：
1. 使用Flask框架
2. 支持用户的CRUD操作
3. 使用SQLite数据库
4. 包含输入验证和错误处理
5. 提供完整的单元测试
6. 添加必要的注释和文档字符串

请给出完整的代码实现。""",
        "evaluation_criteria": ["功能完整性", "代码质量", "错误处理", "测试覆盖", "文档完整"],
        "tech_stack": ["Python", "Flask", "SQLite"]
    },
    {
        "id": "dev_code_02",
        "category": "代码编写",
        "subcategory": "算法实现",
        "prompt": """实现一个LRU缓存算法，要求：
1. 时间复杂度O(1)的get和put操作
2. 容量限制
3. 线程安全考虑
4. 完整的类型注解
5. 单元测试

用Python实现，展示设计思路。""",
        "evaluation_criteria": ["算法正确性", "时间复杂度", "代码清晰度", "测试用例"],
        "tech_stack": ["Python", "算法", "数据结构"]
    },
    {
        "id": "dev_code_03",
        "category": "代码编写",
        "subcategory": "前端组件",
        "prompt": """创建一个React组件，实现一个可过滤、可排序的表格：
要求：
1. 支持多列排序
2. 每列可单独过滤
3. 分页功能
4. 响应式设计
5. TypeScript类型定义
6. 完整的Props文档

请给出组件代码和使用示例。""",
        "evaluation_criteria": ["功能完整", "TypeScript质量", "UI/UX考虑", "代码组织"],
        "tech_stack": ["React", "TypeScript", "前端"]
    },

    # ==================== 调试与问题解决 ====================
    {
        "id": "dev_debug_01",
        "category": "调试",
        "subcategory": "错误诊断",
        "prompt": """分析以下代码的问题并提供修复方案：

```python
import asyncio
import aiohttp
from typing import List

async def fetch_urls(urls: List[str]) -> List[str]:
    results = []
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=10) as response:
                    results.append(await response.text())
            except Exception as e:
                results.append(f"Error: {e}")
    return results

async def main():
    urls = [
        "https://api.example.com/data1",
        "https://api.example.com/data2",
        "https://api.example.com/data3"
    ]
    data = await fetch_urls(urls)
    print(data)

if __name__ == "__main__":
    asyncio.run(main())
```

问题：当URL列表较大时，性能很差。请：
1. 指出性能瓶颈
2. 提供优化方案
3. 给出改进后的代码""",
        "evaluation_criteria": ["问题识别", "解决方案", "代码改进", "性能考量"],
        "tech_stack": ["Python", "异步", "性能优化"]
    },
    {
        "id": "dev_debug_02",
        "category": "调试",
        "subcategory": "内存泄漏",
        "prompt": """以下代码存在内存泄漏问题，请诊断并修复：

```javascript
class DataProcessor {
    constructor() {
        this.data = [];
        this.listeners = [];
    }

    addListener(callback) {
        this.listeners.push(callback);
    }

    process(newData) {
        this.data.push(newData);
        // 处理数据
        const result = this.data.map(item => item * 2);

        // 通知监听器
        this.listeners.forEach(listener => {
            listener(result);
        });

        return result;
    }
}

// 使用示例
const processor = new DataProcessor();
for (let i = 0; i < 1000; i++) {
    const listener = (data) => console.log(`Listener ${i}:`, data.length);
    processor.addListener(listener);
    processor.process([1, 2, 3]);
}
```

请：
1. 指出内存泄漏的原因
2. 提供修复方案
3. 解释修复原理""",
        "evaluation_criteria": ["问题诊断", "解决方案", "解释清晰度"],
        "tech_stack": ["JavaScript", "内存管理"]
    },

    # ==================== 代码审查 ====================
    {
        "id": "dev_review_01",
        "category": "代码审查",
        "subcategory": "安全性审查",
        "prompt": """审查以下用户认证代码的安全性问题：

```python
import sqlite3
import hashlib

def authenticate(username, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # 直接拼接SQL - SQL注入风险！
    query = f"SELECT password_hash FROM users WHERE username = '{username}'"
    cursor.execute(query)

    result = cursor.fetchone()
    conn.close()

    if not result:
        return False

    stored_hash = result[0]
    # 简单的MD5哈希 - 不安全！
    input_hash = hashlib.md5(password.encode()).hexdigest()

    return input_hash == stored_hash

def register(username, password):
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # 同样的问题
    query = f"INSERT INTO users (username, password_hash) VALUES ('{username}', '{hashlib.md5(password.encode()).hexdigest()}')"
    cursor.execute(query)
    conn.commit()
    conn.close()

    return True
```

请：
1. 列出所有安全问题
2. 提供修复建议
3. 给出改进后的代码""",
        "evaluation_criteria": ["安全问题识别", "修复建议", "代码改进"],
        "tech_stack": ["Python", "安全", "数据库"]
    },
    {
        "id": "dev_review_02",
        "category": "代码审查",
        "subcategory": "代码质量",
        "prompt": """审查以下代码的质量问题，提供重构建议：

```python
def process_data(data_list):
    result = []
    for i in range(len(data_list)):
        item = data_list[i]
        if item is not None:
            if type(item) == str:
                if item.strip() != "":
                    processed = item.upper()
                    if processed not in result:
                        result.append(processed)
            elif type(item) == int:
                if item > 0:
                    processed = str(item * 2)
                    if processed not in result:
                        result.append(processed)
            elif type(item) == list:
                for j in range(len(item)):
                    subitem = item[j]
                    if subitem is not None:
                        if type(subitem) == str:
                            if subitem.strip() != "":
                                processed = subitem.lower()
                                if processed not in result:
                                    result.append(processed)
    return result
```

请：
1. 指出代码质量问题
2. 提供重构方案
3. 展示重构后的代码""",
        "evaluation_criteria": ["问题识别", "重构质量", "代码可读性"],
        "tech_stack": ["Python", "代码质量", "重构"]
    },

    # ==================== 文档编写 ====================
    {
        "id": "dev_doc_01",
        "category": "文档",
        "subcategory": "API文档",
        "prompt": """为以下函数编写完整的API文档（包含示例）：

```python
def batch_process(items: List[Any],
                  processor: Callable[[Any], Any],
                  batch_size: int = 10,
                  max_workers: int = 4,
                  timeout: float = 30.0) -> List[Any]:
    '''
    批量处理函数

    Args:
        items: 待处理的项目列表
        processor: 处理单个项目的函数
        batch_size: 每批处理的数量
        max_workers: 最大工作线程数
        timeout: 超时时间（秒）

    Returns:
        处理结果列表，与输入顺序一致

    Raises:
        ValueError: 当参数无效时
        TimeoutError: 当处理超时时
    '''
    # 实现省略...
```

要求：
1. 完整的函数说明
2. 详细的参数说明
3. 返回值说明
4. 异常说明
5. 使用示例
6. 注意事项""",
        "evaluation_criteria": ["文档完整性", "示例质量", "清晰度"],
        "tech_stack": ["Python", "文档"]
    },
    {
        "id": "dev_doc_02",
        "category": "文档",
        "subcategory": "架构文档",
        "prompt": """为一个微服务架构编写架构概述文档：

架构包含：
1. API Gateway (Kong)
2. 用户服务 (Python/FastAPI)
3. 订单服务 (Go/Go)
4. 支付服务 (Java/Spring Boot)
5. 消息队列 (RabbitMQ)
6. 数据库 (PostgreSQL + Redis)

要求：
1. 架构图描述（文字描述）
2. 各组件职责
3. 数据流向
4. 部署考虑
5. 扩展性设计""",
        "evaluation_criteria": ["架构清晰度", "技术准确性", "完整性"],
        "tech_stack": ["架构", "微服务", "文档"]
    },

    # ==================== 架构设计 ====================
    {
        "id": "dev_arch_01",
        "category": "架构设计",
        "subcategory": "系统设计",
        "prompt": """设计一个短链服务系统（类似 bit.ly）：

需求：
1. 生成短链
2. 重定向到原始URL
3. 访问统计
4. 自定义短链
5. 链接过期管理

请提供：
1. 系统架构设计
2. API设计
3. 数据库设计
4. 关键技术选型
5. 扩展性考虑""",
        "evaluation_criteria": ["设计完整性", "技术选型", "扩展性", "可行性"],
        "tech_stack": ["系统设计", "API设计", "数据库设计"]
    },

    # ==================== 工具使用 ====================
    {
        "id": "dev_tool_01",
        "category": "工具使用",
        "subcategory": "Git工作流",
        "prompt": """为一个团队设计Git工作流，要求：

团队情况：
- 10人开发团队
- 持续集成/部署
- 多环境（开发、测试、生产）
- 需要代码审查
- 支持热修复

请提供：
1. 分支策略
2. 提交规范
3. 代码审查流程
4. 发布流程
5. 热修复流程
6. 推荐的Git命令示例""",
        "evaluation_criteria": ["流程完整性", "实用性", "规范性"],
        "tech_stack": ["Git", "工作流", "团队协作"]
    },
    {
        "id": "dev_tool_02",
        "category": "工具使用",
        "subcategory": "Docker配置",
        "prompt": """为一个Python Flask应用编写Docker配置：

应用要求：
1. Flask + Gunicorn
2. PostgreSQL数据库
3. Redis缓存
4. Celery后台任务
5. 环境变量配置
6. 日志管理

请提供：
1. Dockerfile
2. docker-compose.yml
3. 环境变量示例
4. 部署说明
5. 最佳实践建议""",
        "evaluation_criteria": ["配置完整性", "最佳实践", "可部署性"],
        "tech_stack": ["Docker", "Python", "部署"]
    }
]

class DevModelTester:
    """开发能力模型测试器"""

    def __init__(self, output_dir: str = "dev_test_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def run_model_test(self, model: str, prompt: str, timeout: int = 120) -> Tuple[Optional[str], float, Optional[Dict]]:
        """运行模型测试"""
        cmd = ["claude", "--model", model, "--print", prompt, "--no-session-persistence"]

        print(f"  执行: claude --model {model} --print (长度: {len(prompt)})")

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                return result.stdout.strip(), round(elapsed, 2), None
            else:
                error_info = {
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip()[:500],
                    "stdout": result.stdout.strip()[:500]
                }
                return None, round(elapsed, 2), error_info

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return None, round(elapsed, 2), {"error": f"超时 ({timeout}s)"}
        except Exception as e:
            elapsed = time.time() - start_time
            return None, round(elapsed, 2), {"error": str(e)}

    def test_model(self, model_name: str, model_label: str, test_cases: List[Dict] = None) -> Dict:
        """测试模型的所有开发用例"""
        if test_cases is None:
            test_cases = DEV_TEST_CASES

        print(f"\n{'='*60}")
        print(f"开始开发能力测试: {model_label} ({model_name})")
        print(f"{'='*60}")

        results = {
            "model": model_name,
            "label": model_label,
            "test_time": datetime.now().isoformat(),
            "total_cases": len(test_cases),
            "successful_cases": 0,
            "failed_cases": 0,
            "total_time": 0,
            "categories": {},
            "cases": []
        }

        # 初始化分类统计
        categories = set(case["category"] for case in test_cases)
        for category in categories:
            results["categories"][category] = {
                "total": 0,
                "success": 0,
                "total_time": 0,
                "avg_time": 0
            }

        for i, test_case in enumerate(test_cases):
            category = test_case["category"]
            results["categories"][category]["total"] += 1

            print(f"\n[{i+1}/{len(test_cases)}] {category} > {test_case['subcategory']}")
            print(f"  技术栈: {', '.join(test_case['tech_stack'])}")

            # 运行测试
            response, elapsed, error = self.run_model_test(
                model_name, test_case["prompt"]
            )

            case_result = {
                "id": test_case["id"],
                "category": category,
                "subcategory": test_case["subcategory"],
                "tech_stack": test_case["tech_stack"],
                "prompt": test_case["prompt"][:500] + "..." if len(test_case["prompt"]) > 500 else test_case["prompt"],
                "prompt_length": len(test_case["prompt"]),
                "elapsed_time": elapsed,
                "success": response is not None,
                "response_length": len(response) if response else 0,
                "response_preview": response[:300] + "..." if response and len(response) > 300 else response,
                "error": error,
                "evaluation_criteria": test_case["evaluation_criteria"]
            }

            results["cases"].append(case_result)
            results["total_time"] += elapsed
            results["categories"][category]["total_time"] += elapsed

            if response:
                results["successful_cases"] += 1
                results["categories"][category]["success"] += 1
                print(f"  结果: 成功 ({elapsed}s, {len(response)}字符)")
            else:
                results["failed_cases"] += 1
                print(f"  结果: 失败 ({elapsed}s)")
                if error:
                    print(f"  错误: {error.get('error', str(error))}")

        # 计算各类别平均时间
        for category in results["categories"]:
            cat_data = results["categories"][category]
            if cat_data["success"] > 0:
                cat_data["avg_time"] = round(cat_data["total_time"] / cat_data["success"], 2)
            else:
                cat_data["avg_time"] = 0

        # 计算总平均时间
        if results["successful_cases"] > 0:
            results["avg_time"] = round(results["total_time"] / results["successful_cases"], 2)
        else:
            results["avg_time"] = 0

        # 成功率
        results["success_rate"] = round(results["successful_cases"] / results["total_cases"] * 100, 1)

        print(f"\n📊 测试摘要:")
        print(f"  总用例: {results['total_cases']}")
        print(f"  成功: {results['successful_cases']} (成功率: {results['success_rate']}%)")
        print(f"  失败: {results['failed_cases']}")
        print(f"  总耗时: {results['total_time']}s")
        print(f"  平均响应时间: {results['avg_time']}s")

        return results

    def save_results(self, results: Dict, filename: str = None):
        """保存测试结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"dev_test_{results['model']}_{timestamp}.json"

        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"结果已保存: {filepath}")
        return filepath

    def compare_dev_capabilities(self, results_deepseek: Dict, results_claude: Dict):
        """对比两个模型的开发能力"""
        print(f"\n{'='*60}")
        print("开发能力对比报告")
        print(f"{'='*60}")

        comparison = {
            "comparison_time": datetime.now().isoformat(),
            "deepseek": {
                "model": results_deepseek["model"],
                "label": results_deepseek["label"],
                "success_rate": results_deepseek["success_rate"],
                "avg_time": results_deepseek["avg_time"],
                "total_time": results_deepseek["total_time"]
            },
            "claude": {
                "model": results_claude["model"],
                "label": results_claude["label"],
                "success_rate": results_claude["success_rate"],
                "avg_time": results_claude["avg_time"],
                "total_time": results_claude["total_time"]
            },
            "category_comparison": {},
            "summary": {}
        }

        # 总体对比
        print(f"\n📈 总体表现对比:")
        print(f"{'指标':<15} {'DeepSeek':<20} {'Claude':<20} {'差异'}")
        print("-" * 80)

        metrics = [
            ("成功率", f"{results_deepseek['success_rate']}%", f"{results_claude['success_rate']}%"),
            ("平均时间", f"{results_deepseek['avg_time']}s", f"{results_claude['avg_time']}s"),
            ("总耗时", f"{results_deepseek['total_time']}s", f"{results_claude['total_time']}s"),
        ]

        for label, val_deepseek, val_claude in metrics:
            # 计算差异
            try:
                if '%' in val_deepseek:
                    num_ds = float(val_deepseek.replace('%', ''))
                    num_cl = float(val_claude.replace('%', ''))
                    diff = num_ds - num_cl
                    diff_str = f"{'+' if diff > 0 else ''}{diff:.1f}%"
                    if diff > 0:
                        diff_str += " (DeepSeek更高)"
                    else:
                        diff_str += " (Claude更高)"
                else:
                    num_ds = float(val_deepseek.replace('s', ''))
                    num_cl = float(val_claude.replace('s', ''))
                    diff = num_ds - num_cl
                    diff_str = f"{'+' if diff > 0 else ''}{diff:.2f}s"
                    if diff > 0:
                        diff_str += " (Claude更快)"
                    else:
                        diff_str += " (DeepSeek更快)"
            except:
                diff_str = "N/A"

            print(f"{label:<15} {val_deepseek:<20} {val_claude:<20} {diff_str}")

        # 分类别对比
        print(f"\n🔧 开发能力分类对比:")
        print(f"{'开发领域':<12} {'DS成功率':<10} {'Cl成功率':<10} {'DS平均时间':<12} {'Cl平均时间':<12} {'优势方'}")
        print("-" * 80)

        # 收集所有类别
        all_categories = set()
        for cat in results_deepseek["categories"]:
            all_categories.add(cat)
        for cat in results_claude["categories"]:
            all_categories.add(cat)

        for category in sorted(all_categories):
            ds_cat = results_deepseek["categories"].get(category, {"success": 0, "total": 0, "avg_time": 0})
            cl_cat = results_claude["categories"].get(category, {"success": 0, "total": 0, "avg_time": 0})

            ds_success_rate = 0
            cl_success_rate = 0
            if ds_cat["total"] > 0:
                ds_success_rate = round(ds_cat["success"] / ds_cat["total"] * 100, 1)
            if cl_cat["total"] > 0:
                cl_success_rate = round(cl_cat["success"] / cl_cat["total"] * 100, 1)

            # 确定优势方
            advantage = ""
            if ds_success_rate > cl_success_rate + 5:  # 5%阈值
                advantage = "DeepSeek"
            elif cl_success_rate > ds_success_rate + 5:
                advantage = "Claude"
            else:
                advantage = "相当"

            print(f"{category:<12} {ds_success_rate:<10}% {cl_success_rate:<10}% "
                  f"{ds_cat.get('avg_time', 0):<12.1f}s {cl_cat.get('avg_time', 0):<12.1f}s {advantage:<10}")

            # 保存类别对比
            comparison["category_comparison"][category] = {
                "deepseek_success_rate": ds_success_rate,
                "claude_success_rate": cl_success_rate,
                "deepseek_avg_time": ds_cat.get("avg_time", 0),
                "claude_avg_time": cl_cat.get("avg_time", 0),
                "advantage": advantage
            }

        # 成本估算
        print(f"\n💰 成本对比 (基于响应长度):")
        total_chars_ds = sum(case["response_length"] for case in results_deepseek["cases"] if case["success"])
        total_chars_cl = sum(case["response_length"] for case in results_claude["cases"] if case["success"])

        # 估算token数 (中英文混合，保守估算)
        tokens_ds = total_chars_ds * 0.3  # 每个字符≈0.3个token
        tokens_cl = total_chars_cl * 0.3

        # 成本计算 (假设输入输出比例 1:3)
        # DeepSeek: 输入¥0.14/1M, 输出¥0.28/1M ≈ $0.02/$0.04 per 1M
        # Claude: 输入$3/1M, 输出$15/1M
        cost_ds_usd = tokens_ds / 1_000_000 * ((0.02 * 0.25) + (0.04 * 0.75))
        cost_cl_usd = tokens_cl / 1_000_000 * ((3 * 0.25) + (15 * 0.75))

        print(f"  DeepSeek: {total_chars_ds:,} 字符 ≈ {tokens_ds:,.0f} tokens")
        print(f"    估算成本: ${cost_ds_usd:.6f} USD (约 ¥{cost_ds_usd * 7:.4f})")
        print(f"  Claude: {total_chars_cl:,} 字符 ≈ {tokens_cl:,.0f} tokens")
        print(f"    估算成本: ${cost_cl_usd:.6f} USD (约 ¥{cost_cl_usd * 7:.4f})")

        if cost_cl_usd > 0 and cost_ds_usd > 0:
            cost_ratio = cost_cl_usd / cost_ds_usd
            print(f"  💡 成本差异: Claude 是 DeepSeek 的 {cost_ratio:.1f} 倍")

            # 判断是否值得替代
            if cost_ratio > 20 and results_deepseek["success_rate"] >= results_claude["success_rate"] - 10:
                recommendation = "✅ 强烈推荐用 DeepSeek 替代 Claude"
                reason = f"成本仅为 Claude 的 1/{cost_ratio:.0f}，能力相当"
            elif cost_ratio > 10 and results_deepseek["success_rate"] >= results_claude["success_rate"] - 5:
                recommendation = "👍 建议用 DeepSeek 替代 Claude"
                reason = f"成本显著更低 (1/{cost_ratio:.0f})，能力接近"
            elif cost_ratio > 5:
                recommendation = "🤔 可以考虑用 DeepSeek，但需注意质量"
                reason = f"成本较低 (1/{cost_ratio:.0f})，但能力有差距"
            else:
                recommendation = "⚠️ 不建议完全替代"
                reason = "成本优势不明显或能力差距较大"
        else:
            recommendation = "⚠️ 无法计算成本差异"
            reason = "成本计算数据不足"

        comparison["summary"] = {
            "cost_comparison": {
                "deepseek_chars": total_chars_ds,
                "claude_chars": total_chars_cl,
                "deepseek_cost_usd": cost_ds_usd,
                "claude_cost_usd": cost_cl_usd,
                "cost_ratio": cost_cl_usd / cost_ds_usd if cost_ds_usd > 0 else None
            },
            "recommendation": recommendation,
            "reason": reason
        }

        print(f"\n🎯 替代建议: {recommendation}")
        print(f"   原因: {reason}")

        # 保存对比报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        comp_file = self.output_dir / f"dev_comparison_{results_deepseek['model']}_vs_{results_claude['model']}_{timestamp}.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

        print(f"\n对比报告已保存: {comp_file}")

        return comparison

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="日常开发能力对比测试")
    parser.add_argument("--deepseek-model", default="deepseek-chat", help="DeepSeek模型名称")
    parser.add_argument("--claude-model", default="sonnet", help="Claude模型名称")
    parser.add_argument("--output-dir", default="dev_test_results", help="输出目录")
    parser.add_argument("--test-category", help="只测试特定类别 (如: 代码编写, 调试)")
    parser.add_argument("--quick", action="store_true", help="快速测试模式 (只测部分用例)")

    args = parser.parse_args()

    tester = DevModelTester(args.output_dir)

    # 选择测试用例
    test_cases = DEV_TEST_CASES
    if args.test_category:
        test_cases = [tc for tc in DEV_TEST_CASES if tc["category"] == args.test_category]
        print(f"只测试类别: {args.test_category} ({len(test_cases)}个用例)")

    if args.quick:
        # 每个类别选一个代表用例
        from collections import defaultdict
        category_cases = defaultdict(list)
        for tc in test_cases:
            category_cases[tc["category"]].append(tc)

        test_cases = []
        for category, cases in category_cases.items():
            test_cases.append(cases[0])  # 取每个类别的第一个用例

        print(f"快速模式: 从{len(category_cases)}个类别中各选1例，共{len(test_cases)}个用例")

    print(f"\n🔍 日常开发能力测试套件")
    print(f"测试用例数: {len(test_cases)}")
    print(f"覆盖领域: {', '.join(sorted(set(tc['category'] for tc in test_cases)))}")

    # 测试 DeepSeek
    print(f"\n{'='*60}")
    print("第一阶段: 测试 DeepSeek")
    print(f"{'='*60}")

    results_ds = tester.test_model(args.deepseek_model, "DeepSeek Chat", test_cases)
    file_ds = tester.save_results(results_ds)

    # 测试 Claude
    print(f"\n{'='*60}")
    print("第二阶段: 测试 Claude")
    print(f"{'='*60}")

    results_cl = tester.test_model(args.claude_model, "Claude 3.5 Sonnet", test_cases)
    file_cl = tester.save_results(results_cl)

    # 对比分析
    print(f"\n{'='*60}")
    print("第三阶段: 对比分析")
    print(f"{'='*60}")

    comparison = tester.compare_dev_capabilities(results_ds, results_cl)

    print(f"\n✅ 测试完成!")
    print(f"结果文件:")
    print(f"  DeepSeek: {file_ds}")
    print(f"  Claude: {file_cl}")
    print(f"\n替代建议总结:")
    print(f"  {comparison['summary']['recommendation']}")
    print(f"  原因: {comparison['summary']['reason']}")

if __name__ == "__main__":
    main()