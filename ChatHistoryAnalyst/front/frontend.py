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
        max-width: 1280px;
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

    /* Info / success / warning overrides — keep them clean */
    .stAlert {
        border-radius: 6px !important;
        border: 1px solid var(--border) !important;
        background: var(--bg-card) !important;
        font-size: 0.75rem !important;
    }
    .stAlert [data-testid="stMarkdown"] p {
        color: var(--fg-soft) !important;
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
    "rag_stored": False,
    "rag_msg_count": 0,
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
    rag_ok = st.session_state.get("rag_stored", False)
    target = st.session_state.get("cfg_target", "对方")

    st.markdown(f"""
    <div class="status-row">
        <span class="status-label">消息</span>
        <span class="status-value" style="color:{'var(--green)' if chat_count > 0 else 'var(--fg-dim)'};">{chat_count}</span>
    </div>
    <div class="status-row">
        <span class="status-label">对象</span>
        <span class="status-value" style="color:var(--accent-dim);">{target}</span>
    </div>
    <div class="status-row" style="border-bottom:none;">
        <span class="status-label">向量库</span>
        <span class="status-value" style="color:{'var(--green)' if rag_ok else 'var(--fg-dim)'};">{'已存入' if rag_ok else '未存入'}</span>
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
        上传截图或文本，AI 解析情感、气氛与沟通模式
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
left, right = st.columns([5, 4], gap="medium")

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
            type=["txt", "json", "png", "jpg", "jpeg", "webp"],
            key="chat_file_uploader",
            label_visibility="collapsed",
        )
        st.caption("TXT · JSON · PNG · JPG · WebP（截图自动 OCR）")

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
                                "save_to_rag": str(st.session_state.get("cfg_save_rag", False)).lower(),
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
                            msg = st.session_state.upload_message
                            if "存入长期记忆库" in msg or "长期记忆" in msg:
                                st.session_state.rag_stored = True
                                st.session_state.rag_msg_count = len(st.session_state.parsed_chats)
                        else:
                            st.session_state.parsed_chats = []
                            st.session_state.upload_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                            st.session_state.upload_message = ""
                st.rerun()

        if st.session_state.upload_error:
            st.error(st.session_state.upload_error)
        elif st.session_state.upload_message and st.session_state.parsed_chats:
            st.success(st.session_state.upload_message)
            if st.session_state.rag_stored:
                st.success(
                    f"已存入向量库 · {st.session_state.rag_msg_count} 条关于 "
                    f"「{st.session_state.get('cfg_target', '对方')}」的聊天记录"
                )
            elif st.session_state.get("cfg_save_rag"):
                st.warning("向量库存储可能未生效，请检查后端日志")

    with manual_tab:
        manual_input = st.text_area(
            "按格式粘贴聊天记录",
            value=st.session_state.manual_input,
            height=110,
            placeholder="[lyzy 10:00]: 你今天怎么没理我？\n[小z 10:05]: 滚吧渣男",
            key="widget_manual_input",
            label_visibility="collapsed",
        )
        st.session_state.manual_input = manual_input
        st.caption("格式：`[昵称 时间]: 消息内容`，每行一条")

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
        with st.container(height=250):
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
    rag_ok_st = st.session_state.get("rag_stored", False)

    # ── Data bar ──
    if chat_count > 0:
        rag_text = "向量库已存入" if rag_ok_st else "未存入向量库"
        rag_color = "var(--green)" if rag_ok_st else "var(--fg-dim)"
        st.markdown(f"""
        <div class="data-bar">
            <span class="data-bar-count">{chat_count}</span>
            <span style="color:var(--fg-muted);">条消息已加载</span>
            <span style="margin-left:auto;color:{rag_color};font-size:0.68rem;">{rag_text}</span>
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
    if "cfg_save_rag" not in st.session_state:
        st.session_state.cfg_save_rag = False

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
    st.checkbox("存入长期记忆库", key="cfg_save_rag")

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

    # ── Result display ──────────────────────────
    st.markdown("---")

    tab = st.session_state.get("result_tab")

    if tab is None:
        st.markdown("""
        <div class="empty-state">
            <p>↑ 选择分析类型</p>
        </div>
        """, unsafe_allow_html=True)

    elif tab == "imitate":
        st.markdown(
            '<p style="font-size:0.75rem;font-weight:500;color:var(--fg);'
            'letter-spacing:-0.01em;margin-bottom:0.5rem;">模仿回复</p>',
            unsafe_allow_html=True,
        )
        chats = _get_chats()
        if not chats:
            st.warning("请先导入聊天记录")
        else:
            with st.spinner("分析中…"):
                data = _call_skill("imitate", _build_payload())
            if data:
                st.markdown(
                    '<p style="font-size:0.65rem;font-weight:500;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;">对方可能会这样回复</p>',
                    unsafe_allow_html=True,
                )
                st.info(data.get("reply", "—"))
                st.caption("AI 生成 · 仅供娱乐")

    elif tab == "emotion":
        st.markdown(
            '<p style="font-size:0.75rem;font-weight:500;color:var(--fg);'
            'letter-spacing:-0.01em;margin-bottom:0.5rem;">情感状态</p>',
            unsafe_allow_html=True,
        )
        chats = _get_chats()
        if not chats:
            st.warning("请先导入聊天记录")
        else:
            with st.spinner("分析中…"):
                data = _call_skill("emotion_analyze", _build_payload())
            if data:
                score = data.get("emotion_score", 0)
                if score >= 70:
                    score_color = "var(--green)"
                    emoji = "↑"
                elif score >= 40:
                    score_color = "var(--amber)"
                    emoji = "→"
                else:
                    score_color = "var(--red)"
                    emoji = "↓"

                m1, m2 = st.columns(2)
                with m1:
                    st.markdown(f"""
                    <div class="metric">
                        <div class="metric-value" style="color:{score_color};">{score}</div>
                        <div class="metric-label">情感指数 / 100</div>
                    </div>
                    """, unsafe_allow_html=True)
                with m2:
                    emotion = data.get('dominant_emotion', '—')
                    st.markdown(f"""
                    <div class="metric">
                        <div style="font-size:1.8rem;line-height:1;">{emoji}</div>
                        <div class="metric-label">主导情绪</div>
                        <span class="tag">{emotion}</span>
                    </div>
                    """, unsafe_allow_html=True)
                st.markdown(
                    '<p style="font-size:0.65rem;font-weight:500;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;margin:0.3rem 0 0.2rem;">分析依据</p>',
                    unsafe_allow_html=True,
                )
                st.caption(data.get("analysis_reasoning", "—"))

    elif tab == "atmosphere":
        st.markdown(
            '<p style="font-size:0.75rem;font-weight:500;color:var(--fg);'
            'letter-spacing:-0.01em;margin-bottom:0.5rem;">沟通气氛</p>',
            unsafe_allow_html=True,
        )
        chats = _get_chats()
        if not chats:
            st.warning("请先导入聊天记录")
        else:
            with st.spinner("分析中…"):
                data = _call_skill("analyze_atmosphere", _build_payload())
            if data:
                st.markdown(
                    '<p style="font-size:0.65rem;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;margin-bottom:0.2rem;">气氛总结</p>',
                    unsafe_allow_html=True,
                )
                st.info(data.get("atmosphere_summary", "—"))

                st.markdown(
                    '<p style="font-size:0.65rem;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;margin:0.5rem 0 0.2rem;">权力动态</p>',
                    unsafe_allow_html=True,
                )
                st.success(data.get("power_dynamic", "—"))

                st.markdown(
                    '<p style="font-size:0.65rem;color:var(--fg-muted);'
                    'text-transform:uppercase;letter-spacing:0.06em;margin:0.4rem 0 0.3rem;">行动建议</p>',
                    unsafe_allow_html=True,
                )
                suggestions = data.get("actionable_suggestions", [])
                if suggestions:
                    for i, s in enumerate(suggestions):
                        st.markdown(f"""
                        <div class="step">
                            <span class="step-num">{i + 1}</span>
                            <span>{s}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.write("—")

    # ── Reset ──
    if tab is not None:
        st.markdown("---")
        if st.button("清空结果", use_container_width=True):
            st.session_state.result_tab = None
            st.rerun()
