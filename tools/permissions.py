"""
tools/permissions.py
--------------------
权限门控层 —— 决定每个工具调用是否需要用户确认。

对标 claw-code:
  src/permissions.py (ToolPermissionContext dataclass)
  rust/crates/runtime/src/permission_enforcer.rs
改进点（相比原来的裸 set）:
  - PermissionContext dataclass 封装，frozen=True 保证不可变
  - 支持 deny_prefixes 前缀批量拒绝（如 "file_delete" 前缀）
  - 支持运行时动态构建权限上下文
扩展方式:
  - 新增工具时，把它加入 READ_ONLY / WRITE / EXECUTE 其中一个集合
  - 如需新增权限级别（如 NETWORK），在这里扩展分支逻辑
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from tools.implementations import TOOL_MAP

# ---------------------------------------------------------------------------
# 三级权限分类
# 对标 claw-code: PermissionEnforcer 的三层
# ---------------------------------------------------------------------------

READ_ONLY = {"get_current_time", "read_file", "list_files", "search_file"}
WRITE     = {"write_file", "edit_file"}
EXECUTE   = {"run_bash"}


# ---------------------------------------------------------------------------
# PermissionContext dataclass
# 对标 claw-code: src/permissions.py ToolPermissionContext
# 相比裸 set 的优势: frozen=True 不可变 + 支持前缀批量拒绝
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PermissionContext:
    """
    描述当前会话的工具黑名单。frozen=True 保证权限状态不可变。

    deny_names:    精确工具名黑名单（完全匹配）
    deny_prefixes: 前缀黑名单，如 ("file_delete",) 可批量拒绝所有 file_delete* 工具
    """
    deny_names:    frozenset[str]   = field(default_factory=frozenset)
    deny_prefixes: tuple[str, ...]  = ()

    @classmethod
    def from_lists(
        cls,
        deny_names:    list[str] | None = None,
        deny_prefixes: list[str] | None = None,
    ) -> "PermissionContext":
        return cls(
            deny_names=frozenset(n.lower() for n in (deny_names or [])),
            deny_prefixes=tuple(p.lower() for p in (deny_prefixes or [])),
        )

    @classmethod
    def allow_all(cls) -> "PermissionContext":
        """默认上下文：不拒绝任何工具。"""
        return cls()

    def blocks(self, tool_name: str) -> bool:
        """判断指定工具是否被当前上下文拒绝。"""
        lowered = tool_name.lower()
        return (
            lowered in self.deny_names
            or any(lowered.startswith(p) for p in self.deny_prefixes)
        )


# ---------------------------------------------------------------------------
# 用户确认交互
# ---------------------------------------------------------------------------

def _ask_user(tool_name: str, args: dict, trusted_tools: set) -> bool:
    """
    向用户展示操作详情并询问是否允许。
      y = 本次允许
      a = 本会话始终允许（加入 trusted_tools）
      n / 其他 = 拒绝
    """
    print(f"\n⚠️  Agent 请求执行: [{tool_name}]")
    print(f"   参数: {json.dumps(args, ensure_ascii=False, indent=2)}")
    choice = input("是否允许? (y=允许一次 / a=始终允许 / n=拒绝): ").strip().lower()
    if choice == "a":
        trusted_tools.add(tool_name)
        print(f"   ✅ [{tool_name}] 已加入本会话信任列表")
        return True
    elif choice == "y":
        return True
    else:
        print("   ❌ 已拒绝")
        return False


# ---------------------------------------------------------------------------
# 带权限门控的工具执行入口
# ---------------------------------------------------------------------------

def execute_tool(
    name: str,
    args: dict,
    trusted_tools: set,
    recently_denied: set,
    permission_ctx: PermissionContext | None = None,
) -> dict | str:
    """
    带权限门控的工具执行入口。

    执行顺序:
      1. PermissionContext 黑名单检查（配置层拒绝，不询问）
      2. 检查是否是本轮已拒绝的操作
      3. READ_ONLY → 直接执行
      4. EXECUTE   → 每次询问（最高风险）
      5. WRITE     → 信任后跳过询问
    """
    if name not in TOOL_MAP:
        return {"error": f"未知工具: {name}"}

    # 配置层黑名单（PermissionContext）
    ctx = permission_ctx or PermissionContext.allow_all()
    if ctx.blocks(name):
        return {"error": f"工具 [{name}] 已被权限配置禁用"}

    # 本轮已拒绝过的调用，不再重复弹窗
    deny_key = (name, json.dumps(args, sort_keys=True))
    if deny_key in recently_denied:
        return {"error": "此操作本轮已被拒绝，请换个方案或告知用户"}

    # 只读 → 直接执行
    if name in READ_ONLY:
        return TOOL_MAP[name](args)

    # 执行类 → 每次询问
    if name in EXECUTE:
        if name not in trusted_tools and not _ask_user(name, args, trusted_tools):
            recently_denied.add(deny_key)
            return {"error": "用户拒绝"}

    # 写入类 → 首次询问，信任后自动执行
    elif name in WRITE:
        if name not in trusted_tools:
            if not _ask_user(name, args, trusted_tools):
                recently_denied.add(deny_key)
                return {"error": "用户拒绝"}

    return TOOL_MAP[name](args)
