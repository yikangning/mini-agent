"""
agent.py
--------
程序入口 —— 初始化客户端、会话状态，驱动主循环。
支持 --resume <session_id> 恢复上次会话。

对标 claw-code: src/main.py
"""

import argparse
import os

from dotenv import load_dotenv
from openai import OpenAI

from context import MAX_TOKENS, compress_messages, count_tokens, should_compress
from runtime import run_agent_turn
from session import (
    StoredSession,
    UsageSummary,
    list_sessions,
    load_session,
    new_session_id,
    save_session,
)
from tools import TOOLS

# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------

load_dotenv()

client = OpenAI(
    api_key=os.getenv("MOONSHOT_API_KEY"),
    base_url="https://api.moonshot.cn/v1",
)
MODEL = os.getenv("MOONSHOT_MODEL", "moonshot-v1-8k")

SYSTEM_PROMPT = (
    "你是一个本地代码助手，可以读写文件、执行 bash 命令、查询时间。"
    "在执行任何写入或执行操作前，你会等待用户确认。"
    "优先用最少的工具调用完成任务。"
)


# ---------------------------------------------------------------------------
# CLI 参数解析
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mini Agent CLI")
    parser.add_argument(
        "--resume", metavar="SESSION_ID",
        help="恢复指定会话（传入 session_id）"
    )
    parser.add_argument(
        "--list-sessions", action="store_true",
        help="列出所有已保存的会话"
    )
    return parser


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def main():
    parser = build_parser()
    args = parser.parse_args()

    # --list-sessions: 列出所有会话后退出
    if args.list_sessions:
        sessions = list_sessions()
        if not sessions:
            print("没有已保存的会话。")
        else:
            print(f"{'ID':>10}  {'创建时间':>25}  {'消息数':>6}  {'Token':>10}")
            print("-" * 60)
            for s in sessions:
                total = s.input_tokens + s.output_tokens
                print(f"{s.session_id[:8]}  {s.created_at[:19]:>25}  {len(s.messages):>6}  {total:>10}")
        return

    # 会话级状态
    usage = UsageSummary()
    trusted_tools: set = set()

    # --resume: 从已有会话恢复
    if args.resume:
        try:
            stored = load_session(args.resume)
            messages: list = list(stored.messages)
            session_id: str = stored.session_id
            usage.add(stored.input_tokens, stored.output_tokens)
            print(f"✅ 已恢复会话 {session_id[:8]}（{len(messages)} 条消息，历史 token: {usage}）\n")
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return
    else:
        # 新会话
        session_id = new_session_id()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        print(f"Mini Agent CLI  会话 ID: {session_id[:8]}  (输入 exit/quit 退出)\n")

    while True:
        try:
            user_input = input("你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        # 每轮对话开始前清空拒绝记录
        recently_denied: set = set()

        messages.append({"role": "user", "content": user_input})

        # 上下文状态显示
        current_tokens = count_tokens(messages)
        print(f"[CONTEXT] 估算 token: {current_tokens}/{MAX_TOKENS} ({current_tokens/MAX_TOKENS:.1%})")

        # 超阈值则压缩
        if should_compress(messages):
            print("[COMPRESS] 上下文过长，开始压缩...")
            messages = compress_messages(messages, client, MODEL)

        # 执行 Agent 推理，获取结果（含真实 token 用量）
        result = run_agent_turn(
            messages=messages,
            client=client,
            model=MODEL,
            tools=TOOLS,
            trusted_tools=trusted_tools,
            recently_denied=recently_denied,
        )

        # 更新 token 用量统计
        usage.add(result["input_tokens"], result["output_tokens"])
        print(f"[TOKEN] 本轮: in={result['input_tokens']} out={result['output_tokens']} | 累计: {usage}")

        if result["stop_reason"] == "max_turns_reached":
            print("[WARN] 本轮因达到最大工具调用次数而终止，对话历史已保留。")

        # 每轮对话结束后自动保存会话
        from datetime import datetime
        stored = StoredSession(
            session_id=session_id,
            created_at=datetime.now().isoformat(),
            messages=messages,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )
        save_path = save_session(stored)
        print(f"[SESSION] 已保存 → {save_path}")

    print("再见！")


if __name__ == "__main__":
    main()
