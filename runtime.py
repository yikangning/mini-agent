"""
runtime.py
----------
Agent 主循环 —— 一轮对话从用户输入到最终回复的完整流程。

对标 claw-code:
  src/runtime.py (会话管理) + src/query_engine.py (推理循环)
扩展方向:
  - 调整 MAX_TOOL_TURNS 控制最多工具调用轮次
  - 加 hooks（pre_tool / post_tool）用于日志、监控
  - 替换 client.chat.completions.create 为异步版本
"""

# 单次 Agent 推理最多允许的工具调用轮次
# 对标 claw-code: QueryEngineConfig.max_turns = 8
# 防止 LLM 进入工具调用死循环（bash 出错 → 重试 → 再出错 → 无限循环）
MAX_TOOL_TURNS = 10

import json
from tools import execute_tool


def _build_tool_calls_from_stream(message: dict) -> list[dict]:
    """从流式拼接完成的 message dict 里提取 tool_calls 列表（已在流式循环里组装好）。"""
    return message.get("tool_calls", [])


def run_agent_turn(
    messages: list,
    client,
    model: str,
    tools: list,
    trusted_tools: set,
    recently_denied: set,
) -> str:
    """
    执行一轮 Agent 推理，直到 LLM 返回 finish_reason=stop 或达到 MAX_TOOL_TURNS。
    会原地修改 messages，保留完整对话历史以支持多轮对话。
    返回 stop_reason: 'stop' | 'max_turns_reached'

    流程:
      LLM 推理 → finish_reason=tool_calls → 执行工具 → 回传结果 → 继续推理
                → finish_reason=stop      → 对话结束
    """
    finish_reason = None
    tool_turn_count = 0  # 工具调用轮次计数器

    while finish_reason != "stop":
        # 死循环保护：超过最大工具调用轮次则强制终止
        # 对标 claw-code: query_engine.py submit_message() 里的 max_turns 检查
        if tool_turn_count >= MAX_TOOL_TURNS:
            print(f"\n[WARN] 已达到最大工具调用轮次 ({MAX_TOOL_TURNS})，强制终止本轮推理")
            return "max_turns_reached"

        # ----- 发起流式请求 -----
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            stream=True,
        )

        # ----- 逐 chunk 处理流式响应 -----
        assembled: dict = {}          # 拼接中的 assistant 消息
        full_content      = ""
        reasoning_content = ""

        for chunk in stream:
            delta       = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            # 普通文本内容（实时打印）
            if delta.content:
                print(delta.content, end="", flush=True)
                full_content += delta.content

            # reasoning_content（部分模型支持，如 Kimi 的思维链）
            rc_delta = getattr(delta, "reasoning_content", None)
            if rc_delta:
                reasoning_content += rc_delta

            # tool_calls 分片拼接
            # 注意：id/name 只在首个 chunk 出现，arguments 分片累积
            if delta.tool_calls:
                if "tool_calls" not in assembled:
                    assembled["tool_calls"] = []

                for tc in delta.tool_calls:
                    idx = tc.index
                    # 确保列表长度足够
                    while len(assembled["tool_calls"]) <= idx:
                        assembled["tool_calls"].append({})

                    obj = assembled["tool_calls"][idx]
                    obj["index"] = idx

                    if tc.id:
                        obj["id"] = tc.id
                    if tc.type:
                        obj["type"] = tc.type
                    if tc.function:
                        if "function" not in obj:
                            obj["function"] = {}
                        if tc.function.name:
                            obj["function"]["name"] = tc.function.name
                        if tc.function.arguments:
                            obj["function"]["arguments"] = (
                                obj["function"].get("arguments", "") + tc.function.arguments
                            )

        # ----- 流式结束后处理 -----
        if reasoning_content:
            print(f"\n[THINKING] {reasoning_content}")

        if "tool_calls" in assembled:
            tool_turn_count += 1  # 每次实际执行工具才计数

            # Assistant 调用了工具 → 把请求加入历史，然后执行每个工具
            messages.append({
                "role": "assistant",
                "content": full_content,
                "reasoning_content": reasoning_content,
                "tool_calls": assembled["tool_calls"],
            })

            for tc in assembled["tool_calls"]:
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"])

                print(f"\n🔧 调用工具: {name}  参数: {args}")
                result = execute_tool(name, args, trusted_tools, recently_denied)
                print(f"   返回: {result}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        else:
            # 没有工具调用 → 这是最终回复，加入历史
            messages.append({"role": "assistant", "content": full_content})
            if finish_reason == "stop":
                print()  # 补换行

    return "stop"
