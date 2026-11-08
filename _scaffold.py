# -*- coding: utf-8 -*-
"""一次性脚手架脚本：生成赛题3 参赛仓库的初始文件（中文内容按 UTF-8 直接写入）。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FILES = {}

FILES["README.md"] = """# 领域资产认知智能体（华为 ICT 大赛 · 赛题3）

> 基于 **ModelEngine Nexent** 打造的可进化决策智能体：多模态行业数据 → 知识图谱本体 →
> 检索-推理双驱动 → 跨文档多跳推理 + 决策链路可溯源。

## 一、这是什么

面向 **{行业}** 场景，把沉睡的多模态存量数据资产（PDF / 扫描件 / 表格 / 图文报告）
统一识别、理解并资产标识，构建可动态更新的领域知识图谱本体，并基于 Nexent 的
MCP 协议与 Skills 编排能力，实现"检索-推理"双驱动的可溯源决策辅助。

**一句话**：不是聊天机器人，是"行业认知底座 + 可编排工具箱 + 每一步可倒查原件"的系统。

## 二、快速开始（复现步骤）

### 1. 环境要求
| 项 | 最低 | 推荐 |
|---|---|---|
| CPU | 4 核 | 8 核 |
| 内存 | 8 GiB | 16 GiB |
| 磁盘 | 40 GiB | 100 GiB |
| 软件 | Docker 24+ / Docker Compose v2+ | 同左 |

### 2. 启动 Nexent
```bash
git clone https://github.com/ModelEngine-Group/nexent.git
cd nexent
bash deploy.sh docker
```
默认访问 `http://localhost:3000`。首次使用超级管理员 `suadmin@nexent.com` 登录，
进入【租户资源】创建租户与租户管理员，再用新账号登录。

### 3. 导入本项目的智能体与工具
```bash
# TODO: 补充具体导入步骤（智能体 json / MCP 服务 / 知识库文件）
```

### 4. 复现效果
```bash
# TODO: 补充一条多跳问答的复现命令与预期输出
```

## 三、目录结构
```
ontology/        本体定义、LLM 抽取提示词、人工确认日志、标准对齐映射、版本
pipeline/        多模态解析管线（PDF / OCR / 表格）与图谱构建
mcp_servers/     自研 MCP 工具（图谱查询 / 标准检索 / 数值计算）
skills/          可复用 Skill 工作流模板
eval/            评测集、朴素 RAG 基线、对比结果
demo/            可视化 Demo 页面
deploy/          Nexent 部署配置与智能体配置导出
data/            原始数据（raw）与处理后数据（processed）
docs/            开发设计文档（初赛提交材料源稿）
```

## 四、关键指标
| 指标 | 朴素 RAG 基线 | 本方案 | 说明 |
|---|---|---|---|
| 多跳问答准确率 | TODO | TODO | eval/dataset.jsonl，共 N 题 |
| 溯源命中率 | TODO | TODO | 结论出处是否指向正确文件+页码 |
| 跨文档跳数（平均） | 1 | TODO | 需 ≥ 2 跳 |
| 本体构建人时 | TODO 人天 | TODO 人天 | 证明"半自动化" |
| 行业迁移耗时 | — | TODO | 附加分：多行业模板迁移 |

## 五、开源
- GitHub: TODO
- GitCode: TODO

## 六、许可证
MIT（见 `LICENSE`）。Nexent 本体亦为 MIT。
"""

FILES["docs/01-开发设计文档.md"] = """# 开发设计文档

> 对应初赛必交材料【开发设计文档 Word】：项目概述、整体方案设计、知识图谱构建方案、
> 智能体构建方案、原始数据说明、数据处理说明。

## 1. 项目概述
### 1.1 行业与场景
<!-- 明确行业（医疗/金融/制造/政务）、具体业务环节、真实痛点 -->
### 1.2 沉睡数据资产说明
<!-- 列清：数据从哪来、多少份、什么格式、为什么现在用不起来 -->
### 1.3 目标用户与使用方式

## 2. 整体方案设计
### 2.1 系统架构图
<!-- 必须有图。分层：数据接入层 / 认知层（本体+图谱）/ 编排层（MCP+Skill）/ 交互层 -->
### 2.2 数据流
### 2.3 与 Nexent 的集成点
<!-- 说明用了 Nexent 哪些能力：知识库 / MCP / Skill / A2A / 评估 -->

## 3. 知识图谱构建方案
见 `04-本体构建方案.md`。

## 4. 智能体构建方案
见 `03-智能体设计说明.md`。

## 5. 原始数据说明
<!-- 每份数据：名称、来源、格式、页数/行数、是否脱敏、获取方式 -->

## 6. 数据处理说明
<!-- 解析 → 清洗 → 切块 → 元数据标注 → 抽取 → 入库 -->
"""

FILES["docs/02-数据处理说明.md"] = """# 数据处理说明

## 1. 数据清单
| 编号 | 文件名 | 来源 | 格式 | 规模 | 脱敏方式 |
|---|---|---|---|---|---|
| D01 | | | PDF/扫描/XLSX/图文 | | |

## 2. 多模态解析
### 2.1 文本层
### 2.2 扫描件 OCR
### 2.3 表格结构还原
### 2.4 图文（图表/流程图）理解

## 3. 切块与元数据
<!-- 关键：每个 chunk 必须带 file / page / section / type / hash -->
```json
{
  "chunk_id": "",
  "text": "",
  "meta": {"file": "", "page": 0, "section": "", "type": "text|table|figure"}
}
```

## 4. 资产标识
<!-- 打标签：业务域、密级、时效、关联实体、可信度 -->

## 5. 入库与增量更新
<!-- 新增文档如何触发增量抽取？如何避免重复？ -->
"""

FILES["docs/03-智能体设计说明.md"] = """# Nexent 智能体设计说明

> 对应初赛必交材料第 2 项：模型信息、工具信息、知识库信息、**调用关系图**、
> **调试迭代经验**、示例问答截图，并附 json / 知识库 / MCP 文件说明。

## 1. 智能体清单
| 智能体名 | 职责 | 模型 | 工具 | 知识库 |
|---|---|---|---|---|
| | | | | |

## 2. 模型信息
| 用途 | 模型 | 部署方式 | 参数 |
|---|---|---|---|
| 主推理 | | MaaS / 本地 | temperature, max_tokens |
| 向量化 Embedding | | | |
| 多模态 VLM | | | |

## 3. 工具信息（MCP）
| 工具名 | 来源 | 功能 | 输入 | 输出 |
|---|---|---|---|---|
| kg_query | 自研 mcp_servers/kg_query | 图遍历多跳查询 | | |
| standards_lookup | 自研 | 标准条款检索 | | |
| calc | 自研 | 数值/剂量计算 | | |

## 4. 知识库信息
| 知识库 | 内容 | 切块策略 | 检索参数 | 权限 |
|---|---|---|---|---|

## 5. 调用关系图
<!-- 必须贴图：用户提问 → 规划 → [检索 | 图遍历 | 计算] → 证据汇总 → 推理 → 溯源报告 -->

## 6. 检索-推理双驱动执行流
<!-- 说明检索与推理如何交替，而不是"检索一次→生成一次" -->

## 7. 调试迭代经验
| 轮次 | 现象 | 原因分析 | 改动 | 效果变化 |
|---|---|---|---|---|
| v0.1 | | | | |

## 8. 示例问答
### 示例 1（多跳 + 溯源）
**问**：
**答**：
**推理链**：
**引用**：

## 9. 提交的配置文件
| 文件 | 路径 | 说明 |
|---|---|---|
| 智能体配置 | deploy/agent_config_export/ | |
| MCP 配置 | | |
| 知识库清单 | | |
"""

FILES["docs/04-本体构建方案.md"] = """# 低资源场景领域知识图谱本体半自动化构建方案

> 对应任务要求第 2 条：本体半自动化构建 + 持续动态更新 + 与行业规范/标准体系对齐。

## 1. 低资源约束
<!-- 说明：为什么标注稀缺？为什么传统固定知识库不适配？ -->

## 2. 半自动化构建流程
```
领域文档 → LLM 候选实体/关系抽取 → 语义聚类归并 → 人工审核命名
        → 本体候选 v(n) → 一致性校验 → 发布 v(n)
```
### 2.1 抽取（自动化）
- 提示词：`ontology/extraction_prompt.md`
- 抽取目标：实体类型、关系类型、数值阈值、约束条件
### 2.2 归并（自动化）
### 2.3 审核（人工，最小化）
- 日志：`ontology/review_log.csv`
- **关键指标：人工介入率 = 人工修改条数 / AI 提议条数**
### 2.4 一致性校验

## 3. 与行业标准体系对齐
- 映射表：`ontology/standards_mapping.csv`
- 对齐对象：<!-- 指南目录 / 国标 / 行业规范 -->

## 4. 持续动态更新（可进化）
| 机制 | 实现 |
|---|---|
| 增量触发 | 新文档入库自动抽取 |
| 变更提案 | 差异化对比 → 待审提案 |
| 人工闸门 | 一键确认/驳回 |
| 版本发布 | ontology/versions/vX.Y.ttl |
| 历史可复现 | 结论记录所依赖的本体版本 |
| 回滚 | |

## 5. 效率对比（证明"半自动化"的价值）
| 方式 | 构建耗时 | 人工介入 | 覆盖实体类型 |
|---|---|---|---|
| 纯人工 | | | |
| 纯自动 | | | 噪声高 |
| 本方案 | | | |
"""

FILES["ontology/schema.ttl"] = """# TODO: 领域本体定义（实体类型 / 关系类型 / 数值约束）
# 示例骨架，请按所选行业替换
@prefix : <http://example.org/ontology#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

:Entity a owl:Class .
# --- 实体类型 ---
# :Disease   a owl:Class ; rdfs:subClassOf :Entity .
# :Drug      a owl:Class ; rdfs:subClassOf :Entity .
# :Indicator a owl:Class ; rdfs:subClassOf :Entity .
# :Clause    a owl:Class ; rdfs:subClassOf :Entity .
# :Policy    a owl:Class ; rdfs:subClassOf :Entity .

# --- 关系类型 ---
# :contraindicatedFor  a owl:ObjectProperty .
# :requiresReductionWhen a owl:ObjectProperty .
# :basisClause a owl:ObjectProperty .
# :revisedBy a owl:ObjectProperty .

# --- 数值约束（数值比较推理的关键）---
# :thresholdValue a owl:DatatypeProperty .
"""

FILES["ontology/extraction_prompt.md"] = """# 本体候选抽取提示词

> 用途：让 LLM 从领域文档中抽取候选实体与关系，作为"半自动化"的自动化环节。

## 角色
你是领域知识工程师，负责从下方文档片段中抽取知识图谱的候选实体与关系。

## 输入
- 文档片段：`{chunk_text}`
- 来源元数据：`{file} / 第 {page} 页 / 章节 {section}`
- 现有本体（用于复用，避免造新词）：`{existing_schema}`

## 输出（严格 JSON）
```json
{
  "entities": [
    {"name": "", "type": "", "aliases": [], "attributes": {}, "evidence": "原文片段"}
  ],
  "relations": [
    {"head": "", "relation": "", "tail": "", "condition": "", "evidence": "原文片段"}
  ],
  "numeric_constraints": [
    {"subject": "", "operator": ">=|<=|>|<|==", "value": 0, "unit": "", "evidence": ""}
  ],
  "schema_suggestions": [
    {"action": "add_type|add_relation", "name": "", "reason": ""}
  ],
  "confidence": 0.0
}
```

## 硬性约束
1. **禁止编造**：每个实体/关系必须给出原文 evidence，无法定位则不输出。
2. **优先复用**：能用现有本体类型就不要新建。
3. 数值必须带单位与出处页码。
4. 矛盾表述单独放 `conflicts` 字段，不要自行裁决。
"""

FILES["ontology/review_log.csv"] = """proposal_id,timestamp,item_type,name,ai_proposal,human_decision,human_edit,reviewer,reason
P0001,,entity,,,accepted,,,
P0002,,relation,,,edited,,,
P0003,,entity,,,merged,,,
"""

FILES["ontology/standards_mapping.csv"] = """本方案类目,标准/规范名称,标准版本,对应章节/条款号,对齐说明,差异处理
,,,,
"""

FILES["ontology/versions/.gitkeep"] = ""

FILES["pipeline/ingest.py"] = '''# -*- coding: utf-8 -*-
"""多模态数据资产统一识别入口：文件 → 带元数据的 chunk 列表。

设计要点（评委关注）：每个 chunk 必须携带 file / page / section / type，
否则"决策链路可溯源"无法实现。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from pathlib import Path


@dataclass
class Chunk:
    chunk_id: str
    text: str
    meta: dict = field(default_factory=dict)
    # meta 约定字段: file, page, section, type(text|table|figure), asset_tags


def _make_id(source: str, page: int, offset: int, text: str) -> str:
    raw = f"{source}|{page}|{offset}|{text[:64]}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def ingest_text(path: Path, page: int = 1, section: str = "") -> list[Chunk]:
    """纯文本 / 已抽好文字层的 PDF → chunk。"""
    chunks: list[Chunk] = []
    for offset, para in enumerate(_split_paragraphs(path.read_text(encoding="utf-8"))):
        chunks.append(
            Chunk(
                chunk_id=_make_id(str(path), page, offset, para),
                text=para,
                meta={"file": path.name, "page": page, "section": section, "type": "text"},
            )
        )
    return chunks


def _split_paragraphs(text: str, max_len: int = 800) -> list[str]:
    paras, buf = [], ""
    for line in text.splitlines():
        if not line.strip():
            if buf.strip():
                paras.append(buf.strip())
            buf = ""
            continue
        buf += line + "\\n"
        if len(buf) >= max_len:
            paras.append(buf.strip())
            buf = ""
    if buf.strip():
        paras.append(buf.strip())
    return paras


def ingest_pdf(path: Path) -> list[Chunk]:
    """TODO: PDF 文字层抽取（pdfplumber / PyMuPDF），扫描件走 ocr.py。"""
    raise NotImplementedError


def ingest_table(path: Path) -> list[Chunk]:
    """TODO: XLSX/CSV → 结构化 chunk，表格需保留表头语义。"""
    raise NotImplementedError


def ingest_image(path: Path) -> list[Chunk]:
    """TODO: 图表/流程图 → 多模态模型生成结构化描述。"""
    raise NotImplementedError


def ingest_dir(root: Path, out: Path) -> None:
    """批量处理目录并按 JSONL 落盘，供 graph_builder 与知识库导入使用。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            try:
                if path.suffix.lower() in {".txt", ".md"}:
                    chunks = ingest_text(path)
                elif path.suffix.lower() == ".pdf":
                    chunks = ingest_pdf(path)
                elif path.suffix.lower() in {".xlsx", ".csv"}:
                    chunks = ingest_table(path)
                elif path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
                    chunks = ingest_image(path)
                else:
                    continue
            except NotImplementedError:
                print(f"[skip] 未实现: {path.name}")
                continue
            for c in chunks:
                f.write(json.dumps(asdict(c), ensure_ascii=False) + "\\n")
                n += 1
    print(f"写出 {n} 个 chunk -> {out}")


if __name__ == "__main__":
    ingest_dir(Path("data/raw"), Path("data/processed/chunks.jsonl"))
'''

FILES["pipeline/ocr.py"] = '''# -*- coding: utf-8 -*-
"""扫描件 OCR。要求：输出必须回填页码，供溯源使用。"""


def ocr_pdf(path: str, lang: str = "chi_sim+eng") -> list[dict]:
    """TODO: 方案 A PaddleOCR（中文表格强）；方案 B RapidOCR；方案 C 云端 OCR。

    Returns:
        [{"page": 1, "text": "...", "conf": 0.93}]
    """
    raise NotImplementedError
'''

FILES["pipeline/table_parser.py"] = '''# -*- coding: utf-8 -*-
"""表格结构还原。表格是多模态里最容易被做丢的部分，也是数值推理的前提。"""


def parse_table(path: str) -> list[dict]:
    """TODO: 还原为 {page, caption, headers, rows}，并把每行转成可检索文本。"""
    raise NotImplementedError


def table_to_chunks(table: dict, file_name: str) -> list[dict]:
    """表格 → chunk：每行生成"表头: 值"的句子化文本，便于检索与图抽取。"""
    chunks = []
    headers = table.get("headers", [])
    for i, row in enumerate(table.get("rows", [])):
        sentence = "；".join(f"{h}: {v}" for h, v in zip(headers, row) if v not in (None, ""))
        chunks.append(
            {
                "chunk_id": f"{file_name}-t{i}",
                "text": f"[表格] {table.get('caption', '')} {sentence}",
                "meta": {"file": file_name, "page": table.get("page", 1), "type": "table"},
            }
        )
    return chunks
'''

FILES["pipeline/graph_builder.py"] = '''# -*- coding: utf-8 -*-
"""chunk → 知识图谱。原则：图上每一条边都必须能指回 (file, page)。"""
from __future__ import annotations

import json
from pathlib import Path


def load_chunks(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def extract_candidates(chunk: dict, schema_path: Path, llm) -> dict:
    """按 ontology/extraction_prompt.md 调用 LLM 抽取候选实体/关系。

    llm: 任意 OpenAI 兼容客户端；开发期可用本地模型，正式期可切华为云 MaaS。
    """
    prompt = schema_path.read_text(encoding="utf-8")
    # TODO: 拼接 chunk 与现有本体，调用 LLM，解析 JSON，校验 evidence 可定位
    raise NotImplementedError


def build_graph(chunks: list[dict], out_path: Path) -> None:
    """TODO: 写入图存储（Neo4j / 轻量属性图 / 关系型三元组表均可，重点是能多跳）。"""
    raise NotImplementedError


def traverse(seed: str, hops: int = 3) -> list[dict]:
    """多跳遍历 —— 赛题"跨文档多跳推理"的核心算子。返回路径及每条边的出处。"""
    raise NotImplementedError
'''

FILES["mcp_servers/kg_query/server.py"] = '''# -*- coding: utf-8 -*-
"""MCP 工具：知识图谱多跳查询。

这是"检索-推理双驱动"里"图检索"的那条腿，也是和朴素 RAG 拉开差距的关键工具。
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("kg-query")


@mcp.tool()
def find_entities(keyword: str, entity_type: str = "", limit: int = 10) -> list[dict]:
    """按关键词/类型查找实体节点。"""
    raise NotImplementedError


@mcp.tool()
def traverse_relations(start_entity: str, relation: str = "", hops: int = 2) -> list[dict]:
    """从起始实体出发做多跳关系遍历。

    Returns:
        [{"path": [n1, r1, n2, ...], "evidence": [{"file": "", "page": 0, "text": ""}]}]
    """
    raise NotImplementedError


@mcp.tool()
def compare_threshold(subject: str, operator: str, value: float, unit: str = "") -> list[dict]:
    """数值阈值比较，例如 eGFR=40 命中哪些"需减量/禁忌"条款。"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
'''

FILES["mcp_servers/standards_lookup/server.py"] = '''# -*- coding: utf-8 -*-
"""MCP 工具：行业规范/标准条款检索与版本校验（对应"与标准体系对齐"）。"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("standards-lookup")


@mcp.tool()
def lookup_clause(keyword: str, standard: str = "", version: str = "") -> list[dict]:
    """检索标准条款，返回条款号 + 原文 + 版本。"""
    raise NotImplementedError


@mcp.tool()
def check_alignment(class_name: str) -> dict:
    """检查某个本体类目是否已对齐到标准体系（读 ontology/standards_mapping.csv）。"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
'''

FILES["mcp_servers/calc/server.py"] = '''# -*- coding: utf-8 -*-
"""MCP 工具：领域数值计算（剂量/额度/评分等）。推理链里"不能靠模型心算"的部分。"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("domain-calc")


@mcp.tool()
def compute(expression: str) -> dict:
    """安全表达式计算，返回结果与计算过程。"""
    raise NotImplementedError


if __name__ == "__main__":
    mcp.run()
'''

FILES["skills/multi_hop_qa/SKILL.md"] = """# Skill: 跨文档多跳问答

## 用途
对需要跨 ≥2 份文档、≥2 跳关系才能回答的问题，产出**带完整推理链与引用**的答案。

## 输入
- `question`：用户问题
- `max_hops`：最大跳数（默认 3）

## 执行流程
1. **问题解析**：识别问题中的实体、数值、约束条件
2. **检索（双驱动之一）**：向量检索 + `standards_lookup` 取候选证据
3. **图遍历（双驱动之二）**：`kg_query.traverse_relations` 沿本体关系走 N 跳
4. **数值推理**：`kg_query.compare_threshold` / `calc.compute`
5. **冲突检测**：多份文档阈值不一致时标注矛盾，不自行裁决
6. **证据汇总与生成**：每个结论必须挂引用
7. **溯源输出**：见 `trace_report`

## 输出格式
```json
{
  "answer": "",
  "reasoning_chain": [{"step": 1, "action": "", "result": "", "citation": {"file": "", "page": 0}}],
  "citations": [],
  "conflicts": [],
  "confidence": 0.0,
  "insufficient": false
}
```

## 拒绝策略
证据不足时必须 `"insufficient": true` 并说明缺失哪类信息，**禁止编造**。
"""

FILES["skills/conflict_detect/SKILL.md"] = """# Skill: 条款冲突检测

## 用途
同一事实在多份文档中表述不一致时（如说明书阈值 45 vs 指南阈值 40），显式标注冲突。

## 为什么这是加分点
多数参赛作品只做"检索+生成"，冲突检测能直接证明你的系统**理解了知识**而不是**匹配了文本**。

## 执行流程
1. 抽取同一实体/关系的多条候选陈述
2. 归一化（单位、术语、版本）
3. 比对数值与逻辑
4. 输出冲突清单 + 各自出处 + 建议采信依据（版本新旧 / 效力层级）

## 输出
| 冲突项 | 陈述A(出处) | 陈述B(出处) | 建议 |
|---|---|---|---|
"""

FILES["skills/trace_report/SKILL.md"] = """# Skill: 决策链路溯源报告生成

## 用途
把推理过程渲染成人类可审计的报告（"决策链路可溯源"的最终交付形态）。

## 输出
1. **结论**
2. **推理链图**：每步动作 → 结果 → 出处（文件 + 页码 + 原文片段）
3. **引用清单**
4. **冲突与不确定性提示**
5. **所依赖的本体版本 / 知识库快照版本** ← 保证旧结论可复现（"可进化"的证据）
"""

FILES["eval/dataset.jsonl"] = """{"id":"Q001","question":"","answer":"","citations":[{"file":"","page":0}],"hops":2,"type":"multi_hop","notes":""}
{"id":"Q002","question":"","answer":"","citations":[],"hops":2,"type":"numeric","notes":""}
{"id":"Q003","question":"","answer":"","citations":[],"hops":1,"type":"insufficient_evidence","notes":"考察拒答"}
"""

FILES["eval/baseline_rag.py"] = '''# -*- coding: utf-8 -*-
"""朴素 RAG 基线。作用：给评委一个"我们比普通做法强多少"的对照。

设计：单跳向量检索 + 一次生成，无图谱、无多跳、无引用回填。
"""
from __future__ import annotations


def build_index(chunks_path: str) -> None:
    """TODO: 建向量索引（本地可用 sentence-transformers / 云端用 MaaS embedding）。"""
    raise NotImplementedError


def answer(question: str, top_k: int = 5) -> dict:
    """TODO: 检索 top_k 段 → 拼 prompt → 生成。不返回引用。"""
    raise NotImplementedError


def run_eval(dataset_path: str) -> dict:
    """TODO: 跑全量评测集，返回 {"accuracy": ..., "citation_hit": ...}。"""
    raise NotImplementedError
'''

FILES["eval/report.md"] = """# 效果评测报告

## 1. 评测集构建
- 规模：N 题（多跳 / 数值 / 拒答 各占比例）
- 构建方法：<!-- 人工出题 + 标注标准答案与出处；说明如何避免"自己出题自己答对"的偏差 -->
- 数据来源与脱敏说明：<!-- 附加分：真实脱敏行业数据集 -->

## 2. 评测指标
| 指标 | 定义 | 朴素 RAG | 本方案 |
|---|---|---|---|
| 答案准确率 | 与标准答案语义一致 | | |
| 溯源命中率 | 引用文件+页码正确 | | |
| 平均跳数 | 推理链长度 | 1 | |
| 拒答正确率 | 证据不足时是否拒答 | | |
| 冲突检出率 | 真冲突被标出 | 0 | |

## 3. 消融实验
| 配置 | 准确率 | 说明 |
|---|---|---|
| 去掉图谱（仅向量） | | 证明图谱的价值 |
| 去掉多跳（限 1 跳） | | 证明多跳的价值 |
| 去掉引用回填 | | 证明溯源的价值 |

## 4. 多行业迁移验证（附加分）
| 行业 | 迁移改动 | 耗时 | 准确率 |
|---|---|---|---|
| 主行业 | — | — | |
| 迁移行业 | 仅换数据与本体 | TODO | |

## 5. 结论
"""

FILES["demo/README.md"] = """# 可视化 Demo 页面

## 必须展示的三件事（对应评委关注点）
1. **多跳推理过程可见**：逐步展开推理链，而不是只给一段话
2. **引用可点开**：点击引用能看到原文档对应页的原文片段
3. **本体/图谱可视化**：让评委"看见"知识网，而不是听你描述

## 实现方式（三选一）
- **A（最快）**：拆解 Nexent 复刻出独立前端，调 Nexent 北向 API
- **B（最稳）**：Gradio / Streamlit 单页，本地起服务
- **C（最好看）**：Vue/React 前端 + 图可视化（Cytoscape.js / AntV G6）

## 部署（决赛要求可在线访问）
```bash
# TODO
```

> 注意：决赛组委会有权复现你的 Demo，务必准备离线兜底录屏。
"""

FILES["deploy/docker-compose.yml"] = """# TODO: 若对 Nexent 官方 deployment 有定制（额外挂载自研 MCP 服务等），在此声明。
# 基础启动仍推荐使用官方方式：
#   git clone https://github.com/ModelEngine-Group/nexent.git && cd nexent && bash deploy.sh docker
version: "3.8"
services: {}
"""

FILES["deploy/agent_config_export/README.md"] = """# 智能体配置导出

**这是初赛必交材料**（赛题要求"附上需要同步提交的 json 文件"）。

## 每次改完配置必做
1. 在 Nexent 界面导出智能体 / 工作流 json
2. 放到本目录，命名：`agent_<名称>_v<版本>.json`
3. 提交 Git

## 清单
| 文件 | 内容 | 导出时间 |
|---|---|---|
| | 智能体配置 | |
| | MCP 工具配置 | |
| | 知识库清单 | |
"""

FILES["data/README.md"] = """# 数据目录

- `raw/` 原始数据（**不要提交有版权/涉密风险的文件**，用脱敏样本或提供获取脚本）
- `processed/` 处理后数据（chunks.jsonl 等）

## 数据合规（参赛须知第 ⑧ 条）
不得侵犯他人隐私；真实数据必须脱敏。建议：
1. 优先用公开数据（行业标准、公开指南、公开年报、公开数据集）
2. 若用合作单位数据，须取得书面授权并存档
3. 提交前跑一遍脱敏检查（姓名/身份证/手机号/病历号）
"""

FILES[".gitignore"] = """__pycache__/
*.py[cod]
.venv/
venv/
.env
.env.local
node_modules/
dist/
build/
data/raw/*
!data/raw/.gitkeep
data/processed/*
!data/processed/.gitkeep
*.log
.DS_Store
.idea/
.vscode/
"""

FILES["LICENSE"] = """MIT License

Copyright (c) 2026 <你的队伍名>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

for rel, content in FILES.items():
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    print(f"wrote {rel}")

print(f"\n共写出 {len(FILES)} 个文件 -> {ROOT}")
