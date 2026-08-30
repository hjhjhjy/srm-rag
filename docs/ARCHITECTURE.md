# 架构设计说明

## 1. 总体分层

| 层 | 技术 | 职责 |
|---|---|---|
| 接入层 | React + Vite + TypeScript | 流式对话、引用卡、反馈、明暗主题、iframe 桥接、运营后台 |
| API 层 | FastAPI | 路由、鉴权（RBAC/API Key）、限流、CORS、结构化日志、指标暴露 |
| 编排层 | `ChatService` | 意图路由 → 检索 → 提示词拼装 → LLM 流式生成 → 引用 → 持久化 |
| 检索层 | 混合检索（向量 + BM25 + RRF） | 召回候选；意图/流程感知加权 |
| 重排层 | LLM 重排（默认） / BGE 交叉编码器 / 恒等 | 候选精排，提升 Top-N 相关性 |
| 生成层 | DeepSeek（OpenAI 兼容，流式） | 真·大模型答案；无 Key 降级检索增强直答 |
| 知识层 | docx 解析 → 分块 → 向量化 → numpy/Chroma 向量库 | 蓝图知识库构建与存取 |
| 持久层 | SQLite（SQLAlchemy） | 会话、消息、反馈、用户；零外部依赖、易部署 |

## 2. RAG 数据流

```
用户问题
  │
  ▼
意图路由 (router.classify) ── 闲聊/转人工 ──▶ 直答
  │ 检索类
  ▼
查询改写 (HyDE, 仅 LLM 可用且问题简短)  ── 提升口语化问题的召回
  ▼
混合检索: vector(cos) + BM25 + RRF 融合
  · 附录类型意图加权（form/message/warning/report/interface）
  · 流程感知附录提权、子流程加权
  ▼
LLM 重排 (top-12 → 选相关编号)  →  top-8
  ▼
提示词拼装 (context + question + 多轮 history)
  ▼
LLM 流式生成 (DeepSeek) ── 失败 ──▶ 检索增强直答（关键词补摘）
  ▼
引用溯源 (flow_code/flow_name/snippet) + confidence
  ▼
持久化 (会话/消息) + 指标埋点 (CHAT_*/RETRIEVAL_*)
```

## 3. 安全设计

- **认证**：`Authorization: Bearer <JWT>`（供应商/管理员）或 `X-API-Key`（服务级，供 SRM 后端 / iframe 调用）。
- **授权**：`require_roles("admin")` 保护 `/api/kb/rebuild`、`/api/admin/*`；`/api/kb/rebuild` 额外校验 `X-KB-Key`。
- **限流**：slowapi 按客户端 IP，`rate_limit_per_min`（默认 60）全局默认限制。
- **CORS**：`cors_origins` 显式域名；仅当非通配才允许凭证，杜绝 `*` + credentials 冲突。
- **iframe 桥接**：父域白名单 `__IFRAME_ALLOWED_ORIGINS__`（生产务必限定 SRM 域名），仅接受可信域消息。
- **密钥**：`JWT_SECRET` 缺失时告警并使用开发密钥；生产须配置强随机值。

## 4. 可观测性

- `structlog` 结构化日志 + 每请求 `X-Request-ID`。
- `/api/metrics`（Prometheus）：`srm_http_requests_total`、`srm_chat_requests_total{sync|stream}`、`srm_chat_chars_total`、`srm_retrieval_hits/miss_total`、`srm_feedback_positive/negative_total`、`srm_chat_latency_seconds`。

## 5. 离线降级策略（无 HF / 无 Key）

| 组件 | 在线 | 离线降级 |
|---|---|---|
| 嵌入 | BGE（`sentence-transformers`） | sklearn TF-IDF（jieba 分词）/ 纯 numpy |
| 向量库 | Chroma | 内置 numpy 向量库 |
| 重排 | BGE 交叉编码器 | **LLM 重排**（优先）/ 恒等 |
| 生成 | DeepSeek 真·大模型 | 检索增强直答（关键词补摘） |

> 离线环境下仍提供完整 RAG 闭环，仅精度/自然度略降，**不影响演示与可用性**。

## 6. 关键设计取舍

- **自研而非 fork MaxKB**：保留独有的 SRM 8 大模块 / 25 子流程 / 附录体系业务资产，代码 100% 自有；架构范式借鉴 MaxKB（企业 RAG + iframe 嵌入）、LibreChat（鉴权/可观测）、Dify/RAGFlow（引用溯源 + 重排）。
- **SQLite 而非 PG+Redis**：降低部署复杂度，单一容器即可跑通；如需要可平滑替换为 PG。
- **jieba 分词嵌入**：解决中文无空格导致 TF-IDF 整段匹配失效的问题，显著提升子串召回。
