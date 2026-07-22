# 项目改造规划：从「网页自动化测试 Agent」到「智能网页内容抓取 Agent」

> 文档版本：v1.0（2026-07-05）
> 状态：规划中
> 定位：服务于 10 人左右数据分析团队的内部工具，无高并发需求；同时作为简历中 AI 应用 / Agent 开发经历的支撑项目（非重点项目，控制投入）。

---

## 1. 改造目标

### 1.1 新产品定义

**输入**：一个 URL + 一段自然语言描述（说明想要抓取页面中的什么内容，例如"提取这个页面上所有商品的名称、价格和评分"）。

**输出**：结构化数据（JSON 表格），前端可视化展示并支持导出 CSV / Excel。

**核心流程**（Agent 自主完成）：

1. 抓取并渲染页面（复用现有 Playwright 能力）；
2. 理解用户的抓取意图，将自然语言转成结构化的"抓取字段清单"（schema）；
3. 分析页面 DOM，**自主决策抓取策略**（生成 CSS/XPath 选择器 vs. LLM 直接从正文抽取）；
4. 执行抓取，**自检结果质量，不合格则反思并重试**（reflection loop）；
5. 返回结构化结果 + 执行过程日志。

### 1.2 与旧项目的对应关系

旧项目"生成测试代码并执行、统计 case 通过数"的骨架与新需求高度同构，改造是**流水线语义的替换**而非推倒重来：

| 旧流程（autotest） | 新流程（scraper） |
|---|---|
| fetch_dom 抓取页面 | fetch_page（保留，加固） |
| structure_dom 结构化 DOM | structure_dom（保留，优化压缩策略） |
| case_analysis 分析测试用例可测性 | plan_extraction 解析抓取意图 → 字段 schema，判断可抓性 |
| generate_code 生成测试代码 | generate_extractor 生成选择器 / 抽取方案 |
| check_results 执行代码统计通过率 | execute_and_validate 执行抓取 + 质量校验 + 自纠错 |
| 前端展示 pass/fail 汇总 | 前端展示结构化数据表格 + 抓取覆盖率 |

---

## 2. 现状评估

### 2.1 可复用的资产

- **LangGraph 状态机骨架**（`backend/app/agents/autotest_agent.py`）：节点划分、条件边、统一错误处理节点（handle_error）、execution_log 机制，整体设计合理，直接沿用。
- **DOMService**（Playwright 渲染 + BeautifulSoup 结构化）：抓取项目的核心底座，保留并加固。
- **多 LLM Provider 工厂**（`llm_service/`：selector + config + 各 provider 实现）：企业级项目的加分设计，保留。
- **NDJSON 流式响应的前后端约定**：思路正确，迁移到 FastAPI 后改为原生 SSE/StreamingResponse。
- **Pydantic 模型定义习惯**（`models/schemas.py`）：保留，改造字段语义。

### 2.2 现有代码问题清单（改造中一并修复）

| # | 问题 | 位置 | 说明 |
|---|---|---|---|
| 1 | 异步调用缺 `await` | `autotest_agent.py:90` | `extract_structure` 是 async 函数但同步调用，实际返回 coroutine，流程必然出错 |
| 2 | 参数不匹配 | `autotest_agent.py:66-70` vs `dom_service.py:12` | agent 传了 `timeout` 参数，`get_page_html` 签名里没有，运行即 TypeError |
| 3 | `@staticmethod` 却带 `self` | `dom_service.py:72-73` | `summarize_dom` 装饰器与签名矛盾 |
| 4 | State 字段定义与使用不一致 | `schemas.py:49-54` | `AnalysisState` 定义了 `analysis_type`/`custom_prompt`，agent 实际使用 `case_prompt`（TypedDict 不校验，静默漏过） |
| 5 | 用 raw_html 冒充 structured_dom | `autotest_agent.py:107` | 结构化结果没真正用上（代码里已有 TODO） |
| 6 | Flask 下手动 new event loop | `controller/url_test.py:62-63` | 同步框架跑异步 agent 的补丁写法，是迁移 FastAPI 的直接理由 |
| 7 | Playwright 浏览器实例泄漏 | `dom_service.py` | 只 launch 不 close，无生命周期管理 |
| 8 | 任意执行 LLM 生成的代码 | `code_execution_service.py` | 安全隐患；新方案中整体移除该路径（见 3.3） |
| 9 | 硬编码 `SECRET_KEY='dev'`、CORS 写死 | `app/__init__.py` | 配置未外置 |
| 10 | 无依赖清单 | backend 目录 | 没有 requirements.txt / pyproject.toml，环境不可复现 |
| 11 | 无任何测试、无 CI | 全局 | 企业级规范化的主要补课项 |

---

## 3. 技术选型

### 3.1 Web 框架：**FastAPI**（替换 Flask）

决策依据（与本项目强相关，不是泛泛的框架偏好）：

1. **整条链路已经是 async**：Playwright async API、LangGraph `ainvoke`/`astream_events`、各 LLM SDK 的 async 客户端。Flask 下被迫在 generator 里手动 `asyncio.new_event_loop()`（现状问题 #6），FastAPI 原生 async 路由直接消除这层胶水。
2. **Pydantic 深度集成**：项目已大量使用 Pydantic 模型，FastAPI 的请求校验、响应模型、自动 OpenAPI 文档可零成本复用它们。自动生成的 `/docs` 交互式文档对"给数据分析团队用的内部工具"价值很高。
3. **流式输出**：LangGraph 的 `astream_events` 配合 FastAPI `StreamingResponse`/SSE 是社区标准组合，逐节点推送 agent 执行进度的代码量最小。
4. 并发需求低不构成留在 Flask 的理由——选 FastAPI 的动机是异步生态契合度，不是性能。

### 3.2 后端技术栈（确定项）

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python ≥ 3.12 | 沿用 |
| Agent 编排 | LangGraph | 沿用，升级到当前稳定版 |
| LLM 接入 | langchain + 角色化模型工厂（默认阿里云 DashScope / Qwen3） | 见 3.4 |
| Web 框架 | FastAPI + uvicorn | 替换 Flask |
| 页面抓取 | Playwright（动态页）+ httpx（静态页快速路径） | DOMService 拆分升级 |
| HTML 解析 | BeautifulSoup / lxml | 沿用 |
| 数据校验 | Pydantic v2 + pydantic-settings | 配置外置 |
| 持久化 | SQLite + SQLAlchemy 2.0 | 存任务历史与结果；团队规模下不引入独立数据库服务 |
| 导出 | pandas / openpyxl | CSV、Excel 导出 |
| 依赖管理 | uv + pyproject.toml | 锁定依赖，环境可复现 |

前端维持 React + antd，不做大改（非简历重点），仅把"测试结果面板"替换为"数据表格 + 导出按钮 + agent 执行步骤时间线"。

#### 关于「团队已有数据库，为何还额外起一个 SQLite」

这是企业实践中的合理做法，关键在于区分两类数据：

- **应用运行时元数据**（本项目的 SQLite 所存）：任务记录、执行日志、抓取结果快照、策略选择过程。只有本应用读写，生命周期跟随应用。
- **业务分析数据**（团队既有数据库所存）：团队要分析的主题数据、数仓、指标。由 BI / 分析脚本消费，生命周期跟随业务。

Scraper 需要的是前者——它是「应用自管状态」，与被分析的业务数据无关。让一个应用把自己的任务队列 / 执行日志写进团队的分析型数仓，反而会污染分析库、耦合应用与数仓的生命周期、并踩到对方的权限与 schema 规范。「应用自带一个嵌入式轻量库存自身状态」是成熟工具的通行模式（Airflow metadata db、Superset 元数据库等），且 SQLite 无独立进程、不占 DBA 精力，不构成额外运维负担。

**唯一该复用团队数据库的情形**：抓取的**结果数据**本身要并入团队分析流程（与数仓其他表 join、被看板消费）。为此把结果输出设计为**可插拔 sink**：默认落本地 SQLite + 支持 CSV/Excel 导出；预留一个可选的「写入外部数据库」出口（配置连接串即可），而应用自身的任务 / 日志始终留在本地 SQLite。这样既守住「应用自管状态」，又给「结果并入团队数据资产」留了口子，两者不耦死。

### 3.3 移除项

- `code_execution_service` + `subprocess_code_execute`（任意代码执行路径）：新架构下抓取由**受控的执行器**完成——LLM 只产出**声明式的抓取方案**（选择器列表 / 字段映射 JSON），由固定代码解释执行，不再让 LLM 生成可执行 Python 再 subprocess 跑。这既消除安全隐患，也让结果可校验、可重放，是简历上值得强调的设计决策（"约束 LLM 输出为声明式 DSL 而非任意代码"）。
- Selenium/Appium 相关依赖与文档。

### 3.4 LLM 接入：DashScope + 角色化 Qwen 模型

- **接口**：阿里云 DashScope 的 **OpenAI 兼容端点**，用 `langchain-openai` 的 `ChatOpenAI` 指向 `base_url` 接入，避免绑定专有 SDK，未来切换其他 OpenAI 兼容服务成本最低。
- **角色化模型**：流水线按任务性质分派不同模型——
  - *通用推理*（`plan_extraction` 意图解析、`llm_extract` 直抽）→ Qwen3 通用指令模型；
  - *代码任务*（`gen_selectors` 生成 CSS 选择器，本质是编程）→ Qwen 的 **code 专用模型**（qwen3-coder 系列）。
- **双档位**（同一套代码，`.env` 切换）：*逻辑测试档*用小模型（跑通流水线、省成本），*性能测试档*用大模型（评估 agent 实际抽取质量）。
- **型号选择规则**：优先 `qwen3-*`，同代不可用时按版本号递增回退（`qwen3.5-*` → 更高）。具体 model ID 以 DashScope 控制台为准，全部经 `.env` 覆盖，不写死在代码里。

---

## 4. 新架构设计

### 4.1 LangGraph 工作流

```
                    ┌─────────────┐
                    │ fetch_page  │  httpx 快速路径 → 失败/内容不足 → Playwright 渲染
                    └──────┬──────┘
                           ▼
                    ┌─────────────┐
                    │structure_dom│  清洗、去脚本、压缩为带定位信息的 DOM 摘要
                    └──────┬──────┘
                           ▼
                    ┌──────────────┐
                    │plan_extraction│  LLM：自然语言 → 字段 schema + 可抓性判断
                    └──────┬───────┘   （不可抓字段给出原因，对应旧 can_test）
                           ▼
                 ┌───────────────────┐
                 │ choose_strategy   │  条件边（agent 决策点）：
                 └───┬───────────┬───┘  规整列表页 → selector 策略
                     ▼           ▼      非规整内容 → llm_extract 策略
            ┌────────────┐ ┌────────────┐
            │gen_selectors│ │llm_extract │
            └──────┬──────┘ └─────┬──────┘
                   ▼              │
            ┌────────────┐        │
            │  execute   │        │
            └──────┬─────┘        │
                   ▼              ▼
                 ┌───────────────────┐
                 │  validate_result  │  规则校验（非空率、字段完整度、类型一致性）
                 └───┬───────────┬───┘  + LLM 抽样质检
              不合格 │           │ 合格
        （≤N 次重试）▼           ▼
              回到 choose_strategy   ┌──────────────┐
              携带失败反馈（反思）    │format_output │ → END
                                     └──────────────┘
```

核心 agentic 特性（简历叙述的支撑点）：

1. **策略自主决策**：`choose_strategy` 条件边由 LLM 依据 DOM 特征选择抓取路径；
2. **反思自纠错循环**：`validate_result` 不合格时，把失败样本和原因写回 state，重新规划（最多 N 次，防死循环）——旧项目没有回环，这是架构上的实质升级；
3. **双策略互为降级**：selector 策略失败自动降级到 LLM 直抽，成本与鲁棒性权衡显式化。

### 4.2 目录结构（目标形态）

```
backend/
├── pyproject.toml              # uv 管理，锁定依赖
├── .env.example
├── Dockerfile
├── app/
│   ├── main.py                 # FastAPI 入口（替代 run.py + create_app）
│   ├── core/
│   │   ├── config.py           # pydantic-settings，全部配置外置
│   │   ├── logging.py          # structlog / logging 配置，带 request_id
│   │   └── exceptions.py       # 业务异常层级 + 全局 exception handler
│   ├── api/
│   │   └── v1/
│   │       ├── scrape.py       # POST /api/v1/scrape（SSE 流式）
│   │       └── tasks.py        # GET 历史任务 / 结果导出
│   ├── agents/
│   │   ├── scraper_agent.py    # LangGraph 图定义（由 autotest_agent 改造）
│   │   ├── state.py            # ScrapeState（TypedDict + reducer）
│   │   └── nodes/              # 每个节点一个模块，便于单测
│   ├── services/
│   │   ├── fetch_service.py    # 由 dom_service 拆出：httpx + Playwright，含生命周期管理
│   │   ├── dom_service.py      # 纯解析：结构化、压缩、选择器执行
│   │   ├── extraction/
│   │   │   ├── planner.py      # 意图 → schema（由 case_analysis_service 改造）
│   │   │   ├── selector_gen.py # 选择器生成（由 code_generation_service 改造）
│   │   │   ├── llm_extractor.py# LLM 直抽策略
│   │   │   └── validator.py    # 结果质量校验
│   │   ├── llm/                # 角色化 chat-model 工厂（取代旧 llm_service）
│   │   └── sinks/              # 可插拔外部结果 sink
│   ├── models/
│   │   ├── schemas.py          # API 请求/响应模型
│   │   └── orm.py              # SQLAlchemy：ScrapeTask / ScrapeResult
│   └── repository/
│       └── task_repo.py        # 持久化访问层
└── tests/
    ├── unit/                   # 节点级：mock LLM，用固定 HTML fixture
    ├── integration/            # 图级：本地静态测试页端到端
    └── fixtures/pages/         # 若干本地 HTML 样例页
```

### 4.3 关键接口设计

```
POST /api/v1/scrape            # 发起抓取，SSE 流式返回节点级进度事件 + 最终结果
GET  /api/v1/tasks             # 任务历史列表（分页）
GET  /api/v1/tasks/{id}        # 任务详情（含执行日志、策略选择记录）
GET  /api/v1/tasks/{id}/export?format=csv|xlsx
GET  /healthz                  # 健康检查
```

SSE 事件类型建议：`started` / `node_completed`（含节点名、耗时、摘要）/ `retrying`（含反思原因）/ `completed` / `error`。前端时间线组件直接消费。

---

## 5. 企业级规范化清单

按投入产出比排序；★ 为简历叙述中值得点名的项。

### 5.1 必做（P0–P2 内完成）

1. **依赖与环境**：pyproject.toml + uv lock；`.env.example`；README 一键启动说明。
2. **配置管理** ★：pydantic-settings 统一读取环境变量（LLM key、CORS origins、超时、重试次数、SQLite 路径），消灭硬编码。
3. **结构化日志**：JSON 格式日志 + 每请求 request_id 贯穿 agent 全链路；LLM 调用记录 token 用量。
4. **统一错误处理**：业务异常层级（FetchError / PlanningError / ExtractionError…），FastAPI 全局 handler 输出统一错误体；沿用现有 error_code 设计。
5. **安全加固** ★：
   - SSRF 防护：URL 校验，拒绝内网 IP / 非 http(s) 协议（内部工具也要防误用）；
   - 移除任意代码执行路径（见 3.3）；
   - robots.txt 尊重开关 + 请求间隔限速（合规抓取，数据团队场景必要）。
6. **测试与 CI** ★：
   - 单测：每个 graph 节点独立测试，LLM 用 mock/录制响应，HTML 用本地 fixture；
   - 集成测试：对 `tests/fixtures/pages/` 的静态页跑完整图；
   - GitHub Actions：ruff + mypy + pytest；
   - 目标：核心 services 覆盖率 ≥ 70%（够写进简历，不过度投入）。
7. **代码质量**：ruff（lint + format）、mypy（services 层严格）、pre-commit。

### 5.2 选做（加分项，视时间）

8. ~~**容器化**~~ ✅ 已完成：backend Dockerfile（基于 `mcr.microsoft.com/playwright/python`）+ docker-compose（SQLite 挂命名卷）。前端开发期用 `npm start`，未做前端镜像。
9. **可观测性** ★：接入 LangSmith（或 Langfuse 自托管）trace agent 执行。*部分完成*：自建的 execution_log 持久化已落地，每次运行的 token 用量也已记录并在前端展示；外部 trace 平台未接入。
10. ~~**结果缓存**~~ ✅ **已完成，但实现形态与原计划不同**：缓存的不是"抓取结果"，而是**选择器方案**（`selector_cache` 表）。键为 (host, 归一化 prompt, 字段集)，而非原计划的 URL + schema —— 按 host 而非完整 URL 建键，使同站兄弟页面可共享方案。维护策略是**结果驱动**而非 TTL：通过校验才写入，事后失败则失效，让过期选择器自愈。这比 TTL 更贴合抓取场景（页面改版是事件驱动的，不是按时间到期的）。
11. **批量模式**：一个 schema 应用到同构 URL 列表（数据团队高频需求：selector 策略天然可复用，只需首个页面走 LLM，后续纯执行——这是双策略设计的直接收益，值得实现并写进简历）。**注**：选择器缓存（第 10 项）已把地基打好——同站同请求的后续页面本就复用缓存方案、零 LLM 调用，批量模式剩下的主要是"接受 URL 列表 + 并发调度 + 汇总结果"这层编排。

---

## 6. 实施计划

| 阶段 | 内容 | 预估投入 | 交付判定 |
|---|---|---|---|
| **P0 骨架迁移** | 新目录结构；Flask → FastAPI；配置外置；日志/异常框架；修复现状问题 #1–#7、#9、#10；补 pyproject | 1–2 天 | `/healthz` 可用，旧 fetch+structure 链路在 FastAPI 下跑通 |
| **P1 核心抓取图** | plan_extraction / gen_selectors / llm_extract / execute 四节点；受控执行器；单 URL 端到端出结构化 JSON | 2–3 天 | 对 2–3 个真实页面（新闻列表、商品列表、详情页）抓取成功 |
| **P2 Agent 能力** | choose_strategy 决策边；validate_result + 反思重试回环；SSE 逐节点推送 | 1–2 天 | 构造一个 selector 必失败的页面，验证自动降级与重试日志 |
| **P3 持久化与前端** | SQLAlchemy 任务/结果表；历史与导出 API；前端改为数据表格 + 执行时间线 + 导出 | 1–2 天 | 全流程 UI 演示可录屏 |
| **P4 质量与交付** | 测试补齐、CI、（可选）Docker、README 重写 + 架构图 | 1–2 天 | CI 绿灯；克隆仓库按 README 可 10 分钟内跑起 |
| P5 选做 | ~~缓存~~（已完成，见 5.2 第 10 项）；批量模式、LangSmith 仍待做 | 弹性 | — |

总计约 **6–11 天**有效投入，符合"非重点项目、控制规模"的定位。P0–P2 完成即可支撑简历叙述，P3–P4 决定演示与开源观感。

---

## 7. 简历叙述建议（改造完成后）

可支撑的表述要点（均有对应实现，避免空话）：

> ⚠️ 以下每条都已核对过对应实现，**不要添加未实现的表述**。历史上本节曾写"支持 OpenAI/Claude/Gemini/Ollama 热切换""限速合规""尊重 robots.txt"，但 legacy 多 provider 工厂已在 P4 删除、限速与 robots.txt 从未实现——已修正。面试被追问细节时，不实表述的代价远高于少写一条。

- 基于 **LangGraph** 设计带条件路由与反思回环的网页信息抽取 Agent：自然语言意图 → 字段 schema → 双策略（选择器生成 / LLM 直抽）自主决策 → 结果质量校验驱动的自纠错重试与策略降级；
- 将 LLM 输出**约束为声明式抓取方案**由受控执行器执行，替代"生成代码 + subprocess"路径，兼顾安全性与结果可重放；
- **成本优化**：选择器方案缓存（键为 host + 归一化意图 + 字段集），同站同请求复用已验证方案，实现**零 LLM 调用**抓取；缓存维护为结果驱动（校验通过才写入、事后失败即失效），过期选择器自愈。配合按角色分派模型（通用推理 / code 专用）与 DOM prompt 预算控制，并记录每次运行的 token 用量；
- **FastAPI + SSE** 全异步链路流式推送 Agent 节点级执行进度；LLM 接入抽象为角色化工厂，当前支持 DashScope（Qwen3）与 Anthropic，新增 provider 只需加一个分支；
- **工程化**：pydantic-settings 全量配置外置（21 项）、request_id 贯穿的结构化日志、SSRF 防护（拒绝内网地址）、启动时对账中断任务、并发渲染上限、瞬时错误退避重试；pytest（mock LLM + HTML fixture + 内存 SQLite，61 用例）、mypy 全量通过、GitHub Actions CI、Docker 交付。

---

## 8. 风险与边界

- **LLM 成本**：DOM 摘要必须做激进压缩（去脚本样式、截断重复列表项、只保留定位必需属性），否则大页面 token 失控——structure_dom 节点是成本关键路径。
- **反爬与合规**：本项目定位是"指定页面的内容抽取"，不做代理池 / 验证码破解 / 大规模并发爬取。已实现的边界是 SSRF 防护（拒绝内网地址）与并发渲染上限；**robots.txt 检查与按 host 限速尚未实现**（每次运行只发一个请求，节奏取决于调用频率），README 的 Scope 章节已如实声明。若要用于更广的抓取场景，应先补上 robots.txt 检查。
- **范围控制**：登录态页面、无限滚动、跨页去重等属于 P5 之后的可选演进，不纳入本轮目标。
