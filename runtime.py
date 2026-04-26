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
) -> dict:
    """
    执行一轮 Agent 推理，直到 LLM 返回 finish_reason=stop 或达到 MAX_TOOL_TURNS。
    会原地修改 messages，保留完整对话历史以支持多轮对话。
    返回 dict: {"stop_reason": str, "input_tokens": int, "output_tokens": int}

    流程:
      LLM 推理 → finish_reason=tool_calls → 执行工具 → 回传结果 → 继续推理
                → finish_reason=stop      → 对话结束
    """
    finish_reason   = None
    tool_turn_count = 0
    # 本轮累计的真实 token 用量（从 API 响应最后一个 chunk 读取）
    total_input_tokens  = 0
    total_output_tokens = 0

    while finish_reason != "stop":
        # 死循环保护：超过最大工具调用轮次则强制终止
        # 对标 claw-code: query_engine.py submit_message() 里的 max_turns 检查
        if tool_turn_count >= MAX_TOOL_TURNS:
            print(f"\n[WARN] 已达到最大工具调用轮次 ({MAX_TOOL_TURNS})，强制终止本轮推理")
            return {"stop_reason": "max_turns_reached",
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens}

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

            # usage 只在最后一个 chunk 出现，其余 chunk 该字段为 None
            # 注意：Moonshot API 会把 usage 放在 chunk.choices[0].usage 里（而不是 chunk.usage）
            usage = getattr(chunk.choices[0], "usage", None)
            if usage:
                if isinstance(usage, dict):  # 如果是字典
                    total_input_tokens  += usage.get("prompt_tokens", 0)
                    total_output_tokens += usage.get("completion_tokens", 0)
                else:                        # 如果是对象
                    total_input_tokens  += getattr(usage, "prompt_tokens", 0)
                    total_output_tokens += getattr(usage, "completion_tokens", 0)

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
                result_str = json.dumps(result, ensure_ascii=False)
                
                # 如果单次工具输出超过 1 万字符，因为前面外部截断无法处理工具的返回结果，工具返回可能会超过上下文长度
                # 所以这里需要截断工具的返回结果
                if len(result_str) > 10000:
                    truncated_msg = result_str[:10000] + "\n\n...[警告：输出过长已被截断，请使用 search_file 等工具精确查找]"
                else:
                    truncated_msg = result_str
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": truncated_msg,
                })

        else:
            # 没有工具调用 → 这是最终回复，加入历史
            messages.append({"role": "assistant", "content": full_content})
            if finish_reason == "stop":
                print()  # 补换行

    return {
        "stop_reason":    "stop",
        "input_tokens":  total_input_tokens,
        "output_tokens": total_output_tokens,
    }
