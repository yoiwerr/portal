# RAG 后续演进路线

## 短期（下一个迭代周期）

### HyDE (假设文档嵌入)

用户 query 先让 LLM 生成一个"假设的理想答案"，用假设答案的 embedding 去检索，而非直接使用用户原始 query。这对于短 query（如"她生气了吗"）的召回率提升尤为显著。

```
用户 query → LLM 生成假设答案 → embedding(假设答案) → 向量检索
```

### Query 重写

将用户简短、口语化的 query 自动扩展为更具体、更适合检索的查询语句。例如：
- "她生气了吗" → "目标人物在对话中表现出愤怒、不满或冷淡情绪的历史记录"
- "他什么意思" → "目标人物在对话中使用暗示、双关或模糊表达的上下文"

### 检索后 Rerank

当前 `qwen3-rerank` 模型（cross-encoder）正是为此设计：对 `similarity_search` 返回的 top-K 结果进行二次精排，大幅提升检索精度。

```
粗排(embedding) top-20 → 精排(reranker) top-5 → LLM
```

### MMR 多样性

对检索结果做 Maximal Marginal Relevance，惩罚与已选中结果过于相似的文档，保证返回结果的多样性。避免因 chunk_overlap 导致的重复信息占据上下文窗口。

### Metadata-driven 分库检索

不同 skill 自动选择不同的 collection 和过滤策略：
- `imitate` → 优先 `chat_history`，检索特定 sender 的发言风格
- `emotion` → `chat_history` + `psychology_knowledge`，找情感相关理论
- `atmosphere` → `chat_history` + `psychology_knowledge`，找权力动态理论

---

## 中期（架构升级）

### 多级检索

先检索粗粒度 chunk（段落级，定位到相关区域），再检索细粒度 chunk（句子级，精确定位到具体信息），两级结果组合后喂给 LLM。

### 时间衰减加权

聊天历史检索时引入时间衰减因子：越近的消息权重越高。对于模仿和气氛分析尤为重要（最近的关系动态比半年前更有参考价值）。

### 检索质量监控

记录每次检索的关键指标：
- 命中数、平均相似度分数
- LLM 是否实际引用了检索结果
- 用户对分析结果的满意度

建立检索质量 dashboard，及时发现 embedding 模型退化或知识库污染。

### 增量更新

当前只有 insert，没有 update/delete。增加：
- 删除指定 target_person 的所有聊天历史
- 更新知识库文件（删除旧 chunks + 重新导入）
- 按时间范围清理过期聊天记录

### Streaming + Citation

前端展示分析结果时，附带"参考了哪几条历史记录"的可追溯引用。用户点击引用可以查看原文，增强可信度和可解释性。

---

## 长期（生产级）

### GraphRAG

将聊天记录构建为知识图谱（人物 — 消息 — 话题），结合图遍历 + 向量检索，捕捉跨时间的对话关系和话题演化。

### 多模态 RAG

截图直接以 vision embedding 存入向量库，跳过 OCR 损失环节。检索时同时匹配文本语义和视觉布局特征。

### 本地模型

用本地 embedding（如 BGE-M3）+ 本地 LLM（如 Qwen3 本地部署）替代 DashScope，实现完全离线、零延迟的 RAG 链路。
