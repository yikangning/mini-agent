"""
context.py
----------
上下文管理 —— token 计数 + 超阈值自动压缩。

对标 claw-code:
  src/context.py + query_engine.py (压缩触发逻辑)
扩展方向:
  - 调整 MAX_TOKENS / COMPRESS_THRESHOLD / KEEP_RECENT 来控制压缩策略
  - 可替换为更智能的摘要策略（如分段摘要、关键事件提取）
"""

import json
import tiktoken

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

MAX_TOKENS         = 128_000   # Kimi 的上下文窗口上限
COMPRESS_THRESHOLD = 0.75      # 超过 75% 时触发压缩
KEEP_RECENT        = 10        # 保留最近 10 轮完整对话（每轮 ≈ 2 条消息）


# ---------------------------------------------------------------------------
# Token 计数
# ---------------------------------------------------------------------------

def count_tokens(messages: list) -> int:
    """
    用 GPT-4 的 tokenizer 估算 messages 的 token 数。
    对 Kimi 模型误差在 10% 以内，足够用于触发阈值判断。
    """
    enc = tiktoken.encoding_for_model("gpt-4")
    total = 0
    for msg in messages:
        total += 4  # 每条消息固定开销
        for value in msg.values():
            if isinstance(value, str):
                total += len(enc.encode(value))
            elif isinstance(value, list):
                total += len(enc.encode(str(value)))
    return total


def should_compress(messages: list) -> bool:
    """判断当前 messages 是否需要压缩。"""
    return count_tokens(messages) > MAX_TOKENS * COMPRESS_THRESHOLD


# ---------------------------------------------------------------------------
# 上下文压缩
# ---------------------------------------------------------------------------

def compress_messages(messages: list, client, model: str) -> list:
    """
    将早期对话历史压缩为摘要，保留最近 KEEP_RECENT 轮完整对话。

    压缩策略:
      - messages[0]          → system 消息，永远保留
      - messages[-(N*2):]    → 最近 N 轮，原样保留
      - 中间部分             → 发给 LLM 生成摘要，替换为一条 assistant 摘要消息

    注意: 压缩会损失细节（临时约束、失败尝试等），这是已知取舍。
    """
    system_msg   = messages[0]
    recent       = messages[-(KEEP_RECENT * 2):]
    to_compress  = messages[1 : -(KEEP_RECENT * 2)]

    if not to_compress:
        return messages  # 没有可压缩的内容

    summary_prompt = f"""请将以下对话历史压缩成一段简洁的摘要。
摘要应包含：
1. 用户的核心需求和目标
2. 已完成的关键操作（特别是文件修改、命令执行）
3. 重要的中间结论和发现
4. 当前任务的进展状态
特别保留：失败的尝试和原因、用户的所有明确约束。

对话历史：
{json.dumps(to_compress, ensure_ascii=False, indent=2)}

请直接输出摘要，不要加任何前缀。"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": summary_prompt}],
        stream=False,
    )
    summary = response.choices[0].message.content

    compressed = [
        system_msg,
        {"role": "assistant", "content": f"[对话历史摘要]\n{summary}"},
        *recent,
    ]

    before = len(to_compress) + 1 + len(recent)  # +1 for system
    after  = len(compressed)
    print(f"\n[COMPRESS] {before} 条 → {after} 条（摘要 + 最近 {len(recent)} 条）")
    return compressed
