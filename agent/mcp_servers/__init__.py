"""
MCP Server 加载器 + Skills 热加载
工具从 mcp_config.json 动态加载，技能从 skills/ 文件夹热加载
"""

import os
import sys
import json
import importlib

# ── 路径解析（兼容 PyInstaller 打包模式） ─────────────
if getattr(sys, 'frozen', False):
    # 打包模式：可执行文件所在目录 / PyInstaller 解压目录
    _BASE_DIR = os.path.dirname(sys.executable)
    _BUNDLE_DIR = sys._MEIPASS
else:
    # 开发模式：项目根目录（此文件的上级目录）
    _BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _BUNDLE_DIR = _BASE_DIR

# MCP 服务配置文件路径
CONFIG_FILE = os.path.join(_BUNDLE_DIR, "mcp_config.json")
# 技能目录路径，每个子目录对应一个技能
SKILLS_DIR = os.path.join(_BUNDLE_DIR, "skills")


# ── McpLoader：负责从配置文件加载所有 MCP 工具 ────────
class McpLoader:
    """从 mcp_config.json 动态加载所有已启用的 MCP Server 模块。

    加载完成后汇总四个数据结构：
    - tools       : LLM function calling 格式的工具定义列表
    - tool_map    : 工具名 -> 可调用函数 的映射字典
    - tool_labels : 工具名 -> UI 显示标签 的映射字典
    - file_tools  : 需要文件系统权限确认的工具名集合
    """

    def __init__(self, config_file: str):
        # 配置文件路径
        self._config_file = config_file

    def load(self):
        """读取配置文件并逐一导入各 MCP Server 模块。
        返回四元组：(tools, tool_map, tool_labels, file_tools)
        """
        all_tools = []
        all_tool_map = {}
        all_tool_labels = {}
        file_tools = set()
        loaded = []

        # 配置文件不存在时直接返回空结构
        if not os.path.exists(self._config_file):
            print(f"[MCP] 配置文件不存在: {self._config_file}")
            return all_tools, all_tool_map, all_tool_labels, file_tools

        with open(self._config_file, "r", encoding="utf-8") as f:
            config = json.load(f)

        # 遍历所有 server，跳过 enabled=false 的条目
        for name, server_cfg in config.get("servers", {}).items():
            if not server_cfg.get("enabled", True):
                continue
            try:
                # 动态导入 mcp_servers.<name> 模块
                mod = importlib.import_module(f"mcp_servers.{name}")
                all_tools.extend(getattr(mod, "TOOLS", []))
                all_tool_map.update(getattr(mod, "TOOL_MAP", {}))
                all_tool_labels.update(getattr(mod, "TOOL_LABELS", {}))
                file_tools.update(getattr(mod, "PERMISSION_TOOLS", set()))
                loaded.append(f"{name}({len(getattr(mod, 'TOOLS', []))} tools)")
            except Exception as e:
                print(f"[MCP] 加载失败 {name}: {e}")

        print(f"[MCP] 已加载: {', '.join(loaded)}")
        return all_tools, all_tool_map, all_tool_labels, file_tools

    def reload(self):
        """热重载：重新读取配置并加载所有模块（支持运行时增删 MCP Server）。
        返回与 load() 相同的四元组。
        """
        # 清除已导入模块的缓存，确保重新导入拿到最新代码
        if os.path.exists(self._config_file):
            with open(self._config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            for name in config.get("servers", {}):
                mod_name = f"mcp_servers.{name}"
                if mod_name in sys.modules:
                    importlib.reload(sys.modules[mod_name])
        print("[MCP] 执行热重载...", flush=True)
        return self.load()


# ── SkillManager：负责技能的热加载与按需读取 ──────────
class SkillManager:
    """管理 skills/ 目录下的技能文件，支持热插拔（每次从磁盘读取）。

    技能目录结构：
        skills/
          translate/
            skill.md    ← 含 YAML frontmatter（name、description）+ 正文指令
          code-review/
            skill.md
          ...

    skill.md 格式：
        ---
        name: 翻译助手
        description: 中英文互译
        ---
        （正文：具体行为指令）
    """

    def __init__(self, skills_dir: str):
        # 技能根目录
        self._skills_dir = skills_dir

    @staticmethod
    def _parse_skill_md(filepath: str):
        """解析 skill.md 文件，提取 frontmatter 元数据和正文。
        返回 (meta_dict, body_str) 二元组。
        若无 frontmatter，meta_dict 为空字典，body_str 为完整内容。
        """
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        meta = {}
        body = content

        # 检测是否以 "---" 开头（YAML frontmatter 格式）
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                # 逐行解析 key: value
                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        meta[k.strip()] = v.strip()
                body = parts[2].strip()

        return meta, body

    def load_index(self):
        """扫描技能目录，返回轻量索引列表（每次从磁盘读取，支持热插拔）。

        只读取 frontmatter，不加载正文，速度快。
        返回格式：[{"key": "translate", "name": "翻译", "description": "中英互译"}, ...]
        """
        index = []
        if not os.path.isdir(self._skills_dir):
            return index

        for name in sorted(os.listdir(self._skills_dir)):
            skill_file = os.path.join(self._skills_dir, name, "skill.md")
            if not os.path.isfile(skill_file):
                continue
            try:
                meta, _ = self._parse_skill_md(skill_file)
                index.append({
                    "key": name,
                    "name": meta.get("name", name),
                    "description": meta.get("description", ""),
                })
            except Exception:
                # 解析失败时跳过该技能，不影响其他技能
                pass

        return index

    def get_content(self, skill_name: str):
        """按需读取指定技能的完整正文指令。
        返回正文字符串；技能不存在或读取失败时返回 None。
        """
        skill_file = os.path.join(self._skills_dir, skill_name, "skill.md")
        if not os.path.isfile(skill_file):
            return None
        try:
            _, body = self._parse_skill_md(skill_file)
            return body
        except Exception:
            return None


# ── 模块级单例（供外部直接调用） ─────────────────────
# 外部代码通过 from mcp_servers import load_all, load_skills_index, get_skill_content
# 使用这三个薄包装函数，内部委托给对应的单例实例
_mcp_loader    = McpLoader(CONFIG_FILE)
_skill_manager = SkillManager(SKILLS_DIR)


# ── 模块级公开接口（保持向后兼容） ───────────────────
def load_all():
    """加载所有已启用的 MCP Server，返回 (TOOLS, TOOL_MAP, TOOL_LABELS, FILE_TOOLS)"""
    return _mcp_loader.load()


def load_skills_index():
    """扫描 skills/ 目录，返回轻量索引列表（每次从磁盘读取，支持热插拔）。

    返回: [{"key": "translate", "name": "翻译", "description": "中英互译"}, ...]
    """
    return _skill_manager.load_index()


def get_skill_content(skill_name: str):
    """按需读取某个 skill 的完整指令内容（正文部分）。
    返回 None 表示不存在。"""
    return _skill_manager.get_content(skill_name)
