# 架构与 Agent 能力改进方案

> 背景：本项目是服务于 ~10 人数据分析团队的内部工具，无高并发诉求，目标是
> **正确性、成本可控、可运维**。本方案据此校准——凡是"企业级但对本规模属于过度
> 设计"的（微服务、K8s、Postgres、分布式追踪、Vault 等）一律**明确不做**，只保留
> 在当前规模就会真实咬到人的改进。

本文档分三部分：
1. Review 结论（偏差清单）
2. 分阶段改进计划
3. Phase 0（本次已落实的改动）

---

## 1. Review 结论

### 1.1 架构设计层面 vs 企业级实践的偏差

| # | 偏差 | 影响 | 规模判定 |
|---|---|---|---|
| A1 | `POST /scrape` 在请求内同步跑完整个 Agent（fetch + 多次 LLM，30s–2min），无作业抽象 | 无取消、无整体超时预算 | 需处理 |
| A2 | 单 Chromium 共享、每请求 `new_page()`，**无并发上限**；LLM 调用亦无背压 | 多人同时使用可能耗尽内存/句柄 | 需处理 |
| A3 | 落库只在跑完之后（`_persist`）；进程崩溃或 SSE 断连 → **零记录** | 可运维性缺口 | 需处理 |
| A4 | 全链路无 token / 成本计量 | "成本控制"目标无数据支撑 | 需处理 |
| A5 | 产出的 `extraction_plan` / `selector_plan` **未持久化** | 结果抽错时无法复盘 | 需处理 |
| A6 | 外部 sink 为 fire-and-forget，失败仅 log，无重试/补偿 | 目标分析库静默丢数据 | 需处理 |
| A7 | 无任何认证，无用户归属（`created_by` 缺失） | 团队共享工具无法追责/审计 | 视网络环境 |
| A8 | 建表用 `create_all`、无 Alembic | 模式演进不受管理 | **可接受**（代码已自觉） |
| A9 | SQLite 作应用库、单进程 | 无水平扩展 | **可接受**（规模内合理） |

### 1.2 Agent 应用层面（运行时真实问题）

| # | 问题 | 影响 |
|---|---|---|
| B1 | 瞬时故障（429/5xx/超时）无重试即整轮失败；反射循环只在**质量差**时切策略 | 单次网络抖动打断整轮 |
| B2 | DOM 硬截断（`dom_json[:12000]`），长列表静默丢记录，校验器无"是否抽全"信号 | 完整性缺口，用户无感知 |
| B3 | 无缓存 / selector 复用，同 (url, prompt) 重跑全量烧 token | 与成本控制矛盾 |
| B4 | best-effort 返回**最后一次**而非**最好一次**，retry 可能把结果改差 | 正确性回退 |
| B5 | 无防幻觉抽检（不校验抽出值是否真的在源 DOM 中） | llm 策略可能编造 |
| B6 | `llm_extractor` 用裸 JSON 解析（不同于 planner/selector 的结构化输出），更脆 | 偶发解析崩溃 |
| B7 | 失败时不返回任何部分产出（plan / DOM） | token 已花，用户一无所获 |

---

## 2. 分阶段改进计划

按"当前规模的投入产出比"排序。Phase 0 已在本次落实。

### Phase 0 — 低成本、高确定性（✅ 已完成，见第 3 节）
- B1 瞬时故障重试退避（可配置）
- B6 抽取解析失败的修复式重试
- B4 反射循环保留最优结果
- A2 Playwright 并发上限
- A5 plan / selector_plan 持久化 + Task 详情暴露
- B2（部分）DOM 截断的配置化 + 告警日志

### Phase 1 — 可运维 / 成本可见 ✅ 全部完成
- **A3 提交即建行**：✅ 已完成（见 3.7）。
- **A4 token/成本计量**：✅ 已完成（见 3.8）。
- **B2 截断信号入响应**：✅ 已完成（见 3.9）。

### Phase 2 — 质量护栏 / 省钱 ✅ 全部完成
- **B3 selector 复用缓存**：✅ 已完成（见 3.10）。
- **B5 防幻觉抽检**：✅ 已完成（见 3.11）。
- **B7 失败返回部分产出**：✅ 已完成（见 3.12）。

### Phase 3 — 按需（多为组织/合规触发，非技术必需）
- **A7 轻量认证 + 用户归属**：网关/SSO header 透传，Task 记 `created_by`。
- **A6 sink 补偿**：失败任务打 `sink_pending` 标记 + 手动/定时重推入口（本地库为
  权威源，无需上 outbox）。
- **A1 作业化 + 取消**：若同步请求时长成为体验痛点，再引入后台任务 + 取消/整体超时。

### 明确不做（对本规模过度）
微服务化、K8s、Postgres 迁移、分布式追踪（Jaeger 等）、Vault/KMS、Alembic
（等到模式真正在生产演进再引入，代码注释已如此约定）。

---

## 3. Phase 0 已落实的改动

全部通过 `ruff` / `mypy` / `pytest`（37 passed），新增 3 个针对性用例。

### 3.1 瞬时故障重试退避（B1）
- `core/config.py`：新增 `llm_max_retries`（默认 3）、`llm_timeout_s`。
- `services/llm/client.py`：将 `max_retries` / `timeout` 下发给 DashScope
  (`ChatOpenAI`) 与 Claude (`ChatAnthropic`)，由底层客户端做指数退避（429/5xx/超时）。
- 语义澄清：此为**传输层**重试，与反射循环的**质量层**跨策略重试是两回事。

### 3.2 抽取解析的修复式重试（B6）
- `services/extraction/llm_extractor.py`：回复无法解析为 JSON 时，追加一条纠正指令
  重试一次（`max_attempts=2`）再判失败，避免模型多说一句话就整轮崩溃。

### 3.3 反射循环保留最优结果（B4）
- `agents/state.py`：新增 `best_result` / `best_validation` / `best_score`。
- `agents/nodes/validate_result.py`：以 `(是否通过, 有无记录, 平均覆盖率)` 打分跟踪
  历史最优；重试若回退，best-effort 分支返回**更优的早期结果**而非最后一次。
- 新增用例 `test_keeps_best_attempt_when_retry_regresses`。

### 3.4 Playwright 并发上限（A2）
- `core/config.py`：新增 `max_concurrent_browsers`（默认 2）。
- `services/fetch_service.py`：渲染路径加 `asyncio.Semaphore` 背压。

### 3.5 plan / selector_plan 持久化（A5）
- `models/orm.py`：`ScrapeTask` 增 `plan`、`selector_plan`（JSON，可空）。
- `repository/task_repo.py`：`save_from_state` 一并写入。
- `models/schemas.py` + `api/v1/tasks.py`：`TaskDetail` 暴露二者，供结果复盘。
- ⚠️ 注意：本地库用 `create_all`，**不会给已存在的表加列**。已有 `scraper.db`
  需删除重建（或后续用一次性 `ALTER TABLE` 迁移）。新部署无此问题。

### 3.6 DOM 截断配置化 + 告警（B2 部分）
- `core/config.py`：新增 `dom_prompt_char_budget`（默认 12000），消除硬编码魔数。
- `llm_extractor.py` / `selector_gen.py`：预算由 `main.py` 注入；序列化超预算时打
  WARNING 日志。（把该信号提升到响应/校验指标留待 Phase 1。）

### 3.7 提交即建行（A3，Phase 1）
- `repository/task_repo.py`：新增 `create_running(task_id, url, prompt)` 先写入
  `status=pending` 的占位行；`save_from_state` 改为 **upsert**（有则更新、无则插入），
  用 `selectinload` 预载 result 关系以避免异步惰性加载。
- `api/v1/scrape.py`：`/scrape` 与 `/scrape/stream` 均在**请求进入即建行**，跑完再
  更新同一行；未预期异常经 `_mark_failed` 落为 FAILED，否则崩溃/断连时该行停留在
  `pending`——这正是"卡住/孤儿任务"的可见信号（此前是零记录）。
- 流式接口新增一个 `started` 事件把 `task_id` 前置下发，客户端断连后仍可凭此在历史
  中对账（前端忽略未知事件，向后兼容）。
- **启动清理（闭环 pending）**：新增 `ScrapeStatus.INTERRUPTED`；`task_repo`
  新增 `mark_stale_interrupted()`，在 lifespan 启动时把上一进程遗留的非终态行
  （崩溃/重启导致的 pending 等）一次性收敛为 `interrupted` 并记 `finished_at`，
  幂等。前端 `STATUS_COLORS` 补上 `pending`(default)/`interrupted`(warning)。
  这样"卡住的任务"既有实时信号、又能在重启后自动收尾，不会永久停留 pending。
- 新增用例 `test_create_running_then_finalize_updates_same_row`（同行更新、无重复、
  保留 `created_at`）与 `test_mark_stale_interrupted_sweeps_only_nonterminal`
  （只扫非终态、幂等）。

### 3.8 token / 成本计量（A4，Phase 1）
- 采用 LangChain 原生 `UsageMetadataCallbackHandler`：在 `scraper_agent` 的
  `run` / `astream_run` 于图边界创建一个 handler 并经 `config={"callbacks":[...]}`
  传入。LangGraph 会把回调下传到**每一次**嵌套 LLM 调用——包括 planner/selector 的
  结构化输出调用（其解析后的返回值本会丢掉 usage）。**服务层、节点、测试 fake 全部
  零改动**，这是相比"逐层返回 usage 元组"更干净的选择。
- `services/llm/usage.py`：`summarize_usage()` 把 handler 的按模型用量折叠成
  `{input_tokens, output_tokens, total_tokens, by_model}`，attach 到 state。
- 持久化：`ScrapeTask` 增 `input_tokens/output_tokens/total_tokens` 三列；
  `save_from_state` 从 `token_usage` 写入。
- 暴露：`ScrapeResponse.token_usage`（含 by_model 明细）、`TaskSummary.total_tokens`
  （历史列表）、`TaskDetail` 增 input/output 明细。
- 前端：历史表加 **Tokens** 列；结果卡片标题加 token 数标签（打开历史任务时同样显示）。
- 新增用例 `test_llm_usage.py`（求和/空值/缺 total 推断）＋ 持久化与图测试中对
  token 字段的断言。

### 3.9 截断信号入响应（B2，Phase 1）
- 单一真相源：把截断判定从两个抽取器移到 **`structure_dom` 节点**——序列化一次
  DOM、与 `char_budget` 比较，写入 `state["dom_truncated"]`（抽取器只保留切片、不再
  各自告警）。`char_budget` 经 `ScraperAgent(dom_char_budget=...)` 从 settings 注入。
- `ResultValidator.validate(result, *, dom_truncated)`：新增 **`warnings`** 通道
  （与 `issues` 分离）——截断且有记录时给一条"页面过大、模型只看到截断视图，可能漏抽"
  的**建议**；关键点：**不翻转 `ok`、不触发重试**（换策略也解决不了页面过大）。
  `dom_truncated` 也进 `metrics`。
- 因 `ScrapeResponse.validation` 直接透传报告，`warnings` 自动进响应体。
- 前端：结果区在 `validation.warnings` 非空时显示一条 warning Alert（打开历史任务
  同样显示）。
- 新增用例：validator 的告警/不失败/空结果不告警；图测试用 `dom_char_budget=1`
  强制截断，断言完成 + `ok` + warning。

### 3.10 selector 复用缓存（B3，Phase 2）
- 新增 **`selector_cache` 表**（独立表，`create_all` 在旧库上**增量创建、无需迁移**）
  + `SelectorCacheRepository`（get/put/invalidate，get 顺带累加 hit_count）。
- `services/extraction/cache.py`：`SelectorCache` 协议 + `selector_cache_key(url,
  prompt, fields)`——按 **host + 归一化 prompt + 字段集**（顺序无关）哈希，让同站兄弟
  页共享一个 plan。
- 图集成：**`gen_selectors` 读**——命中即复用、跳过 LLM 生成（但反射重试即带
  feedback 时不读缓存，强制重新生成）；**`validate_result` 写**——按结果**结局**维护：
  selector 结果通过校验 → `put`（存已验证的 plan）；命中的缓存 plan 失败 →
  `invalidate`，让陈旧选择器**自愈**而非永久失败。`validate_result` 因此改为 async。
- 成本安全性：命中即跳过 selector 生成的 LLM 调用；即便缓存陈旧导致失败回退到 llm，
  成本也 **≤ 不缓存**（省了一次 selector-gen 调用），且失败即失效、下轮重生。
- 新增用例：key 稳定/敏感、repo put/get/invalidate/覆盖、端到端"存后复用免生成"、
  "陈旧缓存失败即失效并回退"。

### 3.11 防幻觉抽检（B5，Phase 2）
- `ResultValidator.validate(..., source_text=raw_html)`：**仅对 `llm` 策略**（选择器
  结果直接取自 DOM、不会编造）抽样其字符串值（跳过 <3 字符），回查是否出现在源页面
  文本里；样本≥4 且**过半查不到**则记为 `issue`（"possible hallucination"）→ 触发反射。
  比例进 `metrics.unsupported_ratio`。选择器结果与值齐全的 llm 结果都不误伤。
- 节点从 `state["raw_html"]` 传入源文本（对全量 HTML 校验，避开截断误判）。
- 新增用例：llm 幻觉判失败、值齐全放行、selector 不检查；端到端 llm 幻觉→回退 selector。

### 3.12 失败返回部分产出（B7，Phase 2）
- `ScrapeResponse` 增 `plan`；`_build_response` **始终**带上 `extraction_plan`，`data`
  在无抽取结果时回退到压缩 DOM——失败运行也能看到"agent 规划了哪些字段、卡在哪、
  恢复了多少结构"，而非一无所获。
- 前端：失败时在错误下方显示"规划了哪些字段 / 选了什么策略"；打开历史失败任务同样。
- 新增用例 `test_response_builder.py`：失败态返回 plan + 部分 DOM。

### 涉及文件
```
backend/app/core/config.py
backend/app/services/llm/client.py
backend/app/services/fetch_service.py
backend/app/services/extraction/llm_extractor.py
backend/app/services/extraction/selector_gen.py  # 截断告警移至节点 (3.9)
backend/app/services/extraction/validator.py     # warnings (3.9) + 防幻觉 (3.11)
backend/app/services/extraction/cache.py          # SelectorCache + key (3.10)
backend/app/agents/state.py
backend/app/agents/nodes/gen_selectors.py    # 读缓存 (3.10)
backend/app/agents/nodes/validate_result.py  # 写/失效缓存 + 传 source_text (3.10/3.11)
backend/app/agents/nodes/structure_dom.py   # 截断判定单一真相源 (3.9)
backend/app/models/orm.py                    # + selector_cache 表 (3.10)
backend/app/models/schemas.py                # + response.plan (3.12)
backend/app/repository/task_repo.py       # + create_running / upsert (3.7)
backend/app/repository/selector_cache_repo.py  # SelectorCacheRepository (3.10)
backend/app/api/v1/tasks.py
backend/app/api/v1/scrape.py              # 提交即建行 (3.7) + token_usage (3.8) + plan (3.12)
backend/app/main.py                       # 启动清理 (3.7) + budget (3.9) + cache 装配 (3.10)
backend/.env.example
backend/app/agents/scraper_agent.py       # usage 回调 (3.8) + budget (3.9) + selector_cache (3.10)
backend/app/services/llm/usage.py         # summarize_usage (3.8)
frontend/src/components/Scraper/ScraperPage.js  # (3.7) Tokens (3.8) 截断 (3.9) 失败 plan (3.12)
backend/tests/integration/test_graph.py    # + 缓存/幻觉端到端 (3.10/3.11)
backend/tests/unit/test_extraction_services.py
backend/tests/unit/test_validator.py       # 截断告警 (3.9) + 防幻觉 (3.11)
backend/tests/unit/test_selector_cache.py  # key + repo (3.10)
backend/tests/unit/test_response_builder.py # 失败返回部分产出 (3.12)
backend/tests/unit/test_persistence.py    # + create_running upsert (3.7) + tokens (3.8)
backend/tests/unit/test_llm_usage.py       # summarize_usage (3.8)
```
