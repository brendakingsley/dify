"""SQL logic checker tool.

Performs static analysis on a SQL script and reports common issues:
  1. LEFT JOIN result used in arithmetic without NULL guard.
  2. Missing NULL guard (NVL / COALESCE / ISNULL / IFNULL) in arithmetic SELECT expressions.
  3. UNION ALL where the same source table appears in every branch (potential intent to
     deduplicate vs duplicate).
  4. ROW_NUMBER() used without a deterministic ORDER BY (tie-breaking concern).
  5. LEFT JOIN result not filtered (all rows returned even when right-side has no match).
"""

from __future__ import annotations

import re
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, Optional

from core.tools.builtin_tool.tool import BuiltinTool
from core.tools.entities.tool_entities import ToolInvokeMessage

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

# Regex patterns (case-insensitive applied via re.IGNORECASE)
_RE_LEFT_JOIN = re.compile(r"\bLEFT\s+(?:OUTER\s+)?JOIN\b", re.IGNORECASE)
_RE_ARITHMETIC = re.compile(r"[+\-*/]", re.IGNORECASE)
_RE_NULL_GUARD = re.compile(
    r"\b(?:NVL|COALESCE|ISNULL|IFNULL|NULLIF|NVL2|ZEROIFNULL)\s*\(",
    re.IGNORECASE,
)
_RE_ROW_NUMBER = re.compile(
    r"\bROW_NUMBER\s*\(\s*\)\s*OVER\s*\(.*?ORDER\s+BY\b(.*?)\)",
    re.IGNORECASE | re.DOTALL,
)
_RE_UNION_ALL = re.compile(r"\bUNION\s+ALL\b", re.IGNORECASE)
_RE_UNION_BARE = re.compile(r"\bUNION(?!\s+ALL)\b", re.IGNORECASE)
_RE_FROM_TABLE = re.compile(r"\bFROM\s+([\w.]+)", re.IGNORECASE)
_RE_JOIN_TABLE = re.compile(r"\bJOIN\s+([\w.]+)", re.IGNORECASE)
_RE_SELECT_EXPR = re.compile(
    r"\bSELECT\b(.*?)\bFROM\b", re.IGNORECASE | re.DOTALL
)
_RE_WHERE = re.compile(r"\bWHERE\b", re.IGNORECASE)
_RE_WHERE_NULL_FILTER = re.compile(
    r"\bWHERE\b.*?\bIS\s+(?:NOT\s+)?NULL\b", re.IGNORECASE | re.DOTALL
)

# NULL-guard function names per dialect
_NULL_FUNC: dict[str, str] = {
    "hive": "NVL(expr, 0)",
    "spark": "NVL(expr, 0)",
    "oracle": "NVL(expr, 0)",
    "mysql": "IFNULL(expr, 0)",
    "postgresql": "COALESCE(expr, 0)",
    "mssql": "ISNULL(expr, 0)",
}


_SQL_KEYWORDS = frozenset({
    "WHERE", "ON", "SET", "SELECT", "GROUP", "ORDER", "HAVING", "LIMIT",
    "UNION", "LEFT", "RIGHT", "INNER", "FULL", "CROSS", "JOIN", "AS",
    "AND", "OR", "NOT", "IN", "IS", "NULL", "BETWEEN", "LIKE", "CASE",
    "WHEN", "THEN", "ELSE", "END", "WITH", "BY", "OVER", "PARTITION",
})


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARNING" | "INFO"
    code: str
    title: str
    detail: str
    suggestion: str
    location: str = ""
    lines: list[int] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Analysis functions
# ──────────────────────────────────────────────────────────────────────────────

def _line_number(sql: str, pos: int) -> int:
    """Return 1-based line number for a byte offset in *sql*."""
    return sql[:pos].count("\n") + 1


def _split_statements(sql: str) -> list[str]:
    """Split on semicolons, skip empty fragments."""
    return [s.strip() for s in sql.split(";") if s.strip()]


def _extract_table_aliases(stmt: str) -> dict[str, str]:
    """Build a simple alias→table map for a single statement."""
    alias_map: dict[str, str] = {}
    pattern = re.compile(
        r"\b(?:FROM|JOIN)\s+([\w.]+)\s+(?:AS\s+)?([\w]+)",
        re.IGNORECASE,
    )
    for m in pattern.finditer(stmt):
        table, alias = m.group(1), m.group(2)
        if alias.upper() not in _SQL_KEYWORDS:
            alias_map[alias.upper()] = table.upper()
    return alias_map


def check_left_join_arithmetic(sql: str, null_func: str) -> list[Issue]:
    """Warn when a SELECT clause contains arithmetic that mixes columns from a
    LEFT-JOINed table without a NULL guard.  We check at statement level."""
    issues: list[Issue] = []
    for stmt in _split_statements(sql):
        if not _RE_LEFT_JOIN.search(stmt):
            continue
        # Extract right-side table aliases from the LEFT JOIN clauses
        right_aliases: list[str] = []
        for m in re.finditer(
            r"\bLEFT\s+(?:OUTER\s+)?JOIN\s+([\w.]+)\s+(?:AS\s+)?([\w]*)",
            stmt,
            re.IGNORECASE,
        ):
            table = m.group(1)
            raw_alias = m.group(2).strip()
            if raw_alias and raw_alias.upper() not in _SQL_KEYWORDS:
                alias = raw_alias
            else:
                alias = table.split(".")[-1]
            right_aliases.append(alias.upper())

        select_m = _RE_SELECT_EXPR.search(stmt)
        if not select_m:
            continue
        select_body = select_m.group(1)

        # Check each comma-separated expression
        for expr in select_body.split(","):
            expr_clean = expr.strip()
            if not _RE_ARITHMETIC.search(expr_clean):
                continue
            # Check if any right-side alias/column is referenced without a null guard
            for alias in right_aliases:
                pattern = re.compile(
                    r"\b" + re.escape(alias) + r"\s*\.",
                    re.IGNORECASE,
                )
                if pattern.search(expr_clean) and not _RE_NULL_GUARD.search(expr_clean):
                    issues.append(
                        Issue(
                            severity="WARNING",
                            code="LJ001",
                            title="LEFT JOIN 结果参与算术运算但缺少 NULL 保护",
                            detail=(
                                f"表达式 `{expr_clean.strip()}` 使用了 LEFT JOIN 右表 "
                                f"`{alias}` 的列进行算术运算。"
                                f"当右表无匹配行时，该列为 NULL，"
                                f"任何与 NULL 的算术运算结果仍为 NULL。"
                            ),
                            suggestion=(
                                f"将右表字段用 NULL 保护函数包裹，例如："
                                f"`{null_func}` 替换原始字段引用。"
                            ),
                        )
                    )
    return issues


def check_select_arithmetic_null_guard(sql: str, null_func: str) -> list[Issue]:
    """Detect arithmetic in SELECT lists that is not wrapped with a NULL guard."""
    issues: list[Issue] = []
    lines = sql.splitlines()
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        # Skip comment lines
        if stripped.startswith("--") or stripped.startswith("/*"):
            continue
        if not _RE_ARITHMETIC.search(stripped):
            continue
        # Only look at lines that contain column references (dot notation or plain names)
        if "." not in stripped and not re.search(r"\b[A-Z_]{2,}\b", stripped, re.IGNORECASE):
            continue
        if _RE_NULL_GUARD.search(stripped):
            continue
        # Narrow to SELECT-context lines (heuristic: contains AS or ends with comma)
        if not (re.search(r"\bAS\b", stripped, re.IGNORECASE) or stripped.endswith(",")):
            continue
        issues.append(
            Issue(
                severity="INFO",
                code="NL001",
                title="SELECT 表达式中的算术运算可能受 NULL 影响",
                detail=(
                    f"第 {lineno} 行: `{stripped}` — "
                    "表达式中包含算术运算符，若任意操作数为 NULL，"
                    "整个表达式结果将为 NULL。"
                ),
                suggestion=(
                    f"使用 {null_func} 将可能为 NULL 的字段转换为 0 后再运算，"
                    "例如：`NVL(字段名, 0)`。"
                ),
                lines=[lineno],
            )
        )
    return issues


def check_union_all_same_table(sql: str) -> list[Issue]:
    """Warn when a UNION ALL is composed of branches that all reference the same base table,
    which may cause unintentional row duplication."""
    issues: list[Issue] = []
    # Find UNION ALL blocks (simplified: split on UNION ALL)
    parts = re.split(r"\bUNION\s+ALL\b", sql, flags=re.IGNORECASE)
    if len(parts) < 2:
        return issues

    # For each consecutive pair, collect FROM tables
    for i in range(len(parts) - 1):
        left_tables = {m.group(1).upper() for m in _RE_FROM_TABLE.finditer(parts[i])}
        right_tables = {m.group(1).upper() for m in _RE_FROM_TABLE.finditer(parts[i + 1])}
        common = left_tables & right_tables
        if common:
            issues.append(
                Issue(
                    severity="INFO",
                    code="UA001",
                    title="UNION ALL 两侧引用相同的基表，可能产生重复行",
                    detail=(
                        f"UNION ALL 的相邻两段均引用了表 {sorted(common)}。"
                        "若业务目标是对同一主表按不同 JOIN 条件分别取数再合并，"
                        "请确认合并后的重复行是预期行为（计数需求），"
                        "而非本应使用 UNION（去重）。"
                    ),
                    suggestion=(
                        "若合并目的是[主卡可能在 CARD1 也可能在 CARD2]，则 UNION ALL 正确；"
                        "若任务仅关注特定卡槽（如只找第二卡槽），"
                        "请删除不相关的 UNION ALL 分支，避免数据冗余。"
                    ),
                )
            )
    return issues


def check_row_number_ties(sql: str) -> list[Issue]:
    """Warn when ROW_NUMBER() is used to select the 'top 1' record but ties are possible,
    because ROW_NUMBER arbitrarily breaks ties while RANK/DENSE_RANK may be more appropriate."""
    issues: list[Issue] = []
    # Find ROW_NUMBER OVER blocks
    pattern = re.compile(
        r"ROW_NUMBER\s*\(\s*\)\s*OVER\s*\(\s*PARTITION\s+BY\s+(.*?)\s+ORDER\s+BY\s+(.*?)\)",
        re.IGNORECASE | re.DOTALL,
    )
    for m in pattern.finditer(sql):
        order_clause = m.group(2).strip()
        # If ORDER BY is a single aggregated count column it may have ties
        issues.append(
            Issue(
                severity="INFO",
                code="RN001",
                title="ROW_NUMBER() 在存在并列值时会随机取一条",
                detail=(
                    f"ORDER BY `{order_clause}` 排序后使用 ROW_NUMBER() 取第一行。"
                    "若多个行的排序值相同（例如多个 OTHER_IMSI 的出现次数 INSERT_CNT 相同），"
                    "ROW_NUMBER() 会不确定地选取其中一条，可能遗漏同等重要的记录。"
                ),
                suggestion=(
                    "如业务需要保留所有并列最大值，请将 ROW_NUMBER() 替换为 RANK() 或 DENSE_RANK()，"
                    "然后在外层过滤 RN = 1。"
                    "若只需取一条（任意）并列记录，则 ROW_NUMBER() 可保留，但需在注释中说明。"
                ),
            )
        )
    return issues


def check_left_join_unfiltered(sql: str) -> list[Issue]:
    """Warn when a LEFT JOIN result is not filtered on the right table, causing all
    left-side rows to appear in the result even when there is no match."""
    issues: list[Issue] = []
    for stmt in _split_statements(sql):
        if not _RE_LEFT_JOIN.search(stmt):
            continue
        # If the statement has a WHERE clause that filters on IS NOT NULL or IS NULL
        # for any right-table column, it is OK
        if _RE_WHERE_NULL_FILTER.search(stmt):
            continue
        # Check whether the outer query (final SELECT) wraps a subquery with LEFT JOIN
        # and does not add a WHERE to filter the right side
        # Heuristic: if LEFT JOIN appears in the outermost SELECT and there is no
        # WHERE ... IS NOT NULL on right-table columns, raise INFO
        right_aliases_in_where: list[str] = []
        for m in re.finditer(
            r"\bLEFT\s+(?:OUTER\s+)?JOIN\s+([\w.]+)\s+(?:AS\s+)?([\w]*)",
            stmt,
            re.IGNORECASE,
        ):
            table = m.group(1)
            raw_alias = m.group(2).strip()
            if raw_alias and raw_alias.upper() not in _SQL_KEYWORDS:
                alias = raw_alias
            else:
                alias = table.split(".")[-1]
            right_aliases_in_where.append(alias.upper())

        where_m = re.search(r"\bWHERE\b(.*?)(?:GROUP\s+BY|ORDER\s+BY|HAVING|$)",
                             stmt, re.IGNORECASE | re.DOTALL)
        if not where_m:
            # No WHERE at all
            issues.append(
                Issue(
                    severity="INFO",
                    code="LJ002",
                    title="LEFT JOIN 结果未做 NULL 过滤，可能包含未匹配行",
                    detail=(
                        "使用了 LEFT JOIN 但最终结果没有对右表的关联字段做 IS NOT NULL 过滤。"
                        "这意味着即使右表中没有匹配行，左表的所有记录仍会出现在结果中，"
                        "右表字段全部为 NULL。"
                    ),
                    suggestion=(
                        "若业务目标是只保留右表有匹配的行（即确认副卡是漫入异网用户），"
                        "请将 LEFT JOIN 改为 INNER JOIN，"
                        "或在 WHERE 子句中增加 `右表别名.关联字段 IS NOT NULL`。"
                    ),
                )
            )
            continue

        where_body = where_m.group(1)
        for alias in right_aliases_in_where:
            alias_ref = re.compile(r"\b" + re.escape(alias) + r"\.", re.IGNORECASE)
            if not alias_ref.search(where_body):
                issues.append(
                    Issue(
                        severity="INFO",
                        code="LJ002",
                        title="LEFT JOIN 结果未做 NULL 过滤，可能包含未匹配行",
                        detail=(
                            f"LEFT JOIN 右表 `{alias}` 的列未出现在 WHERE 条件中。"
                            f"当右表无对应行时，`{alias}.*` 列均为 NULL，"
                            "这些行仍会保留在结果集里。"
                        ),
                        suggestion=(
                            f"若只需保留右表有匹配的行，请在 WHERE 中增加 "
                            f"`{alias}.关联字段 IS NOT NULL`，"
                            "或将 LEFT JOIN 改为 INNER JOIN。"
                        ),
                    )
                )
    return issues


def check_count_column_vs_star(sql: str) -> list[Issue]:
    """Inform when COUNT(column) is used, noting that it skips NULLs unlike COUNT(*)."""
    issues: list[Issue] = []
    pattern = re.compile(r"\bCOUNT\s*\(\s*(?!\*|\s*1\s*)([\w.]+)\s*\)", re.IGNORECASE)
    for m in pattern.finditer(sql):
        col = m.group(1)
        lineno = _line_number(sql, m.start())
        issues.append(
            Issue(
                severity="INFO",
                code="CT001",
                title="COUNT(列名) 会跳过 NULL 值",
                detail=(
                    f"第 {lineno} 行: `COUNT({col})` — "
                    f"统计的是 `{col}` 字段非 NULL 的行数，而非总行数。"
                    "若该字段存在 NULL 值，COUNT(列名) 的结果会小于 COUNT(*) 或 COUNT(1)。"
                ),
                suggestion=(
                    "若需统计总行数（包含 NULL 行），请改用 COUNT(*) 或 COUNT(1)。"
                    f"若确实只需统计非空的 `{col}`，则保留 COUNT({col}) 并在注释中说明。"
                ),
                lines=[lineno],
            )
        )
    return issues


# ──────────────────────────────────────────────────────────────────────────────
# Report formatter
# ──────────────────────────────────────────────────────────────────────────────

_SEVERITY_EMOJI = {"ERROR": "🔴", "WARNING": "🟠", "INFO": "🔵"}


def _format_report(issues: list[Issue], sql: str) -> str:
    if not issues:
        return (
            "✅ **未发现明显逻辑问题。**\n\n"
            "脚本通过了以下检查：\n"
            "- LEFT JOIN 算术运算 NULL 安全性\n"
            "- SELECT 表达式 NULL 保护\n"
            "- UNION ALL 同表重复风险\n"
            "- ROW_NUMBER 并列值处理\n"
            "- LEFT JOIN 未过滤结果行\n"
            "- COUNT(列名) vs COUNT(*)\n"
        )

    lines: list[str] = [
        f"## SQL 脚本逻辑检查报告\n",
        f"共发现 **{len(issues)}** 个潜在问题：\n",
    ]
    for i, issue in enumerate(issues, start=1):
        emoji = _SEVERITY_EMOJI.get(issue.severity, "⚪")
        lines.append(
            f"### {i}. {emoji} [{issue.severity}] {issue.code} — {issue.title}\n"
        )
        if issue.lines:
            lines.append(f"**位置：** 第 {', '.join(map(str, issue.lines))} 行\n")
        if issue.location:
            lines.append(f"**位置说明：** {issue.location}\n")
        lines.append(f"**问题描述：**\n{issue.detail}\n")
        lines.append(f"**修正建议：**\n{issue.suggestion}\n")
        lines.append("---\n")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Tool class
# ──────────────────────────────────────────────────────────────────────────────

class CheckSqlLogicTool(BuiltinTool):
    def _invoke(
        self,
        user_id: str,
        tool_parameters: dict[str, Any],
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        sql_script: str = tool_parameters.get("sql_script", "")
        dialect: str = tool_parameters.get("dialect", "hive").lower()

        if not sql_script or not sql_script.strip():
            yield self.create_text_message("❌ 请提供需要分析的 SQL 脚本。")
            return

        null_func = _NULL_FUNC.get(dialect, "NVL(expr, 0)")

        issues: list[Issue] = []
        issues.extend(check_left_join_arithmetic(sql_script, null_func))
        issues.extend(check_select_arithmetic_null_guard(sql_script, null_func))
        issues.extend(check_union_all_same_table(sql_script))
        issues.extend(check_row_number_ties(sql_script))
        issues.extend(check_left_join_unfiltered(sql_script))
        issues.extend(check_count_column_vs_star(sql_script))

        report = _format_report(issues, sql_script)
        yield self.create_text_message(report)
