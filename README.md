# FMEA 知识图谱增强检索问答系统

本项目是一个面向中文 FMEA/FMECA 表格的本地知识图谱增强检索问答系统。系统支持 FMEA 表格导入、字段标准化、Neo4j 知识图谱构建、确定性规则问答、Query IR 结构化查询、向量 RAG 兜底检索和 Web 前端访问。

项目适合用于课程实验、FMEA 表格问答验证、知识图谱增强检索流程复现，以及面向工业表格数据的 RAG 方法对比实验。

## 功能特性

- 支持从 FMEA/FMECA CSV 表格构建本地知识图谱。
- 支持失效模式、失效原因、失效后果、项目、功能、风险等级等 FMEA 核心字段的结构化查询。
- 支持 CSV 直答、确定性规则、Query IR、图谱检索和向量检索多路问答流程。
- 支持 Ollama 本地大模型和 embedding 模型，便于离线运行。
- 支持 Neo4j 图数据库存储和查询 FMEA 实体关系。
- 提供 Flask 前端代理和浏览器问答界面。
- 提供批量实验、消融实验、对比实验和评分脚本。
- 支持局域网访问，也可通过 Cloudflare Tunnel 做临时公网访问。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 后端 API | Python, Connexion, Flask, Uvicorn |
| 知识图谱 | Neo4j |
| 问答与向量模型 | Ollama, OpenAI-compatible API, LangChain |
| 数据处理 | pandas, openpyxl, scikit-learn |
| 前端 | HTML, CSS, JavaScript, Flask proxy |
| 实验评估 | Python scripts, CSV/JSON/JSONL reports |

## 仓库结构

```text
├── code/                       # KG-RAG 后端核心代码
│   ├── kg_rag.py               # 后端 HTTP 入口
│   ├── kg_rag_runtime.py       # RAG 服务懒初始化
│   ├── graph_building.py       # CSV 入图和向量索引构建
│   ├── api.yml                 # OpenAPI 接口定义
│   └── kg_rag_core/            # schema、仓储层、Query IR、问答服务
├── csv_trans/                  # FMEA 表格标准化与归一化脚本
├── rag_frontend/               # 前端页面与 Flask 代理服务
├── scripts/                    # 批量测试、题目生成、打分和实验脚本
├── tests/                      # 单元测试
├── 实验/                       # 主要对比实验、消融实验和结果报告
├── 优化实验/                   # 优化后的补充实验结果
├── 论文写作/                   # 论文写作材料和流程图
├── 论文证据/                   # 参考论文、证据材料和改动记录
├── start.txt                   # 常用启动命令速查
├── requirements.txt            # Python 依赖
├── requirement_linux.txt       # Linux 环境依赖
├── LICENSE                     # 开源许可证
└── README.md                   # 项目说明文档
```

说明：`data/`、`answer/`、本地日志、模型文件和数据库文件属于本地运行产物或原始数据，默认不上传到 GitHub。实验报告和可复核结果保存在 `实验/`、`优化实验/` 等目录中。

## 环境要求

推荐运行环境：

- Linux 服务器或 WSL 环境
- Python 3.10 或兼容版本
- Conda 环境，建议环境名为 `fmea`
- Neo4j 5.x
- Ollama
- Git

本项目默认使用本地服务：

| 服务 | 默认地址 | 用途 |
| --- | --- | --- |
| Neo4j Bolt | `bolt://127.0.0.1:7687` | 存储和查询知识图谱 |
| Ollama | `http://127.0.0.1:11434` | 本地 embedding 和问答模型 |
| 后端 API | `http://127.0.0.1:8080/api/v1` | KG-RAG 问答接口 |
| 前端页面 | `http://127.0.0.1:5000` | 浏览器问答界面 |

推荐模型配置：

```text
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

## 安装与配置

进入项目目录：

```bash
cd /home/lizhaoxuan/fmea
```

激活 Conda 环境：

```bash
conda activate fmea
```

如果当前终端不能直接激活环境，可以使用：

```bash
conda run -n fmea python --version
```

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

Linux 环境也可以使用：

```bash
pip install -r requirement_linux.txt
```

确认 Neo4j 可访问：

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p <你的Neo4j密码> "RETURN 1 AS ok;"
```

确认 Ollama 可访问：

```bash
curl http://127.0.0.1:11434/api/tags
ollama list
```

如模型不存在，先下载模型：

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

## 环境变量

在仓库根目录创建 `.env` 文件。不要把真实密码提交到 GitHub。

```env
NEO4J_URL=bolt://127.0.0.1:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<你的Neo4j密码>
NEO4J_DATABASE=neo4j

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_API_BASE=http://127.0.0.1:11434/v1
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
```

前端代理的示例配置在 `rag_frontend/.env.example`，可复制为 `rag_frontend/.env` 后按需修改：

```bash
cp rag_frontend/.env.example rag_frontend/.env
```

## 快速开始

启动后端：

```bash
cd /home/lizhaoxuan/fmea
conda run -n fmea python code/kg_rag.py
```

默认后端地址：

```text
http://127.0.0.1:8080/api/v1
```

导入 FMEA CSV 并构建知识图谱：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/create-fmea-graph \
  -H "Content-Type: application/json" \
  -d '{"path":"data/磷酸铁锂电池FMECA分析表20250416105822.csv"}'
```

执行一次问答：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/question-answer \
  -H "Content-Type: application/json" \
  -d '{"question":"失效模式“单体电压过低”的RPN是多少？"}'
```

启动前端：

```bash
cd /home/lizhaoxuan/fmea/rag_frontend
FMEA_API_BASE=http://127.0.0.1:8080/api/v1 conda run -n fmea python server.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

局域网访问时，将 `127.0.0.1` 换成服务器 IP，例如：

```text
http://172.23.166.240:5000
```

## 常用接口

### 构建图谱

```bash
curl -X POST http://127.0.0.1:8080/api/v1/create-fmea-graph \
  -H "Content-Type: application/json" \
  -d '{"path":"data/磷酸铁锂电池FMECA分析表20250416105822.csv"}'
```

### 问答

```bash
curl -X POST http://127.0.0.1:8080/api/v1/question-answer \
  -H "Content-Type: application/json" \
  -d '{"question":"失效模式“电池箱体进水”的潜在失效后果是什么？"}'
```

### 设置检索候选数量

```bash
curl -X POST http://127.0.0.1:8080/api/v1/set-top_k \
  -H "Content-Type: application/json" \
  -d '{"top_k":5}'
```

### 清空图谱

```bash
curl -X POST http://127.0.0.1:8080/api/v1/clear-fmea-graph \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

## 数据处理

本项目的原始数据默认放在本地 `data/` 目录，但该目录不会上传到 GitHub。这样可以避免上传原始表格、隐私数据或体积较大的中间文件。

CSV 标准化示例：

```bash
cd /home/lizhaoxuan/fmea
conda run -n fmea python csv_trans/normalize_fmea.py \
  data/磷酸铁锂电池FMECA分析表20250416105822.csv \
  --output data/lfp_normalized.csv \
  --format csv
```

电子元器件表转换示例：

```bash
cd /home/lizhaoxuan/fmea
conda run -n fmea python csv_trans/normalize_fmea.py \
  data/电子元器件及故障模式.xlsx \
  --output data/electronic_components_normalized.csv \
  --format csv
```

## 实验与评估

实验结果主要保存在：

- `实验/`：对比实验、消融实验、模块专项实验和汇总报告。
- `优化实验/`：优化模块后的补充实验结果。
- `论文写作/`：论文草稿、流程图和写作材料。
- `论文证据/`：参考论文、证据材料和改动记录。

批量打分示例：

```bash
cd /home/lizhaoxuan/fmea
conda run -n fmea python scripts/score_dfmea_qa.py \
  --csv data/磷酸铁锂电池FMECA分析表20250416105822.csv \
  --questions answer/lfp_fmeca_500_questions.jsonl \
  --predictions answer/lfp_fmeca_500_answers.jsonl \
  --out-csv answer/lfp_fmeca_500_score_detail.csv \
  --out-json answer/lfp_fmeca_500_score_summary.json
```

说明：`answer/` 属于本地临时输出目录，默认不上传。需要保留到远端的实验结论应整理到 `实验/` 或 `优化实验/`。

## 开发与测试

运行测试：

```bash
cd /home/lizhaoxuan/fmea
conda run -n fmea python -m pytest tests
```

新增功能建议遵循现有结构：

- FMEA 字段标准化逻辑放入 `csv_trans/` 或 `code/kg_rag_core/fmea_schema.py`。
- 后端接口入口放入 `code/kg_rag.py` 和 `code/api.yml`。
- 问答主流程放入 `code/kg_rag_core/service/pipeline.py`。
- 规则化问答能力放入 `code/kg_rag_core/service/det_*.py`。
- 前端交互逻辑放入 `rag_frontend/`。
- 批量实验、题目生成、结果汇总脚本放入 `scripts/`。

## Git 提交规范

本仓库默认只上传以下内容：

- 代码文件
- 环境配置示例
- README、启动文档、论文写作和说明文件
- 已整理的实验结果和实验报告

以下内容默认不上传：

- `.env` 和真实密码
- `data/` 原始数据
- `answer/` 临时问答输出
- 本地日志、PID、缓存文件
- Neo4j 数据库、向量索引、模型权重和大文件

提交前建议检查：

```bash
git status --short
git diff --stat
```

## 常见问题

### 后端启动失败并提示 Neo4j 连接错误

先确认 Neo4j 正在运行，并检查 `.env` 中的连接地址、用户名和密码。

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p <你的Neo4j密码> "RETURN 1 AS ok;"
```

### 问答时提示 Ollama 模型不可用

先确认 Ollama 服务可访问，并检查模型是否已下载。

```bash
curl http://127.0.0.1:11434/api/tags
ollama list
```

### 前端无法访问后端

检查前端启动时的 `FMEA_API_BASE` 是否指向正确后端地址。局域网访问时，前端和后端地址都应使用服务器 IP 或正确的代理地址。

### GitHub 推送失败并提示文件过大

检查是否误上传了模型、原始数据或超大的实验原始输出。此类文件应放入本地目录，或整理成压缩后的报告与指标文件后再提交。

## 安全说明

- 不要提交 `.env`、数据库密码、API Key 或真实业务数据。
- 公网长期部署时建议使用 Nginx、HTTPS 和鉴权。
- 不建议直接暴露后端 `8080` 接口到公网。
- 需要共享实验时，优先共享脱敏后的结果文件和实验报告。

## 许可证

本项目使用 MIT License。详情见 [LICENSE](LICENSE)。

## 联系方式

如果问题与当前项目实现有关，请在本仓库提交 issue，或直接在当前工作区继续修改和测试。
