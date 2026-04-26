# Claude Code 模型对比测试指南

本指南帮助你系统性地测试 **Claude Code CLI 连接 DeepSeek** 和 **Claude Code CLI 连接 Anthropic 自家模型** 的差异。

## 📋 测试前提

确保你已具备：

1. **Claude Code CLI** 已安装并可用 (`claude --version`)
2. **DeepSeek API Key** 已配置（环境变量或Claude Code配置）
3. **Anthropic API Key** 已配置（环境变量或Claude Code配置）
4. 两个终端窗口（可选，用于并行测试）

## 🚀 快速开始

### 方案一：自动化测试（推荐）

运行自动化测试脚本：

```bash
# 进入 agent 目录
cd /path/to/agent

# 运行对比测试
python model_comparison.py
```

默认配置：
- 模型1: `deepseek-chat` (DeepSeek Chat)
- 模型2: `sonnet` (Claude 3.5 Sonnet)

自定义模型：
```bash
python model_comparison.py --model1 deepseek-chat --label1 "DeepSeek" --model2 opus --label2 "Claude Opus"
```

### 方案二：手动分终端测试

**终端 A (DeepSeek):**
```bash
# 设置环境变量（如果未全局配置）
export ANTHROPIC_API_KEY="你的-claude-key"
export DEEPSEEK_API_KEY="你的-deepseek-key"

# 测试 DeepSeek
claude --model deepseek-chat
# 然后输入测试问题
```

**终端 B (Claude):**
```bash
# 相同环境变量
export ANTHROPIC_API_KEY="你的-claude-key"
export DEEPSEEK_API_KEY="你的-deepseek-key"

# 测试 Claude
claude --model sonnet  # 或 opus, haiku
# 然后输入相同测试问题
```

### 方案三：非交互式快速测试

```bash
# DeepSeek 测试
claude --model deepseek-chat --print "用Python实现快速排序"

# Claude 测试  
claude --model sonnet --print "用Python实现快速排序"
```

## 🔬 测试用例设计

### 1. 代码能力测试
```bash
# 复杂代码生成
echo "实现一个完整的Flask REST API，包含用户认证、JWT令牌、SQLite数据库和单元测试" | claude --model deepseek-chat --print
echo "实现一个完整的Flask REST API，包含用户认证、JWT令牌、SQLite数据库和单元测试" | claude --model sonnet --print
```

### 2. 中文理解测试
```bash
# 中文成语和古文
echo "解释'塞翁失马，焉知非福'的哲学含义，并举例说明在现代生活中的应用" | claude --model deepseek-chat --print
```

### 3. 逻辑推理测试
```bash
# 逻辑谜题
echo "A说B在说谎，B说C在说谎，C说A和B都在说谎。谁在说真话？" | claude --model sonnet --print
```

### 4. 工具调用测试
```bash
# 文件操作指令
echo "如何在当前目录下查找所有包含'def test_'的Python文件？" | claude --model deepseek-chat --print
```

### 5. 创意写作测试
```bash
# 创意任务
echo "写一个关于AI助手获得自我意识后与人类对话的短篇故事开头" | claude --model sonnet --print
```

## 📊 评估维度

### 响应质量
- **准确性**：答案是否正确
- **完整性**：是否覆盖所有要点
- **结构化**：回答是否条理清晰
- **创造性**：是否有独特见解

### 性能指标
- **响应时间**：从发送到第一个token的时间
- **生成速度**：token生成速率
- **成功率**：是否正常返回（而非报错）

### 成本效率
- **token使用**：输入+输出token数量
- **成本对比**：相同任务的实际花费

### 特殊能力
- **中文理解**：成语、古文、方言
- **代码质量**：可运行性、规范性
- **工具意识**：是否能正确指导工具使用

## 📈 数据分析脚本

创建 `analyze_results.py` 进行深度分析：

```python
import json
from pathlib import Path

def analyze_test_results(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    print(f"模型: {data['model']}")
    print(f"测试时间: {data['test_time']}")
    print(f"成功率: {data['successful_cases']}/{data['total_cases']}")
    print(f"平均响应时间: {data['avg_time']}s")
    
    # 分项分析
    for i, case in enumerate(data['cases']):
        print(f"\n{i+1}. {case['category']}:")
        print(f"   时间: {case['elapsed_time']}s")
        print(f"   状态: {'成功' if case['success'] else '失败'}")
        if case['response']:
            print(f"   长度: {len(case['response'])}字符")

# 使用
analyze_test_results("test_results/test_deepseek-chat_20250411_153045.json")
```

## 🎯 重点测试场景

### 场景1：开发任务
```bash
# 代码调试
echo "这段Python代码有什么问题？如何修复？
def process_data(data):
    result = []
    for item in data:
        result.append(item * 2)
    return results" | claude --model deepseek-chat --print
```

### 场景2：文档分析
```bash
# 长文档总结
cat README.md | claude --model sonnet --print "请总结这个项目的主要功能和技术架构"
```

### 场景3：多步任务
```bash
# 复杂工作流
echo "我想建立一个简单的网页监控系统，需要：
1. 定时抓取网页内容
2. 检测内容变化
3. 发送邮件通知
请给出完整的技术方案和示例代码" | claude --model deepseek-chat --print
```

## 🔧 故障排除

### 问题1：模型不可用
```
错误：模型 'deepseek-chat' 未找到
```
**解决**：
1. 检查API Key配置：`echo $DEEPSEEK_API_KEY`
2. 查看Claude Code配置：`claude --help | grep model`
3. 尝试完整模型ID：`claude --model deepseek-chat`

### 问题2：超时错误
```
错误：请求超时 (60s)
```
**解决**：
1. 增加超时时间：脚本中调整 `timeout` 参数
2. 检查网络连接
3. 简化测试prompt

### 问题3：响应截断
```
响应被截断
```
**解决**：
1. Claude Code可能有输出长度限制
2. 使用 `--print` 模式可能有限制
3. 考虑分步测试

## 📝 记录模板

### 测试记录表
| 测试ID | 模型 | 测试类别 | 响应时间 | 质量评分 | 备注 |
|--------|------|----------|----------|----------|------|
| 001 | DeepSeek | 代码生成 | 5.2s | 4/5 | 代码正确但注释少 |
| 002 | Claude | 代码生成 | 8.7s | 5/5 | 代码+测试用例完整 |

### 质量评分标准
- **5分**：优秀，超出预期
- **4分**：良好，满足需求
- **3分**：一般，基本可用
- **2分**：较差，需要改进
- **1分**：差，无法使用

## 🎪 高级测试建议

### 1. 压力测试
```bash
# 连续测试
for i in {1..10}; do
    echo "测试 $i: 解释什么是RESTful API"
    claude --model deepseek-chat --print "解释什么是RESTful API" | wc -c
    sleep 2
done
```

### 2. 混合场景测试
创建测试文件 `mixed_test.txt`：
```
[代码] 实现二分查找
[推理] 三人说谎问题
[写作] AI未来短文
[分析] 项目架构建议
```

### 3. 成本跟踪
使用 tokenizer 估算实际成本：
```python
import tiktoken  # 近似估算

def estimate_tokens(text):
    encoding = tiktoken.get_encoding("cl100k_base")  # Claude使用
    return len(encoding.encode(text))
```

## 📁 结果目录结构

```
test_results/
├── raw/
│   ├── deepseek_chat_20250411_153045.json
│   └── claude_sonnet_20250411_153145.json
├── comparisons/
│   └── deepseek_vs_claude_20250411_153245.json
└── summary_20250411.md
```

## 💡 测试结论要点

1. **速度对比**：DeepSeek通常更快（国内节点优势）
2. **成本对比**：DeepSeek便宜约20-50倍
3. **质量对比**：Claude在结构化、安全过滤方面可能更优
4. **中文能力**：DeepSeek中文理解可能更好
5. **工具集成**：Claude Code + Claude模型集成度更高

## 🚨 注意事项

1. **API Key安全**：不要将包含API Key的测试结果公开
2. **成本控制**：测试时注意token使用，避免意外高消费
3. **网络环境**：确保稳定的网络连接
4. **模型可用性**：不同模型可能有不同时段可用性
5. **版本差异**：Claude Code更新可能影响测试结果

---

通过系统化测试，你可以获得数据支持，选择最适合你使用场景的模型配置。