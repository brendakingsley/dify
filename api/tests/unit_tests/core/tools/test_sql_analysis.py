"""Unit tests for the SQL logic checker tool.

These tests validate each static analysis check against representative SQL
patterns, including the IoT-card UNION ALL and LEFT JOIN scenarios from the
problem statement.
"""

import sys
import os

import pytest

# ---------------------------------------------------------------------------
# Bootstrap: import only the pure-logic functions from the tool without
# pulling in the full Dify framework (BuiltinTool, ToolInvokeMessage, etc.).
# ---------------------------------------------------------------------------
import importlib.util
import types

# Build a minimal stub for the Dify modules the tool tries to import
_stub = types.ModuleType

for mod_path in [
    "core",
    "core.tools",
    "core.tools.builtin_tool",
    "core.tools.builtin_tool.tool",
    "core.tools.entities",
    "core.tools.entities.tool_entities",
]:
    if mod_path not in sys.modules:
        sys.modules[mod_path] = _stub(mod_path)

# Provide the BuiltinTool and ToolInvokeMessage stubs
sys.modules["core.tools.builtin_tool.tool"].BuiltinTool = object
sys.modules["core.tools.entities.tool_entities"].ToolInvokeMessage = object

# Now import the module under test
_tool_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "../../../../core/tools/builtin_tool/providers/sql_analysis/tools/check_sql_logic.py",
)
spec = importlib.util.spec_from_file_location("check_sql_logic", _tool_path)
_mod = importlib.util.module_from_spec(spec)
# Register the module before exec so @dataclass can resolve __module__
sys.modules["check_sql_logic"] = _mod
spec.loader.exec_module(_mod)

check_left_join_arithmetic = _mod.check_left_join_arithmetic
check_union_all_same_table = _mod.check_union_all_same_table
check_row_number_ties = _mod.check_row_number_ties
check_left_join_unfiltered = _mod.check_left_join_unfiltered
check_count_column_vs_star = _mod.check_count_column_vs_star
check_select_arithmetic_null_guard = _mod.check_select_arithmetic_null_guard
_format_report = _mod._format_report

NULL_FUNC = "NVL(expr, 0)"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

IOT_SQL = """
SELECT A.VCMSISDN, A.IMSI, A.IMEI,
       B.CARD2_IMEI AS OTHER_IMEI,
       B.CARD2_USR_IMSI AS OTHER_IMSI
FROM TEMP_IOT_TURN_OFF_2000_PICI_1 A
LEFT JOIN TEMP_HBB_HEARTBEAT_DETAIL B
       ON A.IMSI = B.CARD1_USR_IMSI AND A.IMEI = B.CARD1_IMEI
UNION ALL
SELECT A.VCMSISDN, A.IMSI, A.IMEI,
       B.CARD1_IMEI AS OTHER_IMEI,
       B.CARD1_USR_IMSI AS OTHER_IMSI
FROM TEMP_IOT_TURN_OFF_2000_PICI_1 A
LEFT JOIN TEMP_HBB_HEARTBEAT_DETAIL B
       ON A.IMSI = B.CARD2_USR_IMSI AND A.IMEI = B.CARD2_IMEI;
"""

FINAL_JOIN_SQL = """
SELECT A.VCMSISDN, A.IMSI, A.IMEI, A.OTHER_IMSI, A.INSERT_CNT,
       B.USR_NBR, B.PROV_CD, B.CITY_CD
FROM TEMP_HBB_OTHER_SLOT_IMSI_INSERT_RANK_DATA A
LEFT JOIN TEMP_HBB_OTHER_SLOT_IMSI_ROAM_IN_DETAIL B ON A.OTHER_IMSI = B.IMSI;
"""

RANK_SQL = """
SELECT A.VCMSISDN, A.IMSI, A.IMEI, A.OTHER_IMSI, A.INSERT_CNT
FROM (
  SELECT VCMSISDN, IMSI, IMEI, OTHER_IMSI, INSERT_CNT,
         ROW_NUMBER() OVER(PARTITION BY VCMSISDN,IMSI,IMEI ORDER BY INSERT_CNT DESC) AS RN
  FROM TEMP_HBB_OTHER_SLOT_IMSI_INSERT_COUNT_DATA
) A WHERE A.RN = 1;
"""

COUNT_SQL = "SELECT COUNT(USR_NBR) FROM TEMP_HBB_OTHER_SLOT_IMSI_INSERT_RANK_DATA;"

CLEAN_SQL = """
SELECT MONTH, USR_ID, NVL(SUM(TAXED_FEE), 0) AS TAXED_FEE
FROM JCFW.TW_PERS_BILL_USR_CH_PRDCT_M_FS
WHERE MONTH BETWEEN 202601 AND 202603
GROUP BY MONTH, USR_ID;
"""

# ---------------------------------------------------------------------------
# Tests: check_union_all_same_table
# ---------------------------------------------------------------------------

class TestUnionAllSameTable:
    def test_detects_same_base_table_in_union_all(self):
        issues = check_union_all_same_table(IOT_SQL)
        codes = [i.code for i in issues]
        assert "UA001" in codes

    def test_no_false_positive_on_different_tables(self):
        sql = "SELECT a FROM T1 UNION ALL SELECT b FROM T2;"
        issues = check_union_all_same_table(sql)
        assert not issues

    def test_no_false_positive_on_clean_sql(self):
        issues = check_union_all_same_table(CLEAN_SQL)
        assert not issues


# ---------------------------------------------------------------------------
# Tests: check_row_number_ties
# ---------------------------------------------------------------------------

class TestRowNumberTies:
    def test_detects_row_number_in_iot_rank_sql(self):
        issues = check_row_number_ties(RANK_SQL)
        codes = [i.code for i in issues]
        assert "RN001" in codes

    def test_no_false_positive_without_row_number(self):
        issues = check_row_number_ties(CLEAN_SQL)
        assert not issues


# ---------------------------------------------------------------------------
# Tests: check_left_join_unfiltered
# ---------------------------------------------------------------------------

class TestLeftJoinUnfiltered:
    def test_detects_unfiltered_left_join_in_final_join_sql(self):
        issues = check_left_join_unfiltered(FINAL_JOIN_SQL)
        codes = [i.code for i in issues]
        assert "LJ002" in codes

    def test_no_false_positive_when_null_filter_present(self):
        sql = """
        SELECT A.ID, B.NAME
        FROM TABLE_A A
        LEFT JOIN TABLE_B B ON A.ID = B.ID
        WHERE B.ID IS NOT NULL;
        """
        issues = check_left_join_unfiltered(sql)
        assert not issues

    def test_no_false_positive_on_clean_sql(self):
        issues = check_left_join_unfiltered(CLEAN_SQL)
        assert not issues


# ---------------------------------------------------------------------------
# Tests: check_count_column_vs_star
# ---------------------------------------------------------------------------

class TestCountColumnVsStar:
    def test_detects_count_column(self):
        issues = check_count_column_vs_star(COUNT_SQL)
        codes = [i.code for i in issues]
        assert "CT001" in codes

    def test_no_false_positive_on_count_star(self):
        sql = "SELECT COUNT(*) FROM T;"
        issues = check_count_column_vs_star(sql)
        assert not issues

    def test_no_false_positive_on_count_one(self):
        sql = "SELECT COUNT(1) FROM T;"
        issues = check_count_column_vs_star(sql)
        assert not issues


# ---------------------------------------------------------------------------
# Tests: check_left_join_arithmetic
# ---------------------------------------------------------------------------

class TestLeftJoinArithmetic:
    def test_detects_arithmetic_on_left_join_column(self):
        sql = """
        SELECT A.FEE - B.DISCOUNT AS NET_FEE
        FROM TABLE_A A
        LEFT JOIN TABLE_B B ON A.ID = B.ID;
        """
        issues = check_left_join_arithmetic(sql, NULL_FUNC)
        codes = [i.code for i in issues]
        assert "LJ001" in codes

    def test_no_issue_when_null_guard_present(self):
        sql = """
        SELECT A.FEE - NVL(B.DISCOUNT, 0) AS NET_FEE
        FROM TABLE_A A
        LEFT JOIN TABLE_B B ON A.ID = B.ID;
        """
        issues = check_left_join_arithmetic(sql, NULL_FUNC)
        assert not issues

    def test_no_issue_without_left_join(self):
        sql = """
        SELECT A.FEE - B.DISCOUNT AS NET_FEE
        FROM TABLE_A A
        INNER JOIN TABLE_B B ON A.ID = B.ID;
        """
        issues = check_left_join_arithmetic(sql, NULL_FUNC)
        assert not issues


# ---------------------------------------------------------------------------
# Tests: _format_report
# ---------------------------------------------------------------------------

class TestFormatReport:
    def test_returns_ok_message_when_no_issues(self):
        report = _format_report([], "SELECT 1;")
        assert "未发现明显逻辑问题" in report

    def test_report_contains_issue_code_and_title(self):
        issues = check_row_number_ties(RANK_SQL)
        report = _format_report(issues, RANK_SQL)
        assert "RN001" in report
        assert "ROW_NUMBER" in report


# ---------------------------------------------------------------------------
# Integration: full IoT scenario
# ---------------------------------------------------------------------------

class TestFullIoTScenario:
    """Run all checks against the complete IoT script from the problem statement."""

    FULL_SQL = IOT_SQL + FINAL_JOIN_SQL + RANK_SQL + COUNT_SQL

    def test_detects_union_all_issue(self):
        issues = check_union_all_same_table(self.FULL_SQL)
        assert any(i.code == "UA001" for i in issues)

    def test_detects_row_number_issue(self):
        issues = check_row_number_ties(self.FULL_SQL)
        assert any(i.code == "RN001" for i in issues)

    def test_detects_left_join_unfiltered_issue(self):
        issues = check_left_join_unfiltered(self.FULL_SQL)
        assert any(i.code == "LJ002" for i in issues)

    def test_detects_count_column_issue(self):
        issues = check_count_column_vs_star(self.FULL_SQL)
        assert any(i.code == "CT001" for i in issues)

    def test_total_issue_count_is_nonzero(self):
        all_issues = (
            check_left_join_arithmetic(self.FULL_SQL, NULL_FUNC)
            + check_union_all_same_table(self.FULL_SQL)
            + check_row_number_ties(self.FULL_SQL)
            + check_left_join_unfiltered(self.FULL_SQL)
            + check_count_column_vs_star(self.FULL_SQL)
        )
        assert len(all_issues) >= 3
