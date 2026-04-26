"""文件路径权限管理"""
import os


class PermissionManager:
    """管理动态文件路径权限系统。"""

    def __init__(self):
        self.allowed_paths: set = set()
        self.pending_approvals: dict = {}

    def is_allowed(self, path: str) -> bool:
        abs_path = os.path.abspath(os.path.expanduser(path))
        return any(abs_path == ap or abs_path.startswith(ap + os.sep) for ap in self.allowed_paths)

    @staticmethod
    def get_tool_path(fn_name: str, fn_args: dict) -> str:
        if fn_name == "search_files":
            return fn_args.get("directory", "~")
        return fn_args.get("path", "~")
