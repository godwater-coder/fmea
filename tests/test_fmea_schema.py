import sys
import unittest
from pathlib import Path
import types

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

fake_langchain_community = types.ModuleType("langchain_community")
fake_vectorstores = types.ModuleType("langchain_community.vectorstores")
fake_graphs = types.ModuleType("langchain_community.graphs")


class _FakeNeo4jVector:
    pass


class _FakeNeo4jGraph:
    pass


fake_vectorstores.Neo4jVector = _FakeNeo4jVector
fake_graphs.Neo4jGraph = _FakeNeo4jGraph
fake_langchain_community.vectorstores = fake_vectorstores
fake_langchain_community.graphs = fake_graphs
sys.modules.setdefault("langchain_community", fake_langchain_community)
sys.modules.setdefault("langchain_community.vectorstores", fake_vectorstores)
sys.modules.setdefault("langchain_community.graphs", fake_graphs)

from kg_rag_core.fmea_schema import PROJECT_SCHEMA_VERSION, normalize_to_project_schema  # noqa: E402


class FmeaSchemaTests(unittest.TestCase):
    def test_standard_table_maps_to_project_schema(self):
        df = pd.DataFrame(
            [
                {
                    "FMEA编号": "1",
                    "产品": "电池包",
                    "分析层级": "系统",
                    "项目/功能": "动力电池",
                    "潜在失效模式": "单体电压过低",
                    "潜在失效后果": "影响用户使用",
                    "严酷度(S)": 7,
                    "潜在失效原因/机理": "单节电池容量降低或损坏",
                    "发生度(O)": 4,
                    "现行预防控制": "设定标准值",
                    "现行探测控制": "万用表测量",
                    "可探测度(D)": 6,
                    "措施优先级(AP)": "H",
                    "建议措施": "更换电压过低电池",
                    "措施状态": "进行中",
                    "措施结果": "待验证",
                    "备注": "样例",
                }
            ]
        )

        out = normalize_to_project_schema(
            df,
            source_file="/tmp/fmea.csv",
            dataset_id="ds1",
            project_id="proj1",
            domain="battery",
            import_batch_id="batch1",
        )

        row = out.iloc[0].to_dict()
        self.assertEqual(row["ProcessStep"], "动力电池")
        self.assertEqual(row["FailureMode"], "单体电压过低")
        self.assertEqual(row["RecommendedAction"], "更换电压过低电池")
        self.assertEqual(row["TempMeasure"], "更换电压过低电池")
        self.assertEqual(row["RPN"], 168)
        self.assertEqual(row["Domain"], "battery")
        self.assertEqual(row["DatasetID"], "ds1")
        self.assertEqual(row["ProjectID"], "proj1")
        self.assertEqual(row["SchemaVersion"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(row["SourceFile"], "fmea.csv")
        self.assertEqual(row["SourceRowNo"], 2)

    def test_process_step_is_forward_filled(self):
        df = pd.DataFrame(
            [
                {"项目/功能": "高压箱", "潜在失效模式": "漏电"},
                {"项目/功能": None, "潜在失效模式": "高压带电"},
            ]
        )

        out = normalize_to_project_schema(df)
        self.assertEqual(out.iloc[0]["ProcessStep"], "高压箱")
        self.assertEqual(out.iloc[1]["ProcessStep"], "高压箱")


if __name__ == "__main__":
    unittest.main()
