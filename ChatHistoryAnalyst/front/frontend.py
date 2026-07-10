import streamlit as st
import requests
import re
import os

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1")

# ── Page config ──────────────────────────────────
st.set_page_config(
    page_title="ChatLab",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════
# Global CSS — Neo-Minimal Dark
# ═══════════════════════════════════════════════════
st.markdown("""
<style>
    /* ── Root tokens ───────────────────────── */
    :root {
        --bg:       #0d0d0f;
        --bg-card:  #141417;
        --bg-hover: #1a1a1f;
        --border:   #2a2a30;
        --border-active: #3a3a44;
        --fg:       #e4e4e7;
        --fg-soft:  #a1a1aa;
        --fg-muted: #71717a;
        --fg-dim:   #52525b;
        --accent:   #8b9cf7;
        --accent-dim: #6366f1;
        --red:      #f87171;
        --amber:    #fbbf24;
        --green:    #4ade80;
    }

    /* ── Global ───────────────────────────────── */
    .stApp {
        background: var(--bg);
    }
    .stApp * {
        font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'Segoe UI', system-ui, sans-serif !important;
    }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* ── Typography ────────────────────────────── */
    h1, h2, h3, h4, h5, h6 {
        color: var(--fg) !important;
        font-weight: 500 !important;
        letter-spacing: -0.02em !important;
    }
    p, span, div, label, caption {
        color: var(--fg-soft);
    }

    /* ── Sidebar ───────────────────────────────── */
    [data-testid="stSidebar"] {
        background: #0a0a0d;
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebar"] .block-container {
        padding: 1rem 0.8rem;
    }
    [data-testid="stSidebar"] hr {
        border-color: var(--border);
        margin: 0.6rem 0;
    }
    [data-testid="stSidebar"] .stMarkdown p {
        font-size: 0.72rem;
    }
    [data-testid="stSidebar"] [data-testid="stCaption"] {
        color: var(--fg-dim);
        font-size: 0.62rem;
    }

    /* ── Buttons — ghost style ─────────────────── */
    .stButton > button {
        background: transparent !important;
        color: var(--fg-soft) !important;
        border: 1px solid var(--border) !important;
        border-radius: 6px !important;
        font-weight: 450 !important;
        font-size: 0.78rem !important;
        padding: 0.4rem 0.9rem !important;
        transition: all 0.15s ease !important;
        letter-spacing: -0.01em !important;
    }
    .stButton > button:hover {
        background: var(--bg-hover) !important;
        border-color: var(--border-active) !important;
        color: var(--fg) !important;
    }
    .stButton > button:active {
        background: #1e1e24 !important;
        border-color: var(--accent-dim) !important;
    }

    /* ── Inputs ─────────────────────────────────── */
    input, textarea {
        background: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 6px !important;
        color: var(--fg) !important;
        font-size: 0.8rem !important;
    }
    input:focus, textarea:focus {
        border-color: var(--accent-dim) !important;
        box-shadow: 0 0 0 2px rgba(99,102,241,0.15) !important;
    }
    input::placeholder, textarea::placeholder {
        color: var(--fg-dim) !important;
    }

    /* ── File uploader ─────────────────────────── */
    [data-testid="stFileUploader"] section {
        border: 1px dashed var(--border) !important;
        border-radius: 8px !important;
        background: var(--bg-card) !important;
        padding: 1rem !important;
    }
    [data-testid="stFileUploader"] section:hover {
        border-color: var(--border-active) !important;
    }

    /* ── Checkbox ───────────────────────────────── */
    .stCheckbox label span {
        color: var(--fg-soft) !important;
        font-size: 0.75rem !important;
    }

    /* ── Dividers ───────────────────────────────── */
    hr {
        border-color: var(--border) !important;
        margin: 0.8rem 0 !important;
    }

    /* ── Tabs ────────────────────────────────────── */
    .stTabs [data-baseweb="tab"] {
        color: var(--fg-muted) !important;
        font-size: 0.75rem !important;
        font-weight: 450 !important;
        padding: 0.3rem 0.6rem !important;
    }
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        color: var(--fg) !important;
    }
    .stTabs [data-baseweb="tab-border"] {
        background: var(--accent-dim) !important;
        height: 1.5px !important;
    }

    /* ── Containers (cards / status) ─────────────── */
    [data-testid="stVerticalBlock"] > div[data-testid="stVerticalBlock"] {
        gap: 0.4rem;
    }

    /* ═══════════════════════════════════════════════
       Custom classes
       ═══════════════════════════════════════════════ */

    /* Status row in sidebar */
    .status-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.3rem 0;
        font-size: 0.7rem;
        border-bottom: 1px solid #1c1c22;
    }
    .status-row:last-child { border-bottom: none; }
    .status-label { color: var(--fg-muted); }
    .status-value { font-weight: 500; }

    /* Chat bubble */
    .bubble {
        max-width: 78%;
        padding: 0.45rem 0.75rem;
        border-radius: 8px;
        margin-bottom: 0.35rem;
        font-size: 0.78rem;
        line-height: 1.55;
        color: var(--fg);
    }
    .bubble-mine {
        background: #1a1a24;
        border: 1px solid #2a2a38;
        margin-left: auto;
        text-align: right;
    }
    .bubble-other {
        background: var(--bg-card);
        border: 1px solid var(--border);
        margin-right: auto;
        text-align: left;
    }
    .bubble-sender {
        font-size: 0.6rem;
        font-weight: 500;
        margin-bottom: 2px;
    }
    .bubble-sender-mine { color: var(--accent); }
    .bubble-sender-other { color: var(--fg-muted); }

    /* Big number for emotion score */
    .metric {
        text-align: center;
        padding: 0.6rem 0;
    }
    .metric-value {
        font-size: 2.8rem;
        font-weight: 350;
        letter-spacing: -0.04em;
        line-height: 1;
    }
    .metric-label {
        font-size: 0.62rem;
        color: var(--fg-muted);
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-top: 0.25rem;
    }

    /* Tag pill */
    .tag {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 99px;
        font-size: 0.62rem;
        font-weight: 450;
        border: 1px solid var(--border);
        color: var(--fg-soft);
        margin-right: 0.25rem;
        margin-bottom: 0.25rem;
    }

    /* Data bar */
    .data-bar {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.4rem 0.65rem;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 6px;
        font-size: 0.7rem;
        margin-bottom: 0.5rem;
    }
    .data-bar-count {
        font-weight: 550;
        font-size: 0.9rem;
        color: var(--fg);
        letter-spacing: -0.02em;
    }

    /* Suggestion step */
    .step {
        display: flex;
        align-items: flex-start;
        gap: 0.55rem;
        margin-bottom: 0.45rem;
        font-size: 0.78rem;
        color: var(--fg-soft);
    }
    .step-num {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 20px;
        height: 20px;
        border-radius: 50%;
        border: 1px solid var(--border-active);
        color: var(--fg-soft);
        font-size: 0.62rem;
        font-weight: 500;
        flex-shrink: 0;
    }

    /* Empty state */
    .empty-state {
        text-align: center;
        padding: 2rem 0;
    }
    .empty-state p {
        color: var(--fg-dim);
        font-size: 0.78rem;
    }

    /* Info / success / warning overrides — roomy & readable */
    .stAlert {
        border-radius: 8px !important;
        border: 1px solid var(--border) !important;
        background: var(--bg-card) !important;
        font-size: 0.82rem !important;
        line-height: 1.6 !important;
        padding: 0.9rem 1rem !important;
        min-height: 60px !important;
        word-break: break-word !important;
    }
    .stAlert [data-testid="stMarkdown"] p {
        color: var(--fg-soft) !important;
        font-size: 0.82rem !important;
        line-height: 1.6 !important;
    }

    /* ── Expander / dialog minimum sizing ─────── */
    [data-testid="stExpander"] details {
        min-height: 400px !important;
        min-width: 500px !important;
    }
    [data-testid="stExpander"] .streamlit-expanderContent {
        max-height: 600px;
        overflow-y: auto;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 4px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #2a2a30; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #3a3a40; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════
# Session state
# ═══════════════════════════════════════════════════
DEFAULTS = {
    "parsed_chats": [],
    "upload_message": "",
    "upload_error": None,
    "last_file_key": None,
    "manual_input": "",
    "result_tab": None,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ═══════════════════════════════════════════════════
# Sidebar — ultra-compact status panel
# ═══════════════════════════════════════════════════
with st.sidebar:
    st.markdown(
        '<p style="font-size:0.68rem;font-weight:550;letter-spacing:0.06em;'
        'text-transform:uppercase;color:#71717a;margin-bottom:0.6rem;">ChatLab</p>',
        unsafe_allow_html=True,
    )

    chat_count = len(st.session_state.get("parsed_chats", []))
    target = st.session_state.get("cfg_target", "对方")

    st.markdown(f"""
    <div class="status-row">
        <span class="status-label">消息</span>
        <span class="status-value" style="color:{'var(--green)' if chat_count > 0 else 'var(--fg-dim)'};">{chat_count}</span>
    </div>
    <div class="status-row" style="border-bottom:none;">
        <span class="status-label">对象</span>
        <span class="status-value" style="color:var(--accent-dim);">{target}</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.caption("v0.1")


# ═══════════════════════════════════════════════════
# Main area
# ═══════════════════════════════════════════════════

# ── Compact header ──
st.markdown("""
<div style="margin-bottom:0.6rem;">
    <h3 style="margin:0 0 0.15rem 0;font-size:1.1rem;font-weight:500;color:#e4e4e7;">
        聊天记录分析
    </h3>
    <p style="color:#71717a;font-size:0.72rem;margin:0;">
        上传聊天记录文本，AI 解析情感、气氛与沟通模式
    </p>
</div>
""", unsafe_allow_html=True)

# ── Shared helpers ──
def _get_chats():
    result = list(st.session_state.get("parsed_chats", []))
    if not result and st.session_state.get("manual_input", "").strip():
        pattern = r"\[(.*?)\s+(.*?)\][:：]\s*(.*)"
        for line in st.session_state.manual_input.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(pattern, line)
            if m:
                sender, time, content = m.groups()
                result.append({"sender": sender, "content": content, "timestamp": time})
    return result


def _build_payload():
    return {
        "target_person": st.session_state.get("cfg_target", "对方"),
        "recent_chat": _get_chats(),
        "background_info": st.session_state.get("cfg_bg", "").strip() or None,
    }


def _call_skill(endpoint: str, payload: dict) -> dict | None:
    try:
        resp = requests.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=120)
    except requests.ConnectionError:
        st.error("无法连接后端，请确认服务已启动")
        return None
    if resp.status_code != 200:
        st.error(f"请求失败 HTTP {resp.status_code}")
        st.code(resp.text[:500])
        return None
    return resp.json()


st.markdown("---")

# ── Two-column layout ──
left, right = st.columns([1, 1], gap="medium")

with left:
    st.markdown(
        '<p style="font-size:0.65rem;font-weight:500;color:#71717a;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">导入</p>',
        unsafe_allow_html=True,
    )

    upload_tab, manual_tab = st.tabs(["文件上传", "手动输入"])

    with upload_tab:
        uploaded_file = st.file_uploader(
            "拖拽文件或点击选择",
            type=["txt", "json", "md"],
            key="chat_file_uploader",
            label_visibility="collapsed",
        )
        st.caption("TXT · JSON · MD（纯文本格式）")
        with st.expander("📋 完整导入格式说明", expanded=False):
            st.markdown("""
### ChatLab 支持的聊天记录格式

每行一条消息，格式固定为：

```
[发送者 时间]: 消息内容
```

#### 格式规则

| 字段 | 说明 | 示例 |
|------|------|------|
| 发送者 | 人名或昵称，需保持一致 | `张三`、`我`、`对方` |
| 时间 | 任意格式均可识别 | `2024-06-01 10:30`、`10:30`、`06-01 22:00` |
| 分隔符 | 英文 `:` 或中文 `：` 均可 | `[张三 10:30]: 你好` |
| 消息内容 | 该条消息的完整文本 | 不能换行，不能为空 |

#### 正确示例

```
[张三 2024-06-01 10:30]: 你好，今天有空一起吃个饭吗？
[我 2024-06-01 10:32]: 好啊，几点？
[张三 2024-06-01 10:33]: 十二点怎么样？老地方
[我 2024-06-01 10:35]: 没问题，到时候见
[张三 2024-06-01 10:36]: 好的，不见不散
```

#### 支持的文件类型

| 类型 | 扩展名 | 说明 |
|------|--------|------|
| 文本文件 | `.txt` `.md` | 纯文本，每行一条消息 |
| JSON 文件 | `.json` | 数组格式 `[{"sender":"...","timestamp":"...","content":"..."}]` |

---

### 🪄 万能提示词：让 AI 帮你格式化

如果你手头是**微信截图、QQ 聊天记录、短信、PDF 文档**等你无法直接粘贴的内容，把下面的提示词复制发给任意大模型（ChatGPT、DeepSeek、通义千问等），它会自动转换为 ChatLab 可读的格式：

> 请将我提供的聊天记录转换为以下固定格式，每行一条消息：
>
> `[发送者名称 时间]: 消息内容`
>
> 规则：
> 1. 方括号内「发送者」和「时间」之间用空格分隔
> 2. 方括号后跟冒号（中英文均可），冒号后有一个空格，然后是消息正文
> 3. 每条消息占一行，不要有空行
> 4. 时间格式保持一致（如全部用 "HH:MM" 或 "YYYY-MM-DD HH:MM"）
> 5. 同一个人名字保持统一
> 6. 忽略系统消息（"你撤回了一条消息"、"对方正在输入..."等）
> 7. 只输出格式化后的文本，不要加任何解释或代码块标记
>
> 以下是需要转换的聊天记录：
>
> [在这里粘贴你的原始聊天记录]

#### 使用流程

1. 🖼️ 截图/文档 → 用手机或工具提取文字
2. 🤖 打开任意大模型 → 粘贴上面的万能提示词
3. 📋 将 AI 输出结果复制到「手动输入」框
4. ✅ 点击分析按钮

> 详细文档见 `docs/如何导入正确格式.md`
            """)

        if uploaded_file is not None:
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.last_file_key != file_key:
                st.session_state.last_file_key = file_key
                with st.spinner("解析中…"):
                    try:
                        resp = requests.post(
                            f"{BASE_URL}/upload_chat_file",
                            files={"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)},
                            data={
                                "target_person": st.session_state.get("cfg_target", "对方"),
                            },
                            timeout=180,
                        )
                    except requests.ConnectionError:
                        st.session_state.upload_error = "无法连接后端服务"
                        st.session_state.parsed_chats = []
                        st.session_state.upload_message = ""
                    else:
                        if resp.status_code == 200:
                            data = resp.json()
                            st.session_state.parsed_chats = data.get("parsed_chats", [])
                            st.session_state.upload_message = data.get("message", "")
                            st.session_state.upload_error = None
                        else:
                            st.session_state.parsed_chats = []
                            st.session_state.upload_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                            st.session_state.upload_message = ""
                st.rerun()

        if st.session_state.upload_error:
            st.error(st.session_state.upload_error)
        elif st.session_state.upload_message and st.session_state.parsed_chats:
            st.success(st.session_state.upload_message)

    with manual_tab:
        manual_input = st.text_area(
            "按格式粘贴聊天记录",
            value=st.session_state.manual_input,
            height=250,
            placeholder="[张三 2024-06-01 10:30]: 你好，今天有空吗？\n[李四 2024-06-01 10:32]: 有的，怎么了？\n[张三 2024-06-01 10:33]: 十二点老地方见？\n[李四 2024-06-01 10:35]: 没问题\n[张三 2024-06-01 10:36]: 好的，不见不散",
            key="widget_manual_input",
            label_visibility="collapsed",
        )
        st.session_state.manual_input = manual_input
        st.caption("格式：`[发送者 时间]: 消息内容`，每行一条")

    # ── Message preview ──
    st.markdown(
        '<p style="font-size:0.65rem;font-weight:500;color:#71717a;'
        'text-transform:uppercase;letter-spacing:0.08em;margin:0.6rem 0 0.3rem;">预览</p>',
        unsafe_allow_html=True,
    )

    chats = st.session_state.get("parsed_chats", [])

    if not chats and st.session_state.get("manual_input", "").strip():
        pattern = r"\[(.*?)\s+(.*?)\][:：]\s*(.*)"
        for line in st.session_state.manual_input.splitlines():
            line = line.strip()
            if not line:
                continue
            m = re.match(pattern, line)
            if m:
                sender, time, content = m.groups()
                chats.append({"sender": sender, "content": content, "timestamp": time})

    if chats:
        with st.container(height=350):
            for chat in chats:
                is_me = "我" in chat.get("sender", "")
                bubble_class = "bubble-mine" if is_me else "bubble-other"
                sender_class = "bubble-sender-mine" if is_me else "bubble-sender-other"
                st.markdown(
                    f"""
                    <div class="bubble {bubble_class}">
                        <div class="bubble-sender {sender_class}">
                            {chat.get('sender','?')} · {chat.get('timestamp','')}
                        </div>
                        <span>{chat.get('content','')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("上传文件或手动输入后，解析结果会出现在这里", icon="↑")


with right:
    chat_count = len(st.session_state.get("parsed_chats", []))

    # ── Data bar ──
    if chat_count > 0:
        st.markdown(f"""
        <div class="data-bar">
            <span class="data-bar-count">{chat_count}</span>
            <span style="color:var(--fg-muted);">条消息已加载</span>
        </div>
        """, unsafe_allow_html=True)

    # ── Config ──
    st.markdown(
        '<p style="font-size:0.65rem;font-weight:500;color:#71717a;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">配置</p>',
        unsafe_allow_html=True,
    )

    if "cfg_target" not in st.session_state:
        st.session_state.cfg_target = "对方"
    if "cfg_bg" not in st.session_state:
        st.session_state.cfg_bg = ""
    st.text_input(
        "目标对象",
        key="cfg_target",
        placeholder="对方昵称",
        label_visibility="collapsed",
    )
    st.text_area(
        "补充背景（选填）",
        key="cfg_bg",
        placeholder="性格特点、关系背景…",
        height=55,
        label_visibility="collapsed",
    )
    st.markdown("---")

    # ── Action buttons ──
    st.markdown(
        '<p style="font-size:0.65rem;font-weight:500;color:#71717a;'
        'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:0.3rem;">分析</p>',
        unsafe_allow_html=True,
    )

    bc1, bc2, bc3 = st.columns(3)
    with bc1:
        if st.button("模仿回复", use_container_width=True):
            st.session_state.result_tab = "imitate"
            st.rerun()
    with bc2:
        if st.button("情感分析", use_container_width=True):
            st.session_state.result_tab = "emotion"
            st.rerun()
    with bc3:
        if st.button("气氛分析", use_container_width=True):
            st.session_state.result_tab = "atmosphere"
            st.rerun()


# ══════════════════════════════════════════════════════════════
# Full-width result display (outside column layout)
# ══════════════════════════════════════════════════════════════

tab = st.session_state.get("result_tab")

if tab is None:
    st.markdown("""
    <div class="empty-state">
        <p>↑ 选择分析类型</p>
    </div>
    """, unsafe_allow_html=True)

elif tab == "imitate":
    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.85rem;font-weight:500;color:var(--fg);'
        'letter-spacing:-0.01em;margin-bottom:0.6rem;">模仿回复</p>',
        unsafe_allow_html=True,
    )
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("分析中…"):
            data = _call_skill("imitate", _build_payload())
        if data:
            _, rcol, _ = st.columns([1, 6, 1])
            with rcol:
                st.markdown(
                    '<p style="font-size:0.65rem;font-weight:500;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;">对方可能会这样回复</p>',
                    unsafe_allow_html=True,
                )
                st.info(data.get("reply", "—"))
                fingerprint = data.get("speech_fingerprint", "")
                if fingerprint:
                    st.markdown(
                        '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                        'letter-spacing:0.06em;margin-top:0.5rem;">语气指纹</p>',
                        unsafe_allow_html=True,
                    )
                    st.caption(fingerprint)
                st.caption("AI 生成 · 仅供娱乐")

elif tab == "emotion":
    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.85rem;font-weight:500;color:var(--fg);'
        'letter-spacing:-0.01em;margin-bottom:0.6rem;">情感心理指数</p>',
        unsafe_allow_html=True,
    )
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("分析中…"):
            data = _call_skill("emotion_analyze", _build_payload())
        if data:
            _, col, _ = st.columns([1, 6, 1])
            with col:
                # ── 四个指数仪表盘（两列并排节省空间）──
                ic1, ic2 = st.columns(2)
                indices = [
                    ("真诚指数", data.get("sincerity_index", 0), data.get("sincerity_reasoning", "")),
                    ("回避指数", data.get("avoidance_index", 0), data.get("avoidance_reasoning", "")),
                    ("冷暴力指数", data.get("cold_violence_index", 0), data.get("cold_violence_reasoning", "")),
                    ("情绪稳定性", data.get("emotional_stability", 0), ""),
                ]

                for idx_col, (ic) in enumerate([ic1, ic2]):
                    with ic:
                        for i in range(idx_col * 2, min(idx_col * 2 + 2, len(indices))):
                            label, value, reasoning = indices[i]
                            if label in ("真诚指数", "情绪稳定性"):
                                if value >= 70: bar_color = "var(--green)"
                                elif value >= 40: bar_color = "var(--amber)"
                                else: bar_color = "var(--red)"
                            else:
                                if value <= 30: bar_color = "var(--green)"
                                elif value <= 60: bar_color = "var(--amber)"
                                else: bar_color = "var(--red)"

                            st.markdown(f"""
                            <div style="margin-bottom:0.8rem;">
                                <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:0.2rem;">
                                    <span style="font-size:0.78rem;color:var(--fg-soft);font-weight:450;">{label}</span>
                                    <span style="font-size:1.2rem;font-weight:500;color:{bar_color};">{value}</span>
                                </div>
                                <div style="height:4px;background:var(--border);border-radius:4px;overflow:hidden;">
                                    <div style="height:100%;width:{value}%;background:{bar_color};border-radius:4px;transition:width 0.3s;"></div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                            if reasoning:
                                st.caption(reasoning)

                st.markdown("---")

                # ── 主导情绪 + 情感趋势 ──
                ec1, ec2 = st.columns(2)
                with ec1:
                    st.markdown(
                        '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                        'letter-spacing:0.06em;">主导情绪</p>',
                        unsafe_allow_html=True,
                    )
                    emotion = data.get("dominant_emotion", "—")
                    st.markdown(f'<span class="tag" style="font-size:0.72rem;">{emotion}</span>', unsafe_allow_html=True)
                with ec2:
                    st.markdown(
                        '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                        'letter-spacing:0.06em;">情感趋势</p>',
                        unsafe_allow_html=True,
                    )
                    st.caption(data.get("emotion_trajectory", "—"))

elif tab == "atmosphere":
    st.markdown("---")
    st.markdown(
        '<p style="font-size:0.85rem;font-weight:500;color:var(--fg);'
        'letter-spacing:-0.01em;margin-bottom:0.6rem;">关系动力学</p>',
        unsafe_allow_html=True,
    )
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("分析中…"):
            data = _call_skill("analyze_atmosphere", _build_payload())
        if data:
            _, col, _ = st.columns([1, 6, 1])
            with col:
                # ── 掌控力分配 ──
                control = data.get("control_strength", {})
                st.markdown(
                    '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                    'letter-spacing:0.06em;margin-bottom:0.2rem;">掌控力分配</p>',
                    unsafe_allow_html=True,
                )
                target_key = next((k for k in control if k != "me" and k != "我"), "对方")
                me_key = next((k for k in control if k in ("me", "我")), "我")
                target_val = control.get(target_key, 50)
                me_val = control.get(me_key, 50)

                st.markdown(f"""
                <div style="display:flex;align-items:center;gap:0.8rem;margin-bottom:0.5rem;">
                    <span style="font-size:0.7rem;color:var(--fg-muted);min-width:2rem;">我</span>
                    <div style="flex:1;height:8px;background:var(--border);border-radius:4px;overflow:hidden;display:flex;">
                        <div style="height:100%;width:{me_val}%;background:var(--accent-dim);border-radius:4px 0 0 4px;"></div>
                        <div style="height:100%;width:{target_val}%;background:var(--red);border-radius:0 4px 4px 0;"></div>
                    </div>
                    <span style="font-size:0.7rem;color:var(--fg-muted);min-width:2rem;text-align:right;">对方</span>
                </div>
                <div style="display:flex;justify-content:space-between;margin-bottom:0.8rem;">
                    <span style="font-size:0.75rem;font-weight:500;color:var(--accent-dim);">{me_val}%</span>
                    <span style="font-size:0.75rem;font-weight:500;color:var(--red);">{target_val}%</span>
                </div>
                """, unsafe_allow_html=True)
                st.caption(data.get("control_analysis", ""))

                # ── 沟通姿态标签 ──
                posture = data.get("communication_posture", "—")
                st.markdown(
                    '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                    'letter-spacing:0.06em;margin-bottom:0.2rem;">沟通姿态</p>',
                    unsafe_allow_html=True,
                )
                st.markdown(f'<span class="tag" style="font-size:0.7rem;">{posture}</span>', unsafe_allow_html=True)

                st.markdown("---")

                # ── 关系进度条（使用4列并排）──
                progress = data.get("relation_progress", {})
                if progress:
                    st.markdown(
                        '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                        'letter-spacing:0.06em;margin-bottom:0.3rem;">关系进度条</p>',
                        unsafe_allow_html=True,
                    )
                    pcols = st.columns(4)
                    prog_items = [
                        ("确定性", progress.get("certainty", 0), "var(--green)"),
                        ("暧昧度", progress.get("ambiguity", 0), "var(--red)"),
                        ("亲近度", progress.get("closeness", 0), "var(--accent-dim)"),
                        ("可能性", progress.get("possibility", 0), "var(--amber)"),
                    ]
                    for pi, (label, val, color) in enumerate(prog_items):
                        with pcols[pi]:
                            st.markdown(f"""
                            <div style="text-align:center;">
                                <div style="font-size:2rem;font-weight:350;color:{color};line-height:1.2;">{val}</div>
                                <div style="height:3px;background:var(--border);border-radius:3px;overflow:hidden;margin:0.3rem 0;">
                                    <div style="height:100%;width:{val}%;background:{color};border-radius:3px;"></div>
                                </div>
                                <div style="font-size:0.65rem;color:var(--fg-muted);">{label}</div>
                            </div>
                            """, unsafe_allow_html=True)
                    st.caption(progress.get("progress_summary", ""))

                st.markdown("---")

                # ── 气氛总结 + 权力动态 ──
                st.info(data.get("atmosphere_summary", "—"))
                with st.expander("权力动态分析"):
                    st.write(data.get("power_dynamic", "—"))

                # ── 行动建议卡片（两列网格）──
                suggestions = data.get("actionable_suggestions", [])
                if suggestions:
                    st.markdown(
                        '<p style="font-size:0.62rem;color:var(--fg-muted);text-transform:uppercase;'
                        'letter-spacing:0.06em;margin:0.4rem 0 0.3rem;">行动建议</p>',
                        unsafe_allow_html=True,
                    )
                    cat_emoji = {"立即行动": "⚡", "长期策略": "🌱", "风险预警": "⚠️"}
                    for s in suggestions:
                        cat = s.get("category", "")
                        pri = s.get("priority", 1)
                        emoji = cat_emoji.get(cat, "→")
                        pri_dots = "●" * pri + "○" * (5 - pri)
                        st.markdown(f"""
                        <div style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;
                                    padding:0.6rem 0.8rem;margin-bottom:0.5rem;">
                            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.3rem;">
                                <span style="font-size:0.65rem;color:var(--fg-muted);">{emoji} {cat}</span>
                                <span style="font-size:0.58rem;color:var(--accent-dim);">{pri_dots}</span>
                            </div>
                            <p style="font-size:0.78rem;color:var(--fg-soft);margin:0 0 0.25rem 0;line-height:1.6;">
                                {s.get('suggestion', '')}
                            </p>
                            <p style="font-size:0.65rem;color:var(--fg-dim);margin:0;">
                                预期: {s.get('expected_effect', '')}
                            </p>
                        </div>
                        """, unsafe_allow_html=True)

# ── Reset ──
if tab is not None:
    st.markdown("---")
    _, bcol, _ = st.columns([2, 1, 2])
    with bcol:
        if st.button("清空结果", use_container_width=True):
            st.session_state.result_tab = None
            st.rerun()
