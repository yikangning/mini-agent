"""
session.py
----------
会话持久化 —— 把对话历史和 token 用量保存到本地 JSON 文件，支持恢复。

对标 claw-code:
  src/session_store.py (StoredSession / save_session / load_session)
  src/models.py       (UsageSummary)
扩展方向:
  - 加密存储（敏感内容保护）
  - 云端同步
  - 多会话列表管理
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# 会话文件默认存放目录
SESSION_DIR = Path(".sessions")


# ---------------------------------------------------------------------------
# 数据结构
# 对标 claw-code: StoredSession + UsageSummary (src/models.py)
# ---------------------------------------------------------------------------

@dataclass
class UsageSummary:
    """Token 用量统计，跨轮次累计。"""
    input_tokens:  int = 0
    output_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens  += input_tokens
        self.output_tokens += output_tokens

    def __str__(self) -> str:
        return f"in={self.input_tokens} out={self.output_tokens} total={self.total}"


@dataclass
class StoredSession:
    """会话的可持久化状态。"""
    session_id:    str
    created_at:    str                # ISO 8601 时间戳
    messages:      list[dict]         # 完整对话历史
    input_tokens:  int = 0
    output_tokens: int = 0


# ---------------------------------------------------------------------------
# 保存 / 加载
# ---------------------------------------------------------------------------

def new_session_id() -> str:
    return uuid4().hex


def save_session(session: StoredSession, directory: Path | None = None) -> Path:
    """把会话写入 JSON 文件，返回文件路径。"""
    target_dir = directory or SESSION_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{session.session_id}.json"
    path.write_text(json.dumps(asdict(session), ensure_ascii=False, indent=2))
    return path


def load_session(session_id: str, directory: Path | None = None) -> StoredSession:
    """从 JSON 文件加载会话，找不到则抛出 FileNotFoundError。"""
    target_dir = directory or SESSION_DIR
    path = target_dir / f"{session_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"会话不存在: {session_id}  (查找路径: {path})")
    data = json.loads(path.read_text())
    return StoredSession(**data)


def list_sessions(directory: Path | None = None) -> list[StoredSession]:
    """列出所有已保存的会话，按创建时间倒序排列。"""
    target_dir = directory or SESSION_DIR
    if not target_dir.exists():
        return []
    sessions = []
    for path in target_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text())
            sessions.append(StoredSession(**data))
        except Exception:
            continue  # 跳过损坏的文件
    return sorted(sessions, key=lambda s: s.created_at, reverse=True)


# ---------------------------------------------------------------------------
# 便捷构造函数
# ---------------------------------------------------------------------------

def new_stored_session(messages: list[dict], usage: UsageSummary) -> StoredSession:
    """从当前 messages 和 usage 创建一个可保存的会话对象。"""
    return StoredSession(
        session_id=new_session_id(),
        created_at=datetime.now().isoformat(),
        messages=messages,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )
