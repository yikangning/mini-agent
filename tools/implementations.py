"""
tools/implementations.py
------------------------
工具的具体实现 —— 每个函数对应一个工具的真实逻辑。

对标 claw-code:
  src/tools.py (execute_tool) + rust/crates/runtime/src/file_ops.rs / bash.rs
扩展方式: 新增工具时，在这里加实现函数，再在 TOOL_MAP 里注册。
"""

import os
import subprocess
from datetime import datetime


# ---------------------------------------------------------------------------
# 危险命令黑名单（静态兜底层）
# 对标 claw-code: rust/crates/runtime/src/bash_validation.rs
# ---------------------------------------------------------------------------

_DANGEROUS_PATTERNS = [
    ("rm -rf /",     "删除根目录"),
    ("rm -rf ~",     "删除家目录"),
    ("sudo",         "提升权限"),
    ("> /etc/",      "写入系统配置"),
    (":(){ :|:& };:", "fork 炸弹"),
    ("mkfs",         "格式化磁盘"),
    ("dd if=",       "磁盘写入"),
]


def is_command_safe(command: str) -> tuple[bool, str]:
    """静态检查命令是否安全，返回 (是否安全, 拒绝原因)。"""
    for pattern, reason in _DANGEROUS_PATTERNS:
        if pattern in command:
            return False, reason
    return True, ""


# ---------------------------------------------------------------------------
# 工具实现函数
# ---------------------------------------------------------------------------

def tool_get_current_time(args: dict) -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def tool_read_file(args: dict) -> dict:
    path = args["path"]
    try:
        content = open(path, encoding="utf-8").read()
        return {"content": content}
    except Exception as e:
        return {"error": f"读取失败: {e}"}


def tool_list_files(args: dict) -> dict:
    path = args.get("path", ".")
    try:
        return {"files": sorted(os.listdir(path))}
    except Exception as e:
        return {"error": f"列目录失败: {e}"}


def tool_write_file(args: dict) -> dict:
    path, content = args["path"], args["content"]
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "success", "message": f"已写入 {len(content)} 字符到 {path}"}
    except Exception as e:
        return {"error": f"写入失败: {e}"}


def tool_run_bash(args: dict) -> dict:
    command = args["command"]
    safe, reason = is_command_safe(command)
    if not safe:
        return {"error": f"命令被安全规则拒绝: {reason}"}
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "命令执行超时（30 秒）"}
    except Exception as e:
        return {"error": f"执行失败: {e}"}


# ---------------------------------------------------------------------------
# 工具名 → 函数 映射表（注册表）
# 扩展方式: 新增工具时在这里加一行
# ---------------------------------------------------------------------------

TOOL_MAP: dict[str, callable] = {
    "get_current_time": tool_get_current_time,
    "read_file":        tool_read_file,
    "list_files":       tool_list_files,
    "write_file":       tool_write_file,
    "run_bash":         tool_run_bash,
}
