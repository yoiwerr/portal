# src/rag_function.py
import os
from dotenv import load_dotenv
from langchain_core.documents import Document
from typing import List
from src.schemas import ChatMessage

from langchain_community.embeddings import DashScopeEmbeddings
from langchain_postgres.vectorstores import PGVector
from sqlalchemy import create_engine, text

load_dotenv()
api_key = os.getenv("DASHSCOPE_API_KEY")
pgpass = os.getenv("PGSQLPASSWORD")

# ==========================================
# 1. 数据库与 Embedding 配置
# ==========================================
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
CONNECTION_STRING = os.getenv(
    "POSTGRES_URL",
    f"postgresql+psycopg2://postgres:{pgpass}@{DB_HOST}:{DB_PORT}/chatdemopg"
)

embeddings = DashScopeEmbeddings(
    model="text-embedding-v3",
    dashscope_api_key=api_key
)


# text-embedding-v3 固定输出 1024 维，无需每次启动调用 API
EMBEDDING_DIM = 1024


def _get_embedding_dim() -> int:
    """返回当前嵌入模型输出的向量维度。"""
    return EMBEDDING_DIM


def _get_stored_vector_dim() -> int | None:
    """查询 pgvector 表中已存储向量的维度，若无数据则返回 None。"""
    engine = None
    try:
        engine = create_engine(CONNECTION_STRING)
        with engine.connect() as conn:
            exists = conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'langchain_pg_embedding')"
            ))
            if not exists.fetchone()[0]:
                return None
            row = conn.execute(text(
                "SELECT vector_dims(embedding) FROM langchain_pg_embedding LIMIT 1"
            ))
            result = row.fetchone()
            if result:
                return result[0]
    except Exception:
        pass
    finally:
        if engine:
            engine.dispose()
    return None


def check_dimension_mismatch() -> bool:
    """检测向量维度是否匹配。返回 True 表示有不匹配（需要人工介入）。"""
    stored_dim = _get_stored_vector_dim()
    if stored_dim is None:
        return False
    current_dim = _get_embedding_dim()
    return stored_dim != current_dim


# 模块加载时检测维度不匹配，发现不一致则报错阻止启动
_dim_mismatch = check_dimension_mismatch()
if _dim_mismatch:
    stored = _get_stored_vector_dim()
    current = _get_embedding_dim()
    raise RuntimeError(
        f"\n{'='*60}\n"
        f"  向量维度不匹配，无法启动。\n"
        f"  表中维度: {stored}\n"
        f"  当前模型维度: {current}\n"
        f"\n"
        f"  请选择以下方式之一修复：\n"
        f"  1. (推荐) 调用清理API: DELETE /api/v1/clear_vector_store\n"
        f"     然后重新导入知识文件和聊天记录\n"
        f"  2. 手动在 PostgreSQL 中执行:\n"
        f"     DROP TABLE IF EXISTS langchain_pg_embedding CASCADE;\n"
        f"     DROP TABLE IF EXISTS langchain_pg_collection CASCADE;\n"
        f"{'='*60}"
    )

# 【永久库】：心理学资料、理论文献
knowledge_store = PGVector(
    embeddings=embeddings,
    collection_name="psychology_knowledge",
    connection=CONNECTION_STRING,
    use_jsonb=True
)

# 【历史库】：聊天记录（持久积累，不再清空）
chat_history_store = PGVector(
    embeddings=embeddings,
    collection_name="chat_history",
    connection=CONNECTION_STRING,
    use_jsonb=True
)


CONTEXT_WINDOW = 3  # 每条消息前后各附带 N 条作为上下文


def _build_chat_context(chats: List[ChatMessage], idx: int) -> str:
    """为第 idx 条消息构建带上下文窗口的内容。"""
    start = max(0, idx - CONTEXT_WINDOW)
    end = min(len(chats), idx + CONTEXT_WINDOW + 1)
    lines = []
    for i in range(start, end):
        c = chats[i]
        prefix = ">>> " if i == idx else "    "
        lines.append(f"{prefix}[{c.timestamp}] {c.sender}: {c.content}")
    return "\n".join(lines)


def save_chats_to_long_term_memory(recent_chats: List[ChatMessage], target_person: str) -> str:
    """
    将前端传入的聊天记录永久存入向量知识库，作为该人物的长期记忆。
    每条消息附带上下文窗口（前后各 CONTEXT_WINDOW 条），写入前去重。
    """
    if not recent_chats:
        return "没有接收到聊天记录。"

    # 写入前去重：检查内容完全相同的消息是否已存在
    existing_contents: set[str] = set()
    try:
        existing_results = chat_history_store.similarity_search(
            target_person, k=min(100, len(recent_chats) * 2),
            filter={"target_person": target_person, "type": "chat_history"}
        )
        for doc in existing_results:
            existing_contents.add(doc.page_content)
    except Exception:
        pass

    docs = []
    skipped = 0
    for i, chat in enumerate(recent_chats):
        content = _build_chat_context(recent_chats, i)

        if content in existing_contents:
            skipped += 1
            continue

        doc = Document(
            page_content=content,
            metadata={
                "target_person": target_person,
                "sender": chat.sender,
                "timestamp": chat.timestamp,
                "type": "chat_history"
            }
        )
        docs.append(doc)

    if not docs:
        return f"所有 {skipped} 条记录已存在，跳过写入。"

    try:
        chat_history_store.add_documents(docs)
        msg = f"成功将 {len(docs)} 条关于 {target_person} 的聊天记录存入长期记忆库"
        if skipped:
            msg += f"（已跳过 {skipped} 条重复）"
        return msg + "！"
    except Exception as e:
        print(f"写入向量库失败: {e}")
        return f"保存失败，数据库发生错误: {str(e)}"

def import_knowledge_file(file_name: str) -> str:
    """
    将 data/ 目录下的 txt 资料文件切块导入心理学知识库 (knowledge_store)。
    调用一次即可，重复调用同一文件会跳过。
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    file_path = os.path.join(os.path.dirname(__file__), "..", "data", file_name)
    file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        return f"文件不存在: {file_path}"

    try:
        existing = knowledge_store.similarity_search(" ", k=1, filter={"source": file_name})
        if existing:
            return f"文件 {file_name} 已导入过（检测到同名 source），跳过。"
    except Exception:
        pass

    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    if not text.strip():
        return f"文件 {file_name} 为空，跳过。"

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
    )

    chunks = text_splitter.split_text(text)
    docs = [
        Document(page_content=chunk, metadata={"source": file_name, "type": "reference_book"})
        for chunk in chunks
    ]

    try:
        knowledge_store.add_documents(docs)
        return f"成功将 {file_name} 导入知识库，共 {len(chunks)} 个文本块。"
    except Exception as e:
        return f"导入失败: {str(e)}"


def clear_vector_stores() -> str:
    """显式清理所有向量表（用于维度不匹配时手动重建）。"""
    from sqlalchemy import create_engine as _create_engine, text as _text
    engine = None
    try:
        engine = _create_engine(CONNECTION_STRING)
        with engine.connect() as conn:
            conn.execute(_text("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE"))
            conn.execute(_text("DROP TABLE IF EXISTS langchain_pg_collection CASCADE"))
            conn.commit()
        return "向量表已清除。请重新导入知识文件和聊天记录。"
    except Exception as e:
        return f"清除失败: {str(e)}"
    finally:
        if engine:
            engine.dispose()


def list_imported_files() -> list:
    """列出已导入知识库的资料文件名（去重）。"""
    try:
        results = knowledge_store.similarity_search(" ", k=100, filter={"type": "reference_book"})
        sources = list(set(doc.metadata.get("source", "unknown") for doc in results))
        return sources
    except Exception:
        return []