# FMEA 知识图谱增强检索问答系统

本项目是一个面向中文 FMEA/FMECA 表格的本地知识图谱增强检索问答系统。系统支持 FMEA 表格导入、统一字段标准化、Neo4j 知识图谱构建、规则化问答、Query IR 结构化查询、向量 RAG 兜底和前端 Web 访问。

## 摘要

失效模式与影响分析（FMEA）用于识别潜在失效、分析失效后果、评估风险等级并制定改进措施。传统 FMEA 数据通常以表格形式存在，字段结构固定但语义关系不显式，难以支撑自然语言问答、跨项目检索和风险分析。

本项目将 FMEA 表格数据标准化为统一 schema，并构建包含失效模式、失效原因、失效后果、项目/功能等实体的知识图谱。系统在问答阶段采用多层路径：CSV 直答、确定性规则、Query IR 结构化查询和向量 RAG 兜底，以提高客观问答的稳定性和可解释性。

当前实现支持本地 Ollama 模型、Neo4j 图数据库、前端 Web 界面、局域网访问和 Cloudflare Tunnel 临时公网访问。

## 仓库结构

```text
├── code/                       # KG-RAG 后端核心代码
│   ├── kg_rag.py               # 后端 HTTP 入口
│   ├── kg_rag_runtime.py       # RAG 服务懒初始化
│   ├── graph_building.py       # CSV 入图和向量索引构建
│   └── kg_rag_core/            # schema、仓储层、Query IR、问答服务
├── csv_trans/                  # FMEA 表格标准化与归一化脚本
├── data/                       # 示例 CSV/XLSX 数据
├── rag_frontend/               # 前端页面与 Flask 代理服务
├── scripts/                    # 批量测试、题目生成、打分脚本
├── tests/                      # 单元测试
├── answer/                     # 问答结果、测试题和评分输出
├── start.txt                   # 本项目启动命令速查文档
├── requirements.txt            # 后端 Python 依赖
├── LICENSE                     # MIT License
└── README.md                   # 项目说明文档
```

## 安装与配置

1. 进入项目目录并使用已有 Conda 环境：

```bash
cd /home/lizhaoxuan/fmea
conda activate fmea
```

如果当前终端不能直接激活环境，可以使用：

```bash
conda run -n fmea python --version
```

2. 确认 Neo4j 已启动：

```bash
cypher-shell -a bolt://127.0.0.1:7687 -u neo4j -p <你的Neo4j密码> "RETURN 1 AS ok;"
```

3. 确认 Ollama 已启动，并安装 embedding 模型：

```bash
curl http://127.0.0.1:11434/api/tags
ollama list
```

推荐 embedding 模型：

```text
nomic-embed-text
```

4. 配置根目录 `.env`：

不要把真实密码提交到远端仓库。

## 使用方法

启动后端服务：

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

执行问答：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/question-answer \
  -H "Content-Type: application/json" \
  -d '{"question":"失效模式“单体电压过低”的RPN是多少？"}'
```

设置向量检索候选数量：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/set-top_k \
  -H "Content-Type: application/json" \
  -d '{"top_k":5}'
```

清空 FMEA 图谱：

```bash
curl -X POST http://127.0.0.1:8080/api/v1/clear-fmea-graph \
  -H "Content-Type: application/json" \
  -d '{"confirm":true}'
```

启动前端界面：

```bash
cd /home/lizhaoxuan/fmea/rag_frontend
FMEA_API_BASE=http://127.0.0.1:8080/api/v1 conda run -n fmea python server.py
```

浏览器访问：

```text
http://127.0.0.1:5000
```

局域网访问时，将 `127.0.0.1` 换成运行服务机器的局域网 IP，例如：

```text
http://172.23.166.240:5000
```

临时公网访问可使用 Cloudflare Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

公网长期部署时，建议使用 Nginx、HTTPS 和鉴权，不建议直接裸露后端 `8080` 接口。

## 附加资源

- Neo4j：[https://neo4j.com/](https://neo4j.com/)
- Ollama：[https://ollama.com/](https://ollama.com/)
- OpenAPI：[https://www.openapis.org/](https://www.openapis.org/)

## 贡献

本项目当前处于课程/实验项目维护阶段。新增功能建议优先遵循现有结构：

- FMEA 字段标准化逻辑放入 `csv_trans/` 或 `code/kg_rag_core/fmea_schema.py`。
- 后端接口入口放入 `code/kg_rag.py` 和 `code/api.yml`。
- 问答主流程放入 `code/kg_rag_core/service/pipeline.py`。
- 规则化问答能力放入 `code/kg_rag_core/service/det_*.py`。
- 前端交互逻辑放入 `rag_frontend/`。

提交前建议至少运行相关测试或脚本验证：

```bash
conda run -n fmea python -m pytest tests
```

## 许可证

本项目使用 MIT License。详情见 [LICENSE](LICENSE)。

## 联系方式

如果问题与当前项目实现有关，请在本仓库提交 issue，或直接在当前工作区继续修改和测试。
