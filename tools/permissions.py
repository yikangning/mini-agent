"""
tools/permissions.py
--------------------
权限门控层 —— 决定每个工具调用是否需要用户确认。

对标 claw-code:
  src/permissions.py + rust/crates/runtime/src/permission_enforcer.rs
扩展方式:
  - 新增工具时，把它加入 READ_ONLY / WRITE / EXECUTE 其中一个集合
  - 如需新增权限级别（如 NETWORK），在这里扩展分支逻辑
"""

import json
from tools.implementations import TOOL_MAP

# ---------------------------------------------------------------------------
# 三级权限分类
# 对标 claw-code: PermissionEnforcer 的 READ_ONLY / workspace-write / execute 三层
# ---------------------------------------------------------------------------

READ_ONLY = {"get_current_time", "read_file", "list_files"}
WRITE     = {"write_file"}
EXECUTE   = {"run_bash"}


def _ask_user(tool_name: str, args: dict, trusted_tools: set,allow_trust=True) -> bool:
    """
    向用户展示操作详情并询问是否允许。
      y = 本次允许
      a = 本会话始终允许（加入 trusted_tools）
      n / 其他 = 拒绝
    """
    print(f"\n⚠️  Agent 请求执行: [{tool_name}]")
    print(f"   参数: {json.dumps(args, ensure_ascii=False, indent=2)}")
    if allow_trust:
        prompt = "是否允许? (y=允许一次 / a=始终允许 / n=拒绝): "
    else :
        prompt = "是否允许? (y=允许一次 / n=拒绝): "
    choice = input(prompt).strip().lower()
    if choice == "a" and allow_trust:
        trusted_tools.add(tool_name)
        print(f"   ✅ [{tool_name}] 已加入本会话信任列表")
        return True
    elif choic == a and not allow_trust:
        return True
    elif choice == "y":
        return True
    else:
        print("   ❌ 已拒绝")
        return False


def execute_tool(
    name: str,
    args: dict,
    trusted_tools: set,
    recently_denied: set,
) -> dict | str:
    """
    带权限门控的工具执行入口。

    执行顺序:
      1. 检查是否是本轮已拒绝的操作 → 直接返回错误，不再弹窗
      2. READ_ONLY → 直接执行
      3. EXECUTE   → 每次询问（最高风险）
      4. WRITE     → 信任后跳过询问
    """
    if name not in TOOL_MAP:
        return {"error": f"未知工具: {name}"}

    # 本轮已拒绝过的调用，不再重复弹窗
    deny_key = (name, json.dumps(args, sort_keys=True))
    if deny_key in recently_denied:
        return {"error": "此操作本轮已被拒绝，请换个方案或告知用户"}

    # 只读 → 直接执行
    if name in READ_ONLY:
        return TOOL_MAP[name](args)

    # 执行类 → 每次询问（即使已信任也问，最高风险）
    if name in EXECUTE:
        if  not _ask_user(name, args, trusted_tools,allow_trust=False):
            recently_denied.add(deny_key)
            return {"error": "用户拒绝"}

    # 写入类 → 首次询问，信任后自动执行
    elif name in WRITE:
        if name not in trusted_tools:
            if not _ask_user(name, args, trusted_tools):
                recently_denied.add(deny_key)
                return {"error": "用户拒绝"}

    return TOOL_MAP[name](args)
