# Mini Agent CLI 🦀

一个从零独立实现的本地 AI Agent 命令行工具，对标 Claude Code / claw-code 核心架构。

## 项目结构

```
mini-agent-cli/
├── agent.py              # 程序入口，初始化 + 主循环        ← 对标 claw-code: src/main.py
├── runtime.py            # Agent 推理循环（流式 + 工具执行） ← 对标 src/runtime.py + query_engine.py
├── context.py            # token 计数 + 上下文压缩          ← 对标 src/context.py
├── tools/
│   ├── __init__.py       # 统一导出
│   ├── definitions.py    # 工具 JSON Schema（告诉 LLM 有哪些工具）← 对标 src/tools.py
│   ├── implementations.py# 工具实现函数 + TOOL_MAP 注册表  ← 对标 rust/crates/runtime/src/
│   └── permissions.py    # 三级权限门控                     ← 对标 rust/crates/runtime/src/permission_enforcer.rs
├── requirements.txt
├── .env.example
└── .gitignore
```

## 架构设计

### 消息流

```
用户输入
  → messages.append(user)
  → [context.py] token 计数 → 超阈值则压缩
  → [runtime.py] 流式推理
      → finish_reason=tool_calls
          → [tools/permissions.py] 权限检查
          → [tools/implementations.py] 工具执行
          → messages.append(tool_result) → 继续推理
      → finish_reason=stop → 打印回复 → 等待下一轮
```

### 权限分级

| 级别 | 工具 | 策略 |
|------|------|------|
| READ_ONLY | get_current_time, read_file, list_files | 直接执行，不询问 |
| WRITE | write_file | 首次询问，会话内信任后自动执行 |
| EXECUTE | run_bash | 每次询问（最高风险） |

## 快速开始

```bash
# 1. 克隆
git clone https://github.com/<你的用户名>/mini-agent-cli
cd mini-agent-cli

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 Moonshot API Key

# 4. 运行
python agent.py
```

## 如何扩展新工具

只需三步：

**Step 1** — 在 `tools/definitions.py` 的 `TOOLS` 列表追加 schema：
```python
{
    "type": "function",
    "function": {
        "name": "search_web",
        "description": "搜索网页内容...",
        "parameters": { ... }
    }
}
```

**Step 2** — 在 `tools/implementations.py` 实现函数并注册：
```python
def tool_search_web(args: dict) -> dict:
    ...

TOOL_MAP["search_web"] = tool_search_web
```

**Step 3** — 在 `tools/permissions.py` 决定权限级别：
```python
READ_ONLY = {..., "search_web"}  # 或加入 WRITE / EXECUTE
```

## 功能特性

- **流式输出** — 实时打印 LLM 回复，正确处理 tool_calls 分片拼接
- **多轮对话记忆** — 完整对话历史在会话内持久保留
- **上下文压缩** — 超过 75% token 阈值时自动压缩早期历史
- **三级权限门控** — 危险操作逐级确认，支持会话内信任缓存
- **拒绝记忆** — 记录本轮已拒操作，阻止 LLM 无限重试
- **bash 安全防御** — 静态黑名单拦截危险命令

## 后续计划

- [ ] RAG 支持（本地文档知识库）
- [ ] edit_file 工具（diff 级别修改，非全量覆写）
- [ ] Web UI（Gradio/Streamlit）
- [ ] 会话持久化（保存 / 恢复对话历史）
- [ ] 多 Agent 协作

## 技术栈

- Python 3.10+
- [Moonshot API](https://platform.moonshot.cn)（兼容 OpenAI 接口）
- `openai` · `python-dotenv` · `tiktoken`
