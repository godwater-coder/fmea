# AI 后端开发工作流

本工作流面向当前仓库，目标是让你用 AI 稳定地推进后端开发，尤其是 `code/` 下的 FMEA / KG-RAG 服务。

适用范围：

- `code/kg_rag.py`
- `code/api.yml`
- `code/kg_rag_core/`
- `code/graph_building.py`
- `data/`
- `answer/`
- 需要接入管理后台时的 `FluxPanel/flux-backend`

## 1. 先定义开发边界

在让 AI 开工前，先把需求归类到下面 4 种之一：

1. API 层改动
2. 规则问答改动
3. 检索/图谱/Neo4j 改动
4. 集成与联调改动

对应目录：

- API 层：`code/api.yml`、`code/kg_rag.py`
- 规则问答：`code/kg_rag_core/service/det_*.py`、`code/kg_rag_core/service/pipeline.py`
- 检索与仓储：`code/kg_rag_core/repository.py`、`code/kg_rag_core/service/ops.py`
- 建图与数据：`code/graph_building.py`、`data/*.csv`
- 管理后台集成：`FluxPanel/flux-backend`、`FluxPanel/flux-frontend`

原则：

- 不要让 AI 一次同时改 API、规则分支、Neo4j 仓储和前端，除非你明确要求端到端交付。
- 能放进 deterministic 分支的问题，不要默认走 LLM。
- 能通过现有 schema 和 repository 完成的查询，不要让 AI 新造一层抽象。

## 2. 推荐的人机协作分工

你负责：

- 给出业务目标，而不是只给技术动作
- 指定影响范围
- 决定是否接受接口变更、返回结构变更、数据结构变更
- 审核 AI 产出的行为是否符合业务

AI 负责：

- 阅读相关代码
- 找到最小改动点
- 实现代码
- 补充必要测试或验证脚本
- 执行本地验证并汇报风险

推荐输入格式：

```txt
目标：
要新增/修复什么能力。

范围：
允许修改哪些目录或文件。

输入输出：
接口入参、返回值、错误码、示例问题。

约束：
必须走 deterministic / 不能改现有返回结构 / 不能影响已有问题回答。

验收：
给出 3~5 条可验证样例。
```

## 3. 标准开发流程

### 阶段 A：需求收敛

先让 AI 回答这 5 件事：

1. 需求属于哪个模块
2. 最可能改哪些文件
3. 是否会影响现有 API
4. 是否需要改 Neo4j 图结构或索引
5. 如何验证没有回归

如果 AI 说不清这 5 点，不要直接让它写代码。

### 阶段 B：代码定位

要求 AI 先读，不要先写。

最低要求：

- 找 API 入口：`code/api.yml`、`code/kg_rag.py`
- 找主流程：`code/kg_rag_core/service/pipeline.py`
- 找对应 deterministic 模块：`code/kg_rag_core/service/det_*.py`
- 找仓储和查询能力：`code/kg_rag_core/repository.py`
- 找建图逻辑：`code/graph_building.py`

这一步的目标不是解释全部代码，而是回答：

- 改动应该落在哪一层
- 有没有现成模式可以复用
- 会不会破坏已有问答链路

### 阶段 C：小步实现

每次只让 AI 做一个明确动作：

1. 先改实现
2. 再补验证
3. 最后跑回归

不要给这种指令：

```txt
帮我顺便把接口、前端、提示词、数据库、性能都优化一下
```

应该拆成：

1. 先新增后端能力
2. 再验证旧问题不回归
3. 再决定是否接前端

### 阶段 D：本地验证

这个项目至少做 4 类验证：

1. 服务能启动
2. 图已初始化或可建图
3. 新增问题能答对
4. 旧有典型问题不回归

最低验证清单：

```bash
python code/kg_rag.py
```

建图验证：

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/create-fmea-graph \
  -H 'Content-Type: application/json' \
  -d '{"path":"data/example_fmea.csv"}'
```

问答验证：

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/question-answer \
  -H 'Content-Type: application/json' \
  -d '{"question":"What failure mode has the highest RPN?"}'
```

参数验证：

```bash
curl -sS -X POST http://127.0.0.1:8080/api/v1/set-top_k \
  -H 'Content-Type: application/json' \
  -d '{"top_k":5}'
```

### 阶段 E：结果验收

验收时只看 4 件事：

1. 功能是否按你的业务意图工作
2. 返回结构是否兼容
3. 是否把客观题错误地改成了 LLM 生成题
4. 是否引入了新的隐性依赖

## 4. 这个仓库最适合 AI 做的后端任务

### 4.1 新增 deterministic 问答

适合场景：

- Top-N
- 阈值筛选
- 某项目/某工序统计
- 某 severity / cause / control 的查表题

推荐落点：

- `code/kg_rag_core/service/det_*.py`
- `code/kg_rag_core/service/pipeline.py`

要求：

- 优先复用现有 `_try_answer_*` 风格
- 命中条件明确
- 未命中时返回 `None`
- 不要吞掉异常边界

### 4.2 新增 API

适合场景：

- 新增配置接口
- 新增调试接口
- 新增导出接口

推荐落点：

- 契约：`code/api.yml`
- 处理函数：`code/kg_rag.py`
- 具体能力：`code/kg_rag_core/service/`

要求：

- 先定义 request / response schema
- 再接 handler
- 不要把业务逻辑全部堆在 `kg_rag.py`

### 4.3 Neo4j / 检索增强

适合场景：

- 优化图查询
- 补 schema 兼容
- 增强向量检索回退
- 处理 embedding 或网络异常降级

推荐落点：

- `code/kg_rag_core/repository.py`
- `code/kg_rag_core/service/ops.py`
- `code/graph_building.py`

要求：

- 优先保守修改
- 先保证可降级
- 不要轻易改索引名、节点标签、关系名

### 4.4 FluxPanel 集成

适合场景：

- 把 FMEA 问答能力包装进管理后台
- 增加后台配置页或接口转发层

要求：

- 先明确谁是主后端
- 不要把 `code/` 的实验型业务逻辑直接塞进 `FluxPanel/flux-backend` 核心模块
- 更推荐通过 API 调用或独立服务集成

## 5. 给 AI 的提示词模板

### 模板 1：新增 deterministic 能力

```txt
请基于当前仓库实现一个新的 deterministic 问答能力。

目标：
支持回答：<在这里写问题类型和示例问题>

约束：
1. 优先走 deterministic，不要走 LLM 生成。
2. 保持现有 API 返回结构兼容。
3. 未命中时必须返回 None，让主流程继续回退。
4. 只允许修改与该能力直接相关的最小文件集。

请先阅读：
- code/kg_rag_core/service/pipeline.py
- code/kg_rag_core/service 下相关 det_*.py
- code/kg_rag_core/repository.py

然后执行：
1. 说明你准备修改哪些文件以及原因
2. 实现代码
3. 给出最小验证方法
4. 说明可能的回归风险
```

### 模板 2：新增 API

```txt
请为当前项目新增一个后端接口。

接口目标：
<写明用途>

输入：
<请求体>

输出：
<返回体>

约束：
1. 必须更新 code/api.yml。
2. handler 放在 code/kg_rag.py。
3. 具体业务逻辑下沉到 code/kg_rag_core/service。
4. 不要把复杂逻辑直接堆在路由层。

请先定位现有相似接口，再实现，并提供 curl 验证命令。
```

### 模板 3：修复问答错误

```txt
请排查当前问答错误，并优先做最小修复。

问题现象：
<写实际错误回答、报错、日志现象>

期望行为：
<写正确结果>

请先完成：
1. 判断问题出在 deterministic、Cypher 检索、向量检索还是最终生成阶段
2. 指出最小改动点
3. 实施修复
4. 用至少 3 个问题做回归验证
```

### 模板 4：做代码评审

```txt
请对当前改动做后端代码评审，重点检查：
1. 是否破坏现有 API
2. 是否误改 deterministic 路由顺序
3. 是否引入不必要的 LLM 依赖
4. 是否可能导致 Neo4j 未初始化时异常处理失真
5. 是否缺少最基本回归验证

输出以问题列表为主，按严重程度排序。
```

## 6. 你在这个项目里要重点防的 8 个坑

1. 直接修改 `pipeline.py` 分支顺序，导致已有高精度问答被更泛化的规则抢先命中。
2. 把本应查表的问题改成 LLM 生成，精度会明显下降。
3. 改了 `api.yml` 但没同步 `kg_rag.py` handler。
4. 改了返回结构，前端或调用脚本却没同步。
5. 误改 Neo4j 标签、关系名、索引名，导致旧图不可用。
6. 验证时没先建图，就误判接口逻辑有问题。
7. 只测新问题，不测旧问题，导致回归。
8. 把 `FluxPanel` 与主业务后端强耦合，后续维护成本会很高。

## 7. 推荐的提交粒度

理想提交粒度：

1. 一个需求只做一个能力
2. 一个提交只解决一类问题
3. 代码改动和验证说明同步出现

推荐结构：

- 提交 1：实现能力
- 提交 2：补验证或补文档

不要在一个提交里同时混入：

- 接口改名
- 路由重构
- 提示词大改
- Neo4j schema 改造

## 8. 我的建议用法

如果你接下来要持续用 AI 做这个项目的后端开发，建议固定采用下面节奏：

1. 先让我读相关代码并确认落点
2. 再让我做最小实现
3. 然后让我跑验证
4. 最后让我写变更说明和回归风险

对这个仓库，最高效的协作方式不是“让 AI 一次做完全部”，而是“让 AI 每次完成一个可验证的后端能力单元”。

## 9. 直接可用的开发指令

你后面可以直接对我说：

```txt
按 AI_BACKEND_WORKFLOW.md 执行：
先分析，再只改 code/kg_rag_core/service，给我新增一个 deterministic 问答能力，支持查询某个 project 下 RPN 最高的 3 个 failure mode，并跑最小验证。
```

或者：

```txt
按 AI_BACKEND_WORKFLOW.md 执行：
给当前项目新增一个后端接口，用于返回图是否已初始化。先更新 api.yml，再实现 handler 和 service，并给我 curl 验证命令。
```
