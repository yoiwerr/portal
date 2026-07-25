"""
Alfred 记忆系统。

L1: 对话内记忆 — PostgreSQL sessions/messages（已实现 ✅）
L2: 跨会话记忆 — PGVector session_memory collection
L3: 用户画像   — PGVector user_profile collection

用法:
    from memory.session_memory import SessionMemory
    from memory.user_profile import UserProfile
"""

from memory.session_memory import SessionMemory
from memory.user_profile import UserProfile
