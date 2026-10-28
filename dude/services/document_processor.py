"""
文档处理器 — 来源感知的语义分割。

核心原则:
  1. 来源信息是不可分割的元数据 → 提取后复制到每个子 Chunk
  2. 正文是可分割的内容 → 只对正文做语义分割
  3. 每个 Chunk 有完整的 identity chain (document_id → parent_id → prev/next chunk)
  4. 多来源文档 → 按来源拆分成独立 Document 后再各自语义分割
  5. source_refs 精确到 Chunk 级别，不无差别挂载

架构:
  原始 .md 文件
    → SourceParser: 提取 source_title, source_url, repository, author, accessed_at, version_or_commit
    → SourceSplitter: 多来源文档按来源拆分
    → SemanticChunker: 对正文语义分割（不含来源描述）
    → ChunkBuilder: 复制来源元数据到每个 Chunk，建立 identity chain
"""

import hashlib
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# Source Metadata Model
# ============================================================

class SourceMetadata:
    """文档级来源元数据 — 不参与语义分割，直接复制到每个子 Chunk。"""

    __slots__ = (
        "source_title", "source_url", "source_type",
        "repository", "author", "accessed_at", "version_or_commit",
        "extra",
    )

    def __init__(
        self,
        source_title: str = "",
        source_url: str = "",
        source_type: str = "document",  # document | capability_card | best_practice | engineering_guide
        repository: str = "",
        author: str = "",
        accessed_at: str = "",
        version_or_commit: str = "",
        extra: dict = None,
    ):
        self.source_title = source_title
        self.source_url = source_url
        self.source_type = source_type
        self.repository = repository
        self.author = author
        self.accessed_at = accessed_at or datetime.now(timezone.utc).isoformat()[:10]
        self.version_or_commit = version_or_commit
        self.extra = extra or {}

    def to_dict(self) -> dict:
        return {
            "source_title": self.source_title,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "repository": self.repository,
            "author": self.author,
            "accessed_at": self.accessed_at,
            "version_or_commit": self.version_or_commit,
            "extra": self.extra,
        }

    @classmethod
    def from_frontmatter(cls, frontmatter: dict, fallback_file_name: str = "") -> "SourceMetadata":
        """从 YAML frontmatter 构建 SourceMetadata。"""
        mapping = {
            "source_title": ["source_title", "title", "name"],
            "source_url": ["source_url", "url", "link"],
            "source_type": ["source_type", "type"],
            "repository": ["repository", "repo"],
            "author": ["author", "creator"],
            "accessed_at": ["accessed_at", "accessed"],
            "version_or_commit": ["version_or_commit", "version", "commit"],
        }

        values = {}
        for field, keys in mapping.items():
            for key in keys:
                if key in frontmatter:
                    values[field] = frontmatter[key]
                    break

        if not values.get("source_title") and fallback_file_name:
            values["source_title"] = fallback_file_name.replace(".md", "").replace("_", " ")

        return cls(**values)


# ============================================================
# Chunk Identity
# ============================================================

class ChunkIdentity:
    """单个 Chunk 的身份链 — 召回时可通过这些信息恢复完整上下文。"""

    __slots__ = (
        "chunk_id", "document_id", "parent_id",
        "chunk_index", "previous_chunk_id", "next_chunk_id",
        "source_refs", "section_title",
    )

    def __init__(
        self,
        chunk_id: str = "",
        document_id: str = "",
        parent_id: str = "",
        chunk_index: int = 0,
        previous_chunk_id: str = "",
        next_chunk_id: str = "",
        source_refs: list[dict] = None,
        section_title: str = "",
    ):
        self.chunk_id = chunk_id
        self.document_id = document_id
        self.parent_id = parent_id
        self.chunk_index = chunk_index
        self.previous_chunk_id = previous_chunk_id
        self.next_chunk_id = next_chunk_id
        self.source_refs = source_refs or []
        self.section_title = section_title

    def to_dict(self) -> dict:
        return {
            k.lstrip("_"): v for k, v in self.__dict__.items()
        }

    @classmethod
    def build_chain(cls, chunks: list[str], document_id: str, source_refs: list[dict]) -> list["ChunkIdentity"]:
        """为一个文档的所有 chunk 建立 identity chain。"""
        identities = []
        for i, chunk_text in enumerate(chunks):
            chunk_id = cls._make_id(document_id, i)
            section_title = cls._extract_section_title(chunk_text)
            identities.append(cls(
                chunk_id=chunk_id,
                document_id=document_id,
                parent_id=document_id,  # 顶层 chunk 的 parent 即 document
                chunk_index=i,
                previous_chunk_id=cls._make_id(document_id, i - 1) if i > 0 else "",
                next_chunk_id=cls._make_id(document_id, i + 1) if i < len(chunks) - 1 else "",
                source_refs=source_refs,
                section_title=section_title,
            ))
        return identities

    @staticmethod
    def _make_id(document_id: str, chunk_index: int) -> str:
        raw = f"{document_id}:chunk:{chunk_index}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_section_title(text: str) -> str:
        """从 chunk 文本中提取第一个标题作为 section_title。"""
        match = re.search(r"^#{1,3}\s+(.+)", text, re.MULTILINE)
        return match.group(1).strip()[:120] if match else ""


# ============================================================
# Source Parser — 提取文档级元数据
# ============================================================

class SourceParser:
    """从 .md 文档中提取来源元数据。

    支持格式:
      - YAML frontmatter (--- ... --- )
      - HTML-style comments (<!-- source: ... -->)
      - Heuristic extraction for documents without explicit metadata
    """

    @staticmethod
    def parse(file_path: Path) -> tuple[SourceMetadata, list[dict], str]:
        """
        解析文档，返回 (source_meta, source_refs_list, body_only)。

        source_meta: 文档级来源元数据
        source_refs_list: 多来源时每个来源的引用信息（从各 section 提取）
        body_only: 剥离 frontmatter 和来源描述的纯正文

        多来源检测：
          如果正文包含 "## 来源1" / "## Source 1" 等标记，
          返回多个 source_refs（每个有 start_offset/end_offset 标注作用范围）。
        """
        raw = file_path.read_text(encoding="utf-8")
        source_meta, body_with_sources = SourceParser._parse_frontmatter(raw, file_path.name)

        # 检测是否多来源文档
        has_multi_sources = any(
            pattern in body_with_sources
            for pattern in ["## 来源", "## Source", "## source:", "## 参考资料"]
        )

        if has_multi_sources:
            source_refs, body_chunks_by_source = SourceParser._extract_multi_sources(body_with_sources)
            # 多来源：为每个来源生成独立的 document body
            # 返回列表 — 调用方应为每个 source 创建独立 Document
            body_only = body_with_sources  # 返回完整 body，SourceSplitter 会处理
            return source_meta, source_refs, body_only
        else:
            # 单来源：直接去掉 frontmatter 后的全文即正文
            body_only = SourceParser._strip_source_descriptions(body_with_sources)
            return source_meta, [], body_only

    @staticmethod
    def _parse_frontmatter(raw: str, fallback_name: str) -> tuple[SourceMetadata, str]:
        """提取 YAML frontmatter。返回 (meta, body_without_frontmatter)。"""
        if not raw.startswith("---"):
            return SourceMetadata(
                source_title=fallback_name.replace(".md", "").replace("_", " "),
                source_type="document",
            ), raw

        parts = raw.split("---", 2)
        if len(parts) < 3:
            return SourceMetadata(source_title=fallback_name), raw

        frontmatter_text = parts[1].strip()
        body = parts[2].strip()

        fm = {}
        for line in frontmatter_text.split("\n"):
            line = line.strip()
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")

            if value.startswith("[") and value.endswith("]"):
                # list
                items = [v.strip().strip("\"'").lstrip("- ") for v in value[1:-1].split("\n") if v.strip()]
                fm[key] = items
            elif value.startswith("|"):
                fm[key] = ""
            else:
                fm[key] = value

        # 也解析 markdown body 开头对来源的描述行
        # e.g. "> 来源: https://..."  "> Source: ..."
        body_lines = body.split("\n")
        body_start = 0
        for line in body_lines[:5]:
            stripped = line.strip().lstrip(">").strip()
            body_start += 1
            if stripped.startswith("来源:") or stripped.startswith("Source:"):
                url = stripped.partition(":")[2].strip()
                if url and "source_url" not in fm:
                    fm["source_url"] = url
            elif stripped.startswith("仓库:") or stripped.startswith("Repo:"):
                repo = stripped.partition(":")[2].strip()
                if repo and "repository" not in fm:
                    fm["repository"] = repo

        return SourceMetadata.from_frontmatter(fm, fallback_name), body

    @staticmethod
    def _extract_multi_sources(body: str) -> tuple[list[dict], list[str]]:
        """
        从多来源文档中提取各个来源信息。

        查找模式:
          ## 来源1: OpenAI GPT-4 Technical Report
          > URL: https://...
          > Accessed: 2026-07-01

        返回 (source_refs, source_bodies)。
        未匹配到结构化来源时，报告整个文档为一个 source_refs 条目。
        """
        # 按 "## 来源" 或 "## Source" 分割
        sections = re.split(r"\n(?=## (?:来源|Source|source:))", body)
        if len(sections) <= 1:
            # 尝试按 "### 来源" 分
            sections = re.split(r"\n(?=### (?:来源|Source))", body)

        if len(sections) <= 1:
            return [], [body]

        source_refs = []
        source_bodies = []

        for section in sections:
            if not section.strip():
                continue
            ref = {
                "source_title": "",
                "source_url": "",
                "author": "",
                "accessed_at": "",
            }

            # 从 section header 和内容中提取
            lines = section.strip().split("\n")
            header = lines[0] if lines else ""
            ref["source_title"] = re.sub(r"^#+\s*(?:来源|Source)\s*\d*[:：]?\s*", "", header).strip()

            for line in lines[1:8]:
                stripped = line.strip().lstrip(">").strip()
                for label, field in [("URL:", "source_url"), ("链接:", "source_url"),
                                      ("作者:", "author"), ("Author:", "author"),
                                      ("访问:", "accessed_at"), ("Accessed:", "accessed_at")]:
                    if stripped.startswith(label):
                        ref[field] = stripped.partition(label)[2].strip()

            source_refs.append(ref)

            # Body 去掉第一行 header 后的内容
            source_bodies.append("\n".join(lines[1:]).strip())

        return source_refs, source_bodies

    @staticmethod
    def _strip_source_descriptions(body: str) -> str:
        """去掉开头的来源描述行（如 "> 来源: https://..."）。"""
        lines = body.split("\n")
        keep_from = 0
        for i, line in enumerate(lines[:8]):
            stripped = line.strip()
            if stripped.startswith(">") and any(
                kw in stripped for kw in ["来源:", "Source:", "URL:", "链接:", "仓库:", "作者:"]
            ):
                continue
            if stripped.startswith(">") or stripped == "":
                keep_from = i
                continue
            keep_from = i
            break
        return "\n".join(lines[keep_from:]).strip()


# ============================================================
# Source Splitter — 按来源拆分成独立 Document
# ============================================================

class SourceSplitter:
    """多来源文档 → 拆分出多个独立 Document。

    每个 Document 携带:
      - document_id (UUID)
      - source_metadata (父级来源信息)
      - source_refs (本段特有引用)
      - body_text (属于此来源的正文)
    """

    @staticmethod
    def split(
        file_path: Path,
        source_meta: SourceMetadata,
        source_refs: list[dict],
        body: str,
    ) -> list[dict]:
        """
        按来源拆分为独立 Document 列表。

        单来源时返回一个 Document（source_refs 为空时用 source_meta）。
        多来源时每个 source_refs 生成一个独立 Document。
        工具知识卡片集合时按 <!-- TOOL CARD --> 拆分，每张卡片独立 Document。

        Returns:
            [{document_id, source_metadata, source_refs, body_text}, ...]
        """
        documents = []

        # ── 工具知识卡片集合检测 ──
        tool_cards = SourceSplitter._extract_tool_cards(body)
        if tool_cards:
            parent_meta = source_meta.to_dict()
            for i, card in enumerate(tool_cards):
                doc_id = SourceSplitter._make_document_id(str(file_path), i)
                # 卡片级元数据：继承父级 + 覆盖卡片特有字段
                card_meta = dict(parent_meta)
                card_meta["source_title"] = card["name"] or card_meta.get("source_title", file_path.stem)
                card_meta["source_type"] = "tool_card"
                card_meta["source_url"] = card.get("source_url") or card_meta.get("source_url", "")
                card_meta["repository"] = card.get("source_repository") or card_meta.get("repository", "")
                card_meta["extra"] = {
                    **card_meta.get("extra", {}),
                    "card_id": card.get("card_id", ""),
                    "category": card.get("category", ""),
                    "risk_level": card.get("risk_level", ""),
                    "documentation_url": card.get("documentation_url", ""),
                    "review_status": card.get("review_status", ""),
                }

                card_refs = [{
                    "source_title": card["name"],
                    "source_url": card.get("source_url", ""),
                    "chunk_range": "all",
                    "card_id": card.get("card_id", ""),
                }]

                documents.append({
                    "document_id": doc_id,
                    "source_metadata": card_meta,
                    "source_refs": card_refs,
                    "body_text": card["body"],
                })
            return documents

        if not source_refs:
            # 单来源
            doc_id = SourceSplitter._make_document_id(str(file_path), 0)
            documents.append({
                "document_id": doc_id,
                "source_metadata": source_meta.to_dict(),
                "source_refs": [],
                "body_text": body,
            })
        else:
            # 多来源 → 每个来源拆成独立 Document
            sections = re.split(r"\n(?=## (?:来源|Source|source:))", body)
            # sections[0] 可能是导言（不属于任何来源）→ 如果短则丢弃
            if sections and len(sections) > 1:
                sections = sections[1:]  # 跳过导言

            for i, section in enumerate(sections):
                ref = source_refs[i] if i < len(source_refs) else {"source_title": f"来源{i+1}"}
                doc_id = SourceSplitter._make_document_id(str(file_path), i)

                # 合并 parent meta + specific ref
                merged_meta = dict(source_meta.to_dict())
                merged_meta.update({k: v for k, v in ref.items() if v})

                # 提取此来源的正文（跳过 section header line）
                lines = section.strip().split("\n")
                header_skipped = "\n".join(
                    line for line in lines[1:]
                    if not (line.strip().startswith(">") and any(
                        kw in line for kw in ["URL:", "链接:", "作者:", "访问:", "Accessed:", "Author:", "Repo:", "仓库:"]
                    ))
                ).strip()

                documents.append({
                    "document_id": doc_id,
                    "source_metadata": merged_meta,
                    "source_refs": [{"source_title": ref.get("source_title", ""),
                                     "source_url": ref.get("source_url", ""),
                                     "chunk_range": "all"}],
                    "body_text": header_skipped or section.strip(),
                })

        return documents

    @staticmethod
    def _extract_tool_cards(body: str) -> list[dict]:
        """从工具知识卡片集合中提取每张卡片的 frontmatter + 正文。

        识别标记: <!-- TOOL CARD XX START --> ... <!-- TOOL CARD XX END -->
        每张卡片内的 --- YAML frontmatter --- 提取为卡片级元数据。

        Returns:
            [{name, category, source_url, documentation_url, source_repository,
              risk_level, card_id, review_status, body}, ...]
            未检测到工具卡片时返回空列表。
        """
        if "<!-- TOOL CARD" not in body:
            return []

        pattern = r"<!-- TOOL CARD \d+ START -->(.*?)<!-- TOOL CARD \d+ END -->"
        matches = re.findall(pattern, body, re.DOTALL)

        if not matches:
            return []

        cards = []
        for card_body in matches:
            card_body = card_body.strip()
            if not card_body:
                continue

            fm = {}
            text = card_body
            # 提取卡片级 YAML frontmatter（每张卡片以 --- 开头）
            if card_body.startswith("---"):
                parts = card_body.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_text = parts[1].strip()
                    text = parts[2].strip()
                    for line in frontmatter_text.split("\n"):
                        line = line.strip()
                        if ":" not in line:
                            continue
                        key, _, value = line.partition(":")
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if value and value not in ("", "null"):
                            fm[key] = value

            name = fm.get("name", "")
            if not name:
                # 兜底: 从正文的第一个 # 标题提取名称
                title_match = re.match(r"^#\s+(.+)", text, re.MULTILINE)
                if title_match:
                    name = title_match.group(1).strip()[:120]

            cards.append({
                "name": name,
                "category": fm.get("category", ""),
                "source_url": fm.get("source_url", ""),
                "documentation_url": fm.get("documentation_url", ""),
                "source_repository": fm.get("source_repository", ""),
                "risk_level": fm.get("risk_level", ""),
                "card_id": fm.get("card_id", ""),
                "review_status": fm.get("review_status", ""),
                "body": text,
            })

        return cards

    @staticmethod
    def _make_document_id(file_path: str, index: int) -> str:
        raw = f"{file_path}:doc:{index}:{uuid.uuid4().hex[:8]}"
        return hashlib.md5(raw.encode()).hexdigest()[:12]


# ============================================================
# SemanticChunker — 正文语义分割（增强版）
# ============================================================

class SemanticChunker:
    """对正文做语义分割 — 不依赖正文中的来源描述维持引用关系。

    来源元数据在 ChunkBuilder 中统一复制到每个子 Chunk。
    """

    def __init__(
        self,
        embedding_fn,
        threshold: float = 0.5,
        min_chars: int = 200,
        max_chars: int = 800,
    ):
        self.embed = embedding_fn
        self.threshold = threshold
        self.min_chars = min_chars
        self.max_chars = max_chars

    def chunk(self, text: str) -> list[dict]:
        """
        语义分割。返回 [{text, section_title, entity_names}, ...]。
        """
        sections = self._split_by_headers(text)
        all_chunks = []
        for section in sections:
            # 提取 section title
            section_title = ""
            header_match = re.match(r"^#{1,4}\s+(.+)", section)
            content = section
            if header_match:
                section_title = header_match.group(1).strip()[:120]
                content = section[header_match.end():].strip()

            if len(content) <= self.min_chars:
                if content.strip():
                    all_chunks.append({
                        "text": section.strip(),
                        "section_title": section_title,
                        "entity_names": self._extract_entities(section),
                    })
                continue

            sentences = self._split_sentences(content)
            if len(sentences) <= 1:
                all_chunks.append({
                    "text": section.strip(),
                    "section_title": section_title,
                    "entity_names": self._extract_entities(section),
                })
                continue

            try:
                embeddings = self.embed(sentences)
            except Exception:
                chunks = self._fallback_chunk(content, section_title)
                all_chunks.extend(chunks)
                continue

            breakpoints = self._find_breakpoints(sentences, embeddings)
            chunks = self._split_at_breakpoints(sentences, breakpoints, section_title)
            all_chunks.extend(chunks)

        return all_chunks

    def _split_by_headers(self, text: str) -> list[str]:
        parts = re.split(r"\n(?=## )", text)
        return [p.strip() for p in parts if p.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        raw = re.split(r"(?<=[。！？.!?\n])\s*", text)
        return [s.strip() for s in raw if s.strip() and len(s.strip()) >= 5]

    def _find_breakpoints(self, sentences: list[str], embeddings: list[list[float]]) -> list[int]:
        breakpoints = []
        for i in range(len(sentences) - 1):
            sim = self._cosine_similarity(embeddings[i], embeddings[i + 1])
            if sim < self.threshold:
                breakpoints.append(i + 1)
        return breakpoints

    def _split_at_breakpoints(
        self, sentences: list[str], breakpoints: list[int], section_title: str
    ) -> list[dict]:
        chunks = []
        start = 0
        for bp in breakpoints + [len(sentences)]:
            segment = sentences[start:bp]
            segment_text = " ".join(segment)

            if len(segment_text) < self.min_chars and bp < len(sentences):
                continue

            if len(segment_text) > self.max_chars:
                sub_texts = self._force_split(segment, self.max_chars)
                chunks.extend([{
                    "text": t, "section_title": section_title,
                    "entity_names": self._extract_entities(t),
                } for t in sub_texts])
            else:
                if segment_text.strip():
                    chunks.append({
                        "text": segment_text.strip(),
                        "section_title": section_title,
                        "entity_names": self._extract_entities(segment_text),
                    })
            start = bp
        return chunks

    def _force_split(self, sentences: list[str], max_chars: int) -> list[str]:
        chunks = []
        current = ""
        for s in sentences:
            if len(current) + len(s) <= max_chars:
                current += " " + s if current else s
            else:
                if current.strip():
                    chunks.append(current.strip())
                current = s
        if current.strip():
            chunks.append(current.strip())
        return chunks

    def _fallback_chunk(self, text: str, section_title: str = "") -> list[dict]:
        sentences = self._split_sentences(text)
        texts = self._force_split(sentences, self.max_chars)
        return [{"text": t, "section_title": section_title, "entity_names": self._extract_entities(t)} for t in texts]

    def _extract_entities(self, text: str) -> list[str]:
        """提取技术实体名称 — 用于构建稠密检索文本。"""
        patterns = [
            r'\b[A-Z][a-z]+(?:\s?[A-Z][a-z]+)*\b',
            r'\b[a-z]+(?:-[a-z]+)+\b',
            r'\b[A-Z]{2,}\b',
            r'\b[a-z]+(?:\.[a-z]+)+\b',
            r'[一-鿿]{2,8}',
        ]
        entities = set()
        for p in patterns:
            found = re.findall(p, text)
            entities.update(f for f in found if len(f) >= 2)
        # 过滤太通用的词
        stop = {"the", "and", "for", "with", "that", "this", "from", "have", "been", "was", "are",
                "可以", "这个", "那个", "什么", "怎么", "一个", "不是", "我们", "他们", "就是", "还是"}
        return list(entities - stop)[:15]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        a_arr, b_arr = np.array(a), np.array(b)
        denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
        return float(np.dot(a_arr, b_arr) / denom) if denom > 0 else 0.0


# ============================================================
# ChunkBuilder — 为每个 Chunk 装配完整 Identity Chain + 复制来源元数据
# ============================================================

class ChunkBuilder:
    """将语义分块结果装配为完整的可索引 Chunk。

    每个 Chunk 包含:
      - 全文 (用于 embedding)
      - 稠密检索文本: source_title + entity_names + section_title + body
      - 稀疏检索文本: repository + url + author + proper nouns
      - 来源元数据（从 parent Document 复制）
      - Identity Chain: document_id/chunk_id/parent_id/prev_id/next_id/chunk_index
      - source_refs (精确到本 Chunk)
    """

    @staticmethod
    def build(
        document: dict,         # {document_id, source_metadata, source_refs, body_text}
        chunks: list[dict],     # [{text, section_title, entity_names}, ...]
    ) -> list[dict]:
        """
        装配所有 Chunk。每个 Chunk 独立可召回，不依赖相邻 Chunk 维持来源引用。

        Returns:
            [{chunk_id, document_id, parent_id, chunk_index,
              previous_chunk_id, next_chunk_id, source_refs,
              source_metadata,  ← 从 document 复制
              search_text_dense, search_text_sparse,
              body_text, section_title, entity_names, content_hash}, ...]
        """
        doc_id = document["document_id"]
        source_meta = document["source_metadata"]
        source_refs = document.get("source_refs", [])

        identities = ChunkIdentity.build_chain(
            [c["text"] for c in chunks], doc_id, source_refs
        )

        result = []
        for i, (chunk_data, identity) in enumerate(zip(chunks, identities)):
            body = chunk_data["text"]
            section_title = chunk_data.get("section_title", identity.section_title)
            entity_names = chunk_data.get("entity_names", [])

            # 稠密检索文本
            extra = source_meta.get("extra", {})
            category = extra.get("category", source_meta.get("category", "")) if isinstance(extra, dict) else ""
            search_dense = ChunkBuilder._build_dense_search_text(
                source_title=source_meta.get("source_title", ""),
                category=category,
                entity_names=entity_names,
                section_title=section_title,
                body=body,
            )

            # 稀疏检索文本
            search_sparse = ChunkBuilder._build_sparse_search_text(
                repository=source_meta.get("repository", ""),
                url=source_meta.get("source_url", ""),
                author=source_meta.get("author", ""),
                entity_names=entity_names,
                category=category,
            )

            result.append({
                "chunk_id": identity.chunk_id,
                "document_id": identity.document_id,
                "parent_id": identity.parent_id,
                "chunk_index": identity.chunk_index,
                "previous_chunk_id": identity.previous_chunk_id,
                "next_chunk_id": identity.next_chunk_id,
                "source_refs": source_refs,
                "source_metadata": source_meta,
                "search_text_dense": search_dense,
                "search_text_sparse": search_sparse,
                "body_text": body,
                "section_title": section_title,
                "entity_names": entity_names,
                "content_hash": hashlib.md5(body.encode()).hexdigest(),
            })

        return result

    @staticmethod
    def _build_dense_search_text(
        source_title: str,
        entity_names: list[str],
        section_title: str,
        body: str,
        category: str = "",
    ) -> str:
        """构建稠密检索文本: source_title + category + entity_names + section_title + body。"""
        parts = []
        if source_title:
            parts.append(source_title)
        if category:
            parts.append(category)
        if entity_names:
            parts.append(" ".join(entity_names[:10]))
        if section_title:
            parts.append(section_title)
        parts.append(body)
        return " | ".join(parts)

    @staticmethod
    def _build_sparse_search_text(
        repository: str,
        url: str,
        author: str,
        entity_names: list[str],
        category: str = "",
    ) -> str:
        """构建稀疏索引文本: repository + url + author + category + proper nouns。"""
        parts = []
        if repository:
            parts.append(repository)
        if url:
            parts.append(url)
        if author:
            parts.append(author)
        if category:
            parts.append(category)
        if entity_names:
            parts.append(" ".join(entity_names[:8]))
        return " ".join(parts) if parts else ""


# ============================================================
# Knowledge Graph Builder — Source → Document → Chunk → Claim
# ============================================================

class KnowledgeGraphBuilder:
    """建立 Source → Document → Chunk → Claim 证据关系。

    PG 表:
      knowledge_sources  — 来源节点
      knowledge_documents — 文档节点 (FK → sources)
      knowledge_chunks    — Chunk 节点 (FK → documents, FK → sources)
      knowledge_claims    — Claim 节点 (FK → chunks)

    非 PGVector collection — 这四张表由 vector_store 的 ensure_tables 创建。
    """

    @staticmethod
    def build_edges(
        document: dict,
        built_chunks: list[dict],
    ) -> dict:
        """
        为一次文档索引生成所有 KG 边。

        Returns:
            {source_node, document_nodes, chunk_edges, claim_nodes}
        """
        source_meta = document["source_metadata"]
        doc_id = document["document_id"]

        source_node = {
            "source_id": KnowledgeGraphBuilder._make_source_id(source_meta),
            "source_title": source_meta.get("source_title", ""),
            "source_url": source_meta.get("source_url", ""),
            "source_type": source_meta.get("source_type", "document"),
            "repository": source_meta.get("repository", ""),
            "author": source_meta.get("author", ""),
            "accessed_at": source_meta.get("accessed_at", ""),
            "version_or_commit": source_meta.get("version_or_commit", ""),
        }

        doc_node = {
            "document_id": doc_id,
            "source_id": source_node["source_id"],
            "source_title": source_meta.get("source_title", ""),
            "chunk_count": len(built_chunks),
        }

        chunk_edges = [
            {
                "chunk_id": c["chunk_id"],
                "document_id": doc_id,
                "source_id": source_node["source_id"],
                "chunk_index": c["chunk_index"],
                "previous_chunk_id": c["previous_chunk_id"],
                "next_chunk_id": c["next_chunk_id"],
            }
            for c in built_chunks
        ]

        return {
            "source_node": source_node,
            "document_node": doc_node,
            "chunk_edges": chunk_edges,
        }

    @staticmethod
    def _make_source_id(source_meta: dict) -> str:
        raw = source_meta.get("source_title", "") + source_meta.get("source_url", "")
        if not raw.strip():
            raw = uuid.uuid4().hex[:12]
        return f"src_{hashlib.md5(raw.encode()).hexdigest()[:12]}"
