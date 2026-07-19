# -*- coding: utf-8 -*-

"""FMEA 核心迁移入口。

用于把现有的 FMEA KG/RAG 核心暴露为一个更清晰的模块名，
便于后续把业务逻辑从旧的 kg_rag_core 目录迁移到统一的 fmea_core 包。
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
CODE_DIR = ROOT / "code"
for _path in (str(ROOT), str(CODE_DIR)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from kg_rag_core import KGRAGService, Neo4JRepository, _as_problem, _json_response

__all__ = [
    "KGRAGService",
    "Neo4JRepository",
    "_as_problem",
    "_json_response",
]
