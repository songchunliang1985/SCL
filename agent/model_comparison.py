#!/usr/bin/env python3
"""
Claude Code 模型对比测试：DeepSeek vs Claude 3.5 Sonnet
测试两个模型在相同前端（Claude Code CLI）下的表现差异
"""

import os
import sys
import time
import json
import subprocess
import argparse
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 测试用例定义
TEST_CASES = [
    {
        "category": "代码生成",
        "prompt": "用Python实现快速排序算法，包含详细注释和测试用例",
        "evaluation_criteria": ["代码正确性", "注释完整性", "可读性"]
    },
    {
        "category": "逻辑推理",
        "prompt": """三个人参加比赛：A说B赢了，B说我没赢，C说我赢了。只有一个人说真话，谁赢了？
请逐步推理并给出答案。""",
        "evaluation_criteria": ["推理过程清晰", "答案正确", "逻辑严密"]
    },
    {
        "category": "中文理解",
        "prompt": "解释成语'画龙点睛'的典故、含义和现代用法",
        "evaluation_criteria": ["典故准确性", "含义解释清晰", "现代用法举例"]
    },
    {
        "category": "工具意识",
        "prompt": "我想查看当前目录下所有Python文件的行数统计，应该用什么命令？请详细说明步骤。",
        "evaluation_criteria": ["命令准确性", "步骤详细", "解释清晰"]
    },
    {
        "category": "创意写作",
        "prompt": "以'人工智能与人类未来'为主题，写一段200字左右的短文",
        "evaluation_criteria": ["主题贴合", "逻辑连贯", "语言优美"]
    },
    {
        "category": "指令遵循",
        "prompt": """请按以下格式回答：
1. 首先列出三个主要观点
2. 然后为每个观点提供例子
3. 最后总结

主题：远程工作的优缺点""",
        "evaluation_criteria": ["格式遵循", "内容完整", "结构清晰"]
    }
]

class ModelTester:
    """模型测试器"""

    def __init__(self, output_dir: str = "test_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

    def run_claude_command(self, model: str, prompt: str, timeout: int = 60) -> Tuple[Optional[str], float, Optional[Dict]]:
        """
        运行Claude Code CLI命令

        Args:
            model: 模型名称 (deepseek-chat, sonnet, opus等)
            prompt: 用户提示
            timeout: 超时时间(秒)

        Returns:
            (response, elapsed_time, error_info)
        """
        # 构建命令
        cmd = ["claude", "--model", model, "--print", prompt]

        print(f"  执行: claude --model {model} --print \"{prompt[:50]}...\"")

        start_time = time.time()
        try:
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ  # 传递当前环境变量（包含API Key）
            )
            elapsed = time.time() - start_time

            if result.returncode == 0:
                return result.stdout.strip(), round(elapsed, 2), None
            else:
                error_info = {
                    "returncode": result.returncode,
                    "stderr": result.stderr.strip(),
                    "stdout": result.stdout.strip()[:500]
                }
                return None, round(elapsed, 2), error_info

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            return None, round(elapsed, 2), {"error": f"超时 ({timeout}s)"}
        except Exception as e:
            elapsed = time.time() - start_time
            return None, round(elapsed, 2), {"error": str(e)}

    def test_model(self, model_name: str, model_label: str) -> Dict:
        """测试单个模型的所有用例"""
        print(f"\n{'='*60}")
        print(f"开始测试: {model_label} ({model_name})")
        print(f"{'='*60}")

        results = {
            "model": model_name,
            "label": model_label,
            "test_time": datetime.now().isoformat(),
            "total_cases": len(TEST_CASES),
            "successful_cases": 0,
            "failed_cases": 0,
            "total_time": 0,
            "cases": []
        }

        for i, test_case in enumerate(TEST_CASES):
            print(f"\n[{i+1}/{len(TEST_CASES)}] {test_case['category']}: {test_case['prompt'][:50]}...")

            # 运行测试
            response, elapsed, error = self.run_claude_command(
                model_name, test_case["prompt"]
            )

            case_result = {
                "category": test_case["category"],
                "prompt": test_case["prompt"],
                "elapsed_time": elapsed,
                "success": response is not None,
                "response": response[:2000] if response else None,  # 截断保存
                "error": error,
                "evaluation_criteria": test_case["evaluation_criteria"]
            }

            results["cases"].append(case_result)
            results["total_time"] += elapsed

            if response:
                results["successful_cases"] += 1
                print(f"  结果: 成功 ({elapsed}s, {len(response)}字符)")
                # 打印响应预览
                preview = response[:200].replace("\n", " ")
                print(f"  预览: {preview}...")
            else:
                results["failed_cases"] += 1
                print(f"  结果: 失败 ({elapsed}s)")
                if error:
                    print(f"  错误: {error.get('error', str(error))}")

        # 计算平均时间
        if results["successful_cases"] > 0:
            results["avg_time"] = round(results["total_time"] / results["successful_cases"], 2)
        else:
            results["avg_time"] = 0

        print(f"\n测试完成: {results['successful_cases']}/{results['total_cases']} 成功")
        print(f"总耗时: {results['total_time']}s, 平均: {results['avg_time']}s")

        return results

    def save_results(self, results: Dict, filename: str = None):
        """保存测试结果到文件"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_{results['model']}_{timestamp}.json"

        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"结果已保存: {filepath}")
        return filepath

    def compare_models(self, results_a: Dict, results_b: Dict):
        """比较两个模型的测试结果"""
        print(f"\n{'='*60}")
        print("模型对比报告")
        print(f"{'='*60}")

        comparison = {
            "comparison_time": datetime.now().isoformat(),
            "model_a": results_a["model"],
            "model_b": results_b["model"],
            "summary": {}
        }

        # 基础指标对比
        metrics = [
            ("success_rate", "成功率", lambda r: f"{r['successful_cases']}/{r['total_cases']}"),
            ("avg_time", "平均响应时间", lambda r: f"{r.get('avg_time', 0)}s"),
            ("total_time", "总耗时", lambda r: f"{r['total_time']}s"),
        ]

        print(f"\n📊 基础指标对比:")
        print(f"{'指标':<15} {results_a['label']:<20} {results_b['label']:<20} 差异")
        print("-" * 80)

        for key, label, getter in metrics:
            val_a = getter(results_a)
            val_b = getter(results_b)

            # 尝试解析数值比较
            try:
                num_a = float(val_a.replace('s', '').split('/')[0])
                num_b = float(val_b.replace('s', '').split('/')[0])

                if '时间' in label:
                    diff = num_a - num_b
                    diff_str = f"{'+' if diff > 0 else ''}{diff:.2f}s"
                    if diff > 0:
                        diff_str += f" ({results_b['label']}更快)"
                    else:
                        diff_str += f" ({results_a['label']}更快)"
                else:
                    diff = num_a - num_b
                    diff_str = f"{'+' if diff > 0 else ''}{diff:.1f}"
            except:
                diff_str = "N/A"

            print(f"{label:<15} {val_a:<20} {val_b:<20} {diff_str}")

        # 分项对比
        print(f"\n📈 分项表现对比:")
        print(f"{'测试类别':<15} {'模型A时间':<12} {'模型B时间':<12} {'差异':<10} {'质量点评'}")
        print("-" * 80)

        for i in range(len(TEST_CASES)):
            case_a = results_a["cases"][i]
            case_b = results_b["cases"][i]

            time_a = case_a["elapsed_time"]
            time_b = case_b["elapsed_time"]
            time_diff = time_a - time_b

            # 简单质量评估（基于响应长度和是否成功）
            if case_a["success"] and case_b["success"]:
                len_a = len(case_a["response"] or "")
                len_b = len(case_b["response"] or "")

                if len_a > len_b * 1.5:
                    quality = "A更详细"
                elif len_b > len_a * 1.5:
                    quality = "B更详细"
                else:
                    quality = "相当"
            elif case_a["success"]:
                quality = "仅A成功"
            elif case_b["success"]:
                quality = "仅B成功"
            else:
                quality = "均失败"

            print(f"{TEST_CASES[i]['category']:<15} {time_a:<12.1f}s {time_b:<12.1f}s "
                  f"{time_diff:>+7.1f}s {quality:<10}")

        # 保存对比报告
        comp_file = self.output_dir / f"comparison_{results_a['model']}_vs_{results_b['model']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(comp_file, "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

        print(f"\n对比报告已保存: {comp_file}")

        # 成本估算
        self.estimate_cost(results_a, results_b)

    def estimate_cost(self, results_a: Dict, results_b: Dict):
        """粗略估算成本差异"""
        print(f"\n💰 成本估算 (基于响应长度粗略估算):")

        # 假设每个字符≈0.25个token（中文较多）
        total_chars_a = sum(len(case["response"] or "") for case in results_a["cases"] if case["response"])
        total_chars_b = sum(len(case["response"] or "") for case in results_b["cases"] if case["response"])

        tokens_a = total_chars_a * 0.25
        tokens_b = total_chars_b * 0.25

        # 假设价格（每百万token）
        # DeepSeek: 输入¥0.14/1M，输出¥0.28/1M ≈ $0.02/1M输入，$0.04/1M输出
        # Claude 3.5 Sonnet: 输入$3/1M，输出$15/1M

        # 假设输入输出比例 1:4（简单估算）
        cost_a_usd = tokens_a / 1_000_000 * ((0.02 * 0.2) + (0.04 * 0.8))  # 加权平均
        cost_b_usd = tokens_b / 1_000_000 * ((3 * 0.2) + (15 * 0.8))  # 加权平均

        print(f"  {results_a['label']}: {total_chars_a:,} 字符 ≈ {tokens_a:,.0f} tokens")
        print(f"    估算成本: ${cost_a_usd:.4f} USD")
        print(f"  {results_b['label']}: {total_chars_b:,} 字符 ≈ {tokens_b:,.0f} tokens")
        print(f"    估算成本: ${cost_b_usd:.4f} USD")

        if cost_b_usd > 0:
            ratio = cost_b_usd / cost_a_usd if cost_a_usd > 0 else float('inf')
            print(f"  💡 成本比例: {results_b['label']} 是 {results_a['label']} 的 {ratio:.1f} 倍")

def main():
    parser = argparse.ArgumentParser(description="Claude Code 模型对比测试")
    parser.add_argument("--model1", default="deepseek-chat", help="第一个模型名称")
    parser.add_argument("--label1", default="DeepSeek Chat", help="第一个模型显示名称")
    parser.add_argument("--model2", default="sonnet", help="第二个模型名称")
    parser.add_argument("--label2", default="Claude 3.5 Sonnet", help="第二个模型显示名称")
    parser.add_argument("--output-dir", default="test_results", help="结果输出目录")
    parser.add_argument("--compare-only", action="store_true", help="仅比较已有结果文件")
    parser.add_argument("--results-file1", help="已有的第一个模型结果文件")
    parser.add_argument("--results-file2", help="已有的第二个模型结果文件")

    args = parser.parse_args()

    tester = ModelTester(args.output_dir)

    if args.compare_only:
        if not args.results_file1 or not args.results_file2:
            print("错误: --compare-only 需要指定 --results-file1 和 --results-file2")
            sys.exit(1)

        with open(args.results_file1, "r", encoding="utf-8") as f:
            results1 = json.load(f)
        with open(args.results_file2, "r", encoding="utf-8") as f:
            results2 = json.load(f)

        tester.compare_models(results1, results2)
    else:
        # 测试第一个模型
        results1 = tester.test_model(args.model1, args.label1)
        file1 = tester.save_results(results1)

        # 测试第二个模型
        results2 = tester.test_model(args.model2, args.label2)
        file2 = tester.save_results(results2)

        # 对比
        tester.compare_models(results1, results2)

        print(f"\n✅ 测试完成!")
        print(f"结果文件:")
        print(f"  {file1}")
        print(f"  {file2}")
        print(f"\n提示: 可以使用 --compare-only 模式重新比较:")
        print(f"  python {__file__} --compare-only --results-file1 {file1} --results-file2 {file2}")

if __name__ == "__main__":
    main()