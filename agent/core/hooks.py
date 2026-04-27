"""Hook 管道 —— 工具调用的拦截中间件

支持 post-hook，按工具名模式匹配（支持 fnmatch 通配符）。
不匹配任何 hook 的工具直接透传，零开销。
"""

import fnmatch


class HookPipeline:
    """轻量工具调用拦截管道。

    用法:
        pipeline = HookPipeline()
        pipeline.add_post("rag_*", my_handler)

        # agent_runner 中:
        wrapped = pipeline.wrap(tool_name, original_fn)
        result = wrapped(**tool_args)
    """

    def __init__(self):
        self._post_hooks = []  # [(pattern, handler), ...]

    def add_post(self, pattern: str, handler):
        """注册 post-hook。handler(tool_name, tool_args, result_str) -> result_str 或 None 表示不修改。"""
        self._post_hooks.append((pattern, handler))

    def copy(self) -> "HookPipeline":
        """返回浅拷贝，可在此基础上添加临时 hook 而不影响原管道。"""
        new = HookPipeline()
        new._post_hooks = list(self._post_hooks)
        return new

    def wrap(self, tool_name: str, fn):
        """返回包装后的函数。无匹配 hook 则直接返回原函数。"""
        matching = [(p, h) for p, h in self._post_hooks if fnmatch.fnmatch(tool_name, p)]
        if not matching:
            return fn

        def _wrapped(**kwargs):
            result = fn(**kwargs)
            for _pattern, handler in matching:
                try:
                    new_result = handler(tool_name, kwargs, result)
                    if new_result is not None:
                        result = new_result
                except Exception:
                    pass
            return result

        return _wrapped
