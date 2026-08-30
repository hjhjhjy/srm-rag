# 青山利康 SRM 供应商智能问答系统（RAG）

> 面向**供应商**的企业级**检索增强生成（RAG）问答系统**，产品名称「智能问答助手」，嵌入 SRM 系统，帮助供应商自助使用系统。
> 基于《SRM 业务蓝图 V5.0》的 RAG 管线，答案带蓝图流程码（**QS_SRM_\***）出处引用。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-blue.svg)](.github/workflows/ci.yml)
[![Stack](https://img.shields.io/badge/Stack-FastAPI%20%2B%20React-9cf.svg)]()

---

## ✨ 核心特性（企业级）

- **真·大模型问答**：接入 DeepSeek（OpenAI 兼容），答案由 LLM 生成并标注蓝图出处；未配置 Key 时自动降级为检索增强直答，保证可演示。
- **混合检索 + 精排（RAG 主流架构）**：稠密向量（**BGE 本地模型 / OpenAI 兼容 Embedding API**）语义召回 + **BM25** 关键词召回 + **RRF** 融合；意图/流程感知加权；**bge-reranker-v2-m3 交叉编码器精排**。向量库默认 **pgvector（PostgreSQL 向量扩展）**，本地开发可切 numpy / chroma。
- **引用溯源**：每个答案标注 `QS_SRM_*` 流程码与来源片段，可点击查看。
- **安全与可观测**：JWT（供应商 / 管理员 **RBAC**）+ 服务级 API Key；按 IP **限流**；CORS 显式可信源；`structlog` 结构化日志 + 请求 ID；`/api/metrics` Prometheus 指标。
- **专业前端**：React + Vite + TS，SSE 流式、会话持久化、Markdown 风格答案、引用卡、点赞/点踩反馈、明暗主题、**iframe postMessage 桥接**（父域白名单校验）。
- **运营后台**：管理员可查看会话 / 消息 / 反馈 / 知识库 / 检索命中统计。
- **工程外壳**：`pyproject.toml`（ruff/black/mypy）、pytest + Vitest 测试、GitHub Actions CI、Docker + Compose 一键部署、MIT 开源。

## 🏗️ 架构

```
┌──────────────┐    iframe(postMessage)    ┌──────────────────────────────┐
│  SRM 系统    │ ───────────────────────▶  │  前端 (React+Vite+TS)         │
│ (父页面)     │ ◀── ready/resize/theme ── │  流式 · 引用卡 · 反馈 · 主题   │
└──────────────┘                          └──────────────┬───────────────┘
                                                         │ /api  (CORS/鉴权/限流)
                                                         ▼
                              ┌────────────────────────────────────────────┐
                              │  后端 (FastAPI)                              │
                              │  · 鉴权 RBAC + API Key  · 限流  · 结构化日志 │
                              │  · /api/metrics (Prometheus)                 │
                              │  ChatService: 意图路由→检索→LLM→引用→持久化  │
                              └───┬───────────┬────────────┬────────────┬────┘
                                  │           │            │            │
                          ┌───────▼──┐  ┌─────▼─────┐ ┌────▼─────────┐ ┌──▼────────┐
                          │ 检索    │  │ LLM       │ │ 精排        │ │ 知识库    │
                          │ BGE稠密 │  │ DeepSeek  │ │ bge-reranker│ │ docx→分块 │
                          │ +BM25   │  │ (流式)    │ │ 交叉编码器 │ │ →pgvector │
                          │ +RRF    │  │           │ │            │ │          │
                          └──────────┘  └───────────┘ └────────────┘ └──────────┘
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 📌 项目定位：RAG 问答系统（而非 Agent）

本项目的核心能力是**检索增强生成（RAG）**：用户提问 → 从《业务蓝图》知识库检索相关片段 → DeepSeek 生成**带出处引用**的答案。
它**不调用任何业务系统接口、不做多步自主规划**，因此严格定位为「RAG 问答系统」；产品侧名称「智能问答助手」沿用即可。

- 若面试被问「这是 Agent 吗」：坦诚说明——核心是 RAG、目前为只读问答；若要升级为 Agent，会加入工具调用（查订单/提交反馈等）与多步闭环。
- 关于「Agent vs RAG」的更完整说明，见 [docs/RESUME_CN.md](docs/RESUME_CN.md)。

## 🚀 本地运行

### 后端
```bash
cd backend
pip install -r <见 pyproject.toml dependencies>   # 或自建虚拟环境
cp ../.env.example ../.env                        # 按需填写 DEEPSEEK_API_KEY 等
python -m knowledge.build_kb                      # 首次构建知识库（解析蓝图 docx）
uvicorn app.main:app --host 0.0.0.0 --port 8000   # 启动
# 文档: http://localhost:8000/docs
```

### 前端
```bash
cd frontend
npm install
npm run dev        # 开发: http://localhost:5173 (代理 /api → :8000)
npm run build      # 产出 dist/
```

> 开发演示默认服务密钥 `srm_dev_demo_key`（见 `.env.example`），**生产务必替换为强随机值**。

## 🐳 Docker 部署
```bash
# 在 srm-maxkb/ 目录
docker compose -f deploy/docker-compose.yml up -d --build
# 首次进入后端容器构建知识库:
docker compose -f deploy/docker-compose.yml exec backend python -m knowledge.build_kb
# 访问: http://localhost:8080
```

## 🔌 嵌入 SRM 系统
零代码 iframe 嵌入，详见 [docs/embed-guide.md](docs/embed-guide.md)：
```html
<iframe src="https://your-host/" width="420" height="720"
        style="border:0;border-radius:12px" allow="clipboard-write"></iframe>
```
父页可通过 `postMessage` 下发 `theme` / `auth`（JWT）并与子页 `ready` / `resize` 握手。

## 📊 评测
- 后端 `tests/`：pytest 冒烟（健康 / 鉴权拦截 / 带密钥问答 / 管理员统计）。
- 前端 `src/**/*.test.ts`：Vitest（SSE 解析等纯函数）。
- CI：lint + 测试 + 构建；配置 `DEEPSEEK_API_KEY` 后启用 LLM 评测门禁。

## 📁 目录结构
```
srm-maxkb/
├── backend/      FastAPI 后端（RAG 核心 / 鉴权 / 可观测 / 管理后台）
├── frontend/     React 前端（流式对话 / 引用 / 反馈 / iframe 桥接 / 运营后台）
├── deploy/       Dockerfile / nginx / docker-compose
├── docs/         ARCHITECTURE.md / embed-guide.md
├── showcase/     简历展示站（静态，可托管）
├── .github/      CI 工作流
└── README.md
```

## 📝 许可证
[MIT](LICENSE)
