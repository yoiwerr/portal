import streamlit as st
import requests
import re
import os

BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1")

# ── 页面配置 ──────────────────────────────────
st.set_page_config(
    page_title="ChatLab — 聊天记录分析引擎",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── 全局样式：象牙白底 + 粉色辅色 ──────────
st.markdown("""
<style>
    /* 全局背景 — 象牙白 */
    .stApp { background: #FFF8F0; }

    /* 主区域顶部间距 */
    .block-container { padding-top: 1rem; }

    /* Streamlit 原生按钮 — 粉色 */
    .stButton > button {
        background: #e91e63 !important;
        color: #ffffff !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: background 0.2s !important;
    }
    .stButton > button:hover {
        background: #c2185b !important;
        color: #ffffff !important;
    }

    /* 卡片 */
    .card {
        border: 1px solid #f8d7e4;
        border-radius: 14px;
        padding: 1.2rem;
        margin-bottom: 0.8rem;
        background: #FFF0F5;
    }

    /* 大数字 */
    .big-number {
        font-size: 2.2rem;
        font-weight: 700;
    }

    /* 标签 */
    .tag {
        display: inline-block;
        padding: 0.18rem 0.7rem;
        border-radius: 99px;
        font-size: 0.72rem;
        font-weight: 500;
        background: #fce4ec;
        color: #c2185b;
        margin-right: 0.3rem;
    }

    /* section 标题 */
    .section-title {
        font-size: 0.8rem;
        font-weight: 600;
        color: #c2185b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.5rem;
    }

    /* 输入框聚焦 */
    input:focus, textarea:focus {
        border-color: #e91e63 !important;
        box-shadow: 0 0 0 1px #e91e63 !important;
    }
</style>
""", unsafe_allow_html=True)

# ── 会话状态初始化 ──────────────────────────────
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
# 侧边栏 — 仅保留品牌 + 状态，紧凑
# ═══════════════════════════════════════════════════
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/chat.png", width=36)
    st.markdown(
        '<p style="font-size:0.9rem;font-weight:700;margin:0;">ChatLab</p>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── 数据状态卡片 ──
    chat_count = len(st.session_state.get("parsed_chats", []))
    rag_ok = st.session_state.get("rag_stored", False)
    target = st.session_state.get("cfg_target", "对方")

    status_items = [
        ("📊 已加载消息", f"{chat_count} 条", "#10b981" if chat_count > 0 else "#9ca3af"),
        ("🎯 分析对象", target, "#7c3aed"),
        ("🧠 向量库", "✅ 已存入" if rag_ok else "○ 未存入", "#10b981" if rag_ok else "#9ca3af"),
    ]
    for label, val, color in status_items:
        st.markdown(
            f"""
            <div style="display:flex;justify-content:space-between;align-items:center;
                        padding:0.35rem 0;font-size:0.72rem;
                        border-bottom:1px solid #f3f4f6;">
                <span style="color:#6b7280;">{label}</span>
                <span style="color:{color};font-weight:600;">{val}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.caption("v0.1 · 数据仅本地存储")


# ═══════════════════════════════════════════════════
# 主区域
# ═══════════════════════════════════════════════════

# ── 紧凑 Hero ──
st.markdown("""
<div style="margin-bottom:0.2rem;">
    <h3 style="margin-bottom:0.1rem;">聊天记录深度分析</h3>
    <p style="color:#9ca3af;font-size:0.82rem;">
        上传聊天截图或文本，AI 自动解析并分析情感、气氛与沟通姿态
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# ── 双栏布局：左（上传+预览）│ 右（配置+操作按钮）──
left, right = st.columns([5.5, 3.5], gap="medium")

with left:
    st.markdown('<p class="section-title">📤 导入聊天记录</p>', unsafe_allow_html=True)

    upload_tab, manual_tab = st.tabs(["📎 文件上传", "✏️ 手动输入"])

    with upload_tab:
        uploaded_file = st.file_uploader(
            "拖拽文件到此处，或点击选择",
            type=["txt", "json", "png", "jpg", "jpeg", "webp"],
            key="chat_file_uploader",
            label_visibility="collapsed",
        )
        st.caption("支持 TXT · JSON · PNG · JPG · WebP（截图自动 OCR）")

        if uploaded_file is not None:
            file_key = f"{uploaded_file.name}_{uploaded_file.size}"
            if st.session_state.last_file_key != file_key:
                st.session_state.last_file_key = file_key
                with st.spinner("正在解析文件…"):
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
                            # 检测向量库是否存入成功
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
                    f"✅ 已存入向量库 · {st.session_state.rag_msg_count} 条关于 "
                    f"「{st.session_state.get('cfg_target', '对方')}」的聊天记录"
                )
            elif st.session_state.get("cfg_save_rag"):
                st.warning("⚠️ 向量库存储可能未生效，请检查后端日志")

    with manual_tab:
        manual_input = st.text_area(
            "按格式粘贴聊天记录",
            value=st.session_state.manual_input,
            height=120,
            placeholder="[lyzy 10:00]: 你今天怎么没理我？\n[小z 10:05]: 滚吧渣男",
            key="widget_manual_input",
            label_visibility="collapsed",
        )
        st.session_state.manual_input = manual_input
        st.caption("格式：`[昵称 时间]: 消息内容`，每行一条")

    # ── 消息预览 ──
    st.markdown('<p class="section-title" style="margin-top:0.8rem;">📋 消息预览</p>', unsafe_allow_html=True)

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
        with st.container(height=260):
            for i, chat in enumerate(chats):
                is_me = "我" in chat.get("sender", "")
                align = "flex-end" if is_me else "flex-start"
                bubble_bg = "#fce4ec" if is_me else "#f3e8ff"
                bubble_border = "#f8bbd0" if is_me else "#d8b4fe"
                text_align = "right" if is_me else "left"
                msg_text = chat.get("content", "")
                st.markdown(
                    f"""
                    <div style="display:flex;justify-content:{align};margin-bottom:0.35rem;">
                        <div style="max-width:80%;padding:0.35rem 0.7rem;
                                    border-radius:10px;background:{bubble_bg};
                                    border:1px solid {bubble_border};
                                    text-align:{text_align};">
                            <span style="font-weight:600;font-size:0.65rem;color:#9ca3af;">
                                {chat.get('sender','?')} · {chat.get('timestamp','')}
                            </span>
                            <br>
                            <span style="font-size:0.8rem;color:#1f2937;">{msg_text}</span>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    else:
        st.info("上传文件或手动输入后，解析结果会出现在这里", icon="👆")


with right:
    # ── 数据状态速览 ──
    chat_count = len(st.session_state.get("parsed_chats", []))
    rag_ok = st.session_state.get("rag_stored", False)

    if chat_count > 0:
        rag_badge = (
            '<span style="color:#10b981;">✅ 向量库已存入</span>'
            if rag_ok
            else '<span style="color:#f59e0b;">⚠️ 未存入向量库</span>'
        )
        st.markdown(
            f"""
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;
                        padding:0.6rem 0.9rem;margin-bottom:0.8rem;font-size:0.73rem;">
                📊 已加载 <b>{chat_count}</b> 条消息 &nbsp;|&nbsp; {rag_badge}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ── 分析配置（独立卡片）──
    st.markdown('<p class="section-title">⚙️ 分析配置</p>', unsafe_allow_html=True)

    if "cfg_target" not in st.session_state:
        st.session_state.cfg_target = "对方"
    if "cfg_bg" not in st.session_state:
        st.session_state.cfg_bg = ""
    if "cfg_save_rag" not in st.session_state:
        st.session_state.cfg_save_rag = False

    st.text_input(
        "目标对象名称",
        key="cfg_target",
        placeholder="输入对方昵称",
        label_visibility="collapsed",
    )
    st.text_area(
        "补充背景（选填）",
        key="cfg_bg",
        placeholder="选填：性格特点、关系背景…",
        height=65,
        label_visibility="collapsed",
    )
    st.checkbox("存入长期记忆库", key="cfg_save_rag")

    st.markdown("---")

    # ── 三个功能按键（右侧主操作区）──
    st.markdown('<p class="section-title">🔍 开始分析</p>', unsafe_allow_html=True)

    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        if st.button("🎭 模仿对方回复", use_container_width=True, help="模仿对方的语气和风格生成回复"):
            st.session_state.result_tab = "imitate"
            st.rerun()
    with btn_col2:
        if st.button("❤️ 情感状态分析", use_container_width=True, help="分析对方的历史情感变化趋势"):
            st.session_state.result_tab = "emotion"
            st.rerun()
    with btn_col3:
        if st.button("🔮 沟通气氛分析", use_container_width=True, help="分析对话的权力动态和沟通氛围"):
            st.session_state.result_tab = "atmosphere"
            st.rerun()

    # ── 快捷提示 ──
    st.caption("点击上方按钮开始对应分析，结果将显示在下方")


# ── 分隔线 ──
st.markdown("---")


# ═══════════════════════════════════════════════════
# 结果展示区
# ═══════════════════════════════════════════════════

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
        st.error("无法连接后端，请确认服务已启动：`uvicorn src.main:app`")
        return None
    if resp.status_code != 200:
        st.error(f"请求失败 HTTP {resp.status_code}")
        st.code(resp.text[:500])
        return None
    return resp.json()


tab = st.session_state.get("result_tab")

if tab is None:
    st.markdown(
        """
        <div style="text-align:center;padding:1.5rem 0;color:#9ca3af;">
            <p style="font-size:0.85rem;">👈 在右侧上传聊天记录并选择分析类型，结果将在此处展示</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

elif tab == "imitate":
    st.subheader("🎭 模仿对方回复")
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("Agent 正在模仿语气…"):
            data = _call_skill("imitate", _build_payload())
        if data:
            st.markdown("#### 对方可能会这样回复")
            st.info(data.get("reply", "—"))
            st.caption("以上回复由 AI 生成，仅供娱乐参考")

elif tab == "emotion":
    st.subheader("❤️ 历史情感状态分析")
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("Agent 正在提取情感特征…"):
            data = _call_skill("emotion_analyze", _build_payload())
        if data:
            score = data.get("emotion_score", 0)
            if score >= 70:
                color = "#10b981"
                emoji = "😊"
            elif score >= 40:
                color = "#f59e0b"
                emoji = "😐"
            else:
                color = "#e91e63"
                emoji = "😞"

            m1, m2, m3 = st.columns([1, 1, 2])
            with m1:
                st.markdown(
                    f"""
                    <div style="text-align:center;padding:1rem;">
                        <div style="font-size:0.72rem;color:#9ca3af;">情感指数</div>
                        <div class="big-number" style="color:{color};">{score}<span style="font-size:0.85rem;">/100</span></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with m2:
                st.markdown(
                    f"""
                    <div style="text-align:center;padding:1rem;">
                        <div style="font-size:0.72rem;color:#9ca3af;">主导情绪</div>
                        <div style="font-size:1.4rem;margin-top:0.5rem;">{emoji}</div>
                        <span class="tag">{data.get('dominant_emotion', '—')}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with m3:
                st.markdown("**分析依据**")
                st.caption(data.get("analysis_reasoning", "—"))

elif tab == "atmosphere":
    st.subheader("🔮 沟通气氛与权力动态分析")
    chats = _get_chats()
    if not chats:
        st.warning("请先导入聊天记录")
    else:
        with st.spinner("Agent 正在深度解析…"):
            data = _call_skill("analyze_atmosphere", _build_payload())
        if data:
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 气氛总结")
                st.info(data.get("atmosphere_summary", "—"))
            with col_b:
                st.markdown("#### 权力动态")
                st.success(data.get("power_dynamic", "—"))

            st.markdown("#### 行动建议")
            suggestions = data.get("actionable_suggestions", [])
            if suggestions:
                for i, s in enumerate(suggestions):
                    st.markdown(
                        f"""
                        <div style="display:flex;align-items:baseline;margin-bottom:0.5rem;">
                            <span style="
                                display:inline-flex;align-items:center;justify-content:center;
                                width:22px;height:22px;border-radius:50%;
                                background:#7c3aed;color:white;font-size:0.7rem;font-weight:600;
                                margin-right:0.5rem;flex-shrink:0;
                            ">{i + 1}</span>
                            <span style="font-size:0.85rem;">{s}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.write("暂无建议。")

# ── 重置按钮 ──
if tab is not None:
    st.markdown("---")
    if st.button("🔄 清空结果，重新开始", use_container_width=False):
        st.session_state.result_tab = None
        st.rerun()
