"""
Overlord11 - Database Tool
===========================
SQLite-backed persistent structured storage. Create tables, insert/update/delete
rows, run arbitrary SELECT queries, and manage schemas — all without leaving
the tool suite.

Actions:
  create_table  – Define a new table with typed columns.
  insert        – Insert one or more rows into a table.
  select        – Run a SELECT query (supports WHERE, ORDER BY, LIMIT).
  update        – Update rows matching a condition.
  delete        – Delete rows matching a condition.
  execute       – Run a raw SQL statement (use with caution).
  schema        – List tables and their column definitions.
  drop_table    – Delete a table and all its data.
  count         – Count rows in a table.

Usage (CLI):
    python database_tool.py --db data.db --action schema
    python database_tool.py --db data.db --action create_table --table users --columns 'id INTEGER PRIMARY KEY,name TEXT,email TEXT'
    python database_tool.py --db data.db --action insert --table users --row '{"name":"Alice","email":"alice@example.com"}'
    python database_tool.py --db data.db --action select --table users --where 'name = "Alice"'
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _connect(db_path: str) -> tuple:
    """Open a SQLite connection and return (conn, cursor) or raise."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn, conn.cursor()


def database_tool(
    action: str,
    db: str = "data.db",
    table: Optional[str] = None,
    columns: Optional[str] = None,
    row: Optional[Any] = None,
    rows: Optional[List[dict]] = None,
    where: Optional[str] = None,
    set_values: Optional[Dict[str, Any]] = None,
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
    sql: Optional[str] = None,
    params: Optional[list] = None,
    if_not_exists: bool = True,
) -> dict:
    """
    SQLite-backed persistent database operations.

    Args:
        action:       Operation: create_table, insert, select, update, delete,
                      execute, schema, drop_table, count.
        db:           Path to the SQLite database file. Created if it does not exist.
        table:        Table name to operate on.
        columns:      Comma-separated column definitions for create_table
                      (e.g., 'id INTEGER PRIMARY KEY, name TEXT NOT NULL').
        row:          Dict of column→value pairs for insert. Mutually exclusive with rows.
        rows:         List of row dicts for bulk insert.
        where:        SQL WHERE clause (without 'WHERE' keyword) for select/update/delete.
        set_values:   Dict of column→value pairs for update action.
        order_by:     ORDER BY clause for select (e.g., 'created_at DESC').
        limit:        Maximum rows to return for select.
        sql:          Raw SQL for execute action.
        params:       Positional parameters for execute action's parameterized query.
        if_not_exists: Use IF NOT EXISTS for create_table. Defaults to True.

    Returns:
        dict with keys:
            status       – "success" or "error"
            action       – action performed
            db           – database file path
            rows         – query results as list of dicts (select)
            row_count    – affected/returned row count
            last_insert_id – row ID of last insert
            tables       – list of table schemas (schema action)
            error        – error message (on failure)
            hint         – corrective action (on failure)
    """
    valid_actions = ("create_table", "insert", "select", "update", "delete",
                     "execute", "schema", "drop_table", "count")
    if action not in valid_actions:
        return {
            "status": "error",
            "action": action,
            "error": f"Unknown action: '{action}'",
            "hint": f"Use one of: {', '.join(valid_actions)}",
        }

    try:
        conn, cur = _connect(db)
    except Exception as exc:
        return {
            "status": "error",
            "action": action,
            "db": db,
            "error": f"Cannot open database: {exc}",
            "hint": "Check that the directory for the db path is writable.",
        }

    def _err(msg: str, hint: str = "") -> dict:
        conn.close()
        return {"status": "error", "action": action, "db": db, "error": msg, "hint": hint}

    try:
        # ── schema ─────────────────────────────────────────────────────────
        if action == "schema":
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            table_names = [r[0] for r in cur.fetchall()]
            tables = []
            for tname in table_names:
                cur.execute(f"PRAGMA table_info({tname})")
                cols = [{"cid": r[0], "name": r[1], "type": r[2],
                         "not_null": bool(r[3]), "default": r[4], "pk": bool(r[5])}
                        for r in cur.fetchall()]
                tables.append({"table": tname, "columns": cols, "column_count": len(cols)})
            conn.close()
            return {
                "status": "success",
                "action": "schema",
                "db": db,
                "table_count": len(tables),
                "tables": tables,
            }

        # ── create_table ───────────────────────────────────────────────────
        if action == "create_table":
            if not table:
                return _err("'table' is required for create_table",
                            "Provide the table name in the 'table' parameter.")
            if not columns:
                return _err("'columns' is required for create_table",
                            "Provide column definitions, e.g., 'id INTEGER PRIMARY KEY, name TEXT'")
            exists_clause = "IF NOT EXISTS " if if_not_exists else ""
            sql_stmt = f"CREATE TABLE {exists_clause}{table} ({columns})"
            cur.execute(sql_stmt)
            conn.commit()
            # Read back schema
            cur.execute(f"PRAGMA table_info({table})")
            col_info = [{"name": r[1], "type": r[2], "pk": bool(r[5])} for r in cur.fetchall()]
            conn.close()
            return {
                "status": "success",
                "action": "create_table",
                "db": db,
                "table": table,
                "columns": col_info,
            }

        # ── drop_table ─────────────────────────────────────────────────────
        if action == "drop_table":
            if not table:
                return _err("'table' is required for drop_table",
                            "Provide the table name in the 'table' parameter.")
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            conn.commit()
            conn.close()
            return {"status": "success", "action": "drop_table", "db": db, "table": table}

        # ── insert ─────────────────────────────────────────────────────────
        if action == "insert":
            if not table:
                return _err("'table' is required for insert",
                            "Provide the table name in the 'table' parameter.")
            insert_rows = []
            if rows:
                insert_rows = rows
            elif row:
                insert_rows = [row] if isinstance(row, dict) else row
            else:
                return _err("'row' or 'rows' is required for insert",
                            "Provide row data as a dict in 'row' or list of dicts in 'rows'.")

            if not insert_rows:
                return _err("No rows provided to insert", "Provide at least one row dict.")

            # Use first row to determine columns
            col_names = list(insert_rows[0].keys())
            placeholders = ", ".join("?" for _ in col_names)
            col_list = ", ".join(col_names)
            stmt = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"

            last_id = None
            for r in insert_rows:
                values = [r.get(c) for c in col_names]
                cur.execute(stmt, values)
                last_id = cur.lastrowid

            conn.commit()
            conn.close()
            return {
                "status": "success",
                "action": "insert",
                "db": db,
                "table": table,
                "row_count": len(insert_rows),
                "last_insert_id": last_id,
            }

        # ── select ─────────────────────────────────────────────────────────
        if action in ("select", "count"):
            if not table:
                return _err(f"'table' is required for {action}",
                            "Provide the table name in the 'table' parameter.")
            if action == "count":
                sql_stmt = f"SELECT COUNT(*) as count FROM {table}"
            else:
                sql_stmt = f"SELECT * FROM {table}"

            if where:
                sql_stmt += f" WHERE {where}"
            if order_by and action == "select":
                sql_stmt += f" ORDER BY {order_by}"
            if limit and action == "select":
                sql_stmt += f" LIMIT {int(limit)}"

            cur.execute(sql_stmt)
            result_rows = [dict(r) for r in cur.fetchall()]
            conn.close()

            if action == "count":
                return {
                    "status": "success",
                    "action": "count",
                    "db": db,
                    "table": table,
                    "where": where,
                    "count": result_rows[0]["count"] if result_rows else 0,
                }
            return {
                "status": "success",
                "action": "select",
                "db": db,
                "table": table,
                "where": where,
                "row_count": len(result_rows),
                "rows": result_rows,
            }

        # ── update ─────────────────────────────────────────────────────────
        if action == "update":
            if not table:
                return _err("'table' is required for update",
                            "Provide the table name.")
            if not set_values:
                return _err("'set_values' is required for update",
                            "Provide column-value pairs to update in 'set_values'.")
            set_clause = ", ".join(f"{k} = ?" for k in set_values.keys())
            values = list(set_values.values())
            sql_stmt = f"UPDATE {table} SET {set_clause}"
            if where:
                sql_stmt += f" WHERE {where}"
                values_final = values
            else:
                values_final = values
            cur.execute(sql_stmt, values_final)
            affected = cur.rowcount
            conn.commit()
            conn.close()
            return {
                "status": "success",
                "action": "update",
                "db": db,
                "table": table,
                "where": where,
                "rows_affected": affected,
            }

        # ── delete ─────────────────────────────────────────────────────────
        if action == "delete":
            if not table:
                return _err("'table' is required for delete",
                            "Provide the table name.")
            sql_stmt = f"DELETE FROM {table}"
            if where:
                sql_stmt += f" WHERE {where}"
            cur.execute(sql_stmt)
            affected = cur.rowcount
            conn.commit()
            conn.close()
            return {
                "status": "success",
                "action": "delete",
                "db": db,
                "table": table,
                "where": where,
                "rows_deleted": affected,
            }

        # ── execute ────────────────────────────────────────────────────────
        if action == "execute":
            if not sql:
                return _err("'sql' is required for execute",
                            "Provide a raw SQL statement in the 'sql' parameter.")
            exec_params = params or []
            cur.execute(sql, exec_params)
            if cur.description:
                result_rows = [dict(r) for r in cur.fetchall()]
                conn.commit()
                conn.close()
                return {
                    "status": "success",
                    "action": "execute",
                    "db": db,
                    "sql": sql,
                    "row_count": len(result_rows),
                    "rows": result_rows,
                }
            else:
                affected = cur.rowcount
                conn.commit()
                conn.close()
                return {
                    "status": "success",
                    "action": "execute",
                    "db": db,
                    "sql": sql,
                    "rows_affected": affected,
                }

    except sqlite3.OperationalError as exc:
        conn.close()
        return {
            "status": "error",
            "action": action,
            "db": db,
            "error": f"SQL error: {exc}",
            "hint": "Check table name, column names, and SQL syntax. Use schema action to inspect the database.",
        }
    except sqlite3.IntegrityError as exc:
        conn.close()
        return {
            "status": "error",
            "action": action,
            "db": db,
            "error": f"Integrity constraint violation: {exc}",
            "hint": "Check for duplicate primary keys, NOT NULL violations, or foreign key mismatches.",
        }
    except Exception as exc:
        try:
            conn.close()
        except Exception:
            pass
        return {
            "status": "error",
            "action": action,
            "db": db,
            "error": f"Unexpected error: {exc}",
            "hint": "Inspect the error and retry with corrected parameters.",
        }

    return {"status": "error", "action": action, "error": "Internal error"}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Overlord11 Database Tool")
    parser.add_argument("--action", required=True,
                        choices=["create_table", "insert", "select", "update",
                                 "delete", "execute", "schema", "drop_table", "count"])
    parser.add_argument("--db", default="data.db", help="SQLite database file path")
    parser.add_argument("--table", default=None)
    parser.add_argument("--columns", default=None, help="Column definitions for create_table")
    parser.add_argument("--row", default=None, help="JSON dict for single row insert")
    parser.add_argument("--rows", default=None, help="JSON array of dicts for bulk insert")
    parser.add_argument("--where", default=None, help="SQL WHERE clause (no 'WHERE' keyword)")
    parser.add_argument("--set_values", default=None, help="JSON dict of columns to update")
    parser.add_argument("--order_by", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sql", default=None, help="Raw SQL for execute action")
    parser.add_argument("--params", default=None, help="JSON array of params for execute")
    parser.add_argument("--if_not_exists", default="true", help="Add IF NOT EXISTS clause (true/false). Default: true.")

    args = parser.parse_args()

    def _json_or_none(s, name):
        if s is None:
            return None
        try:
            return json.loads(s)
        except json.JSONDecodeError as exc:
            print(json.dumps({"status": "error", "error": f"Invalid JSON for {name}: {exc}"}), flush=True)
            sys.exit(1)

    result = database_tool(
        action=args.action,
        db=args.db,
        table=args.table,
        columns=args.columns,
        row=_json_or_none(args.row, "--row"),
        rows=_json_or_none(args.rows, "--rows"),
        where=args.where,
        set_values=_json_or_none(args.set_values, "--set_values"),
        order_by=args.order_by,
        limit=args.limit,
        sql=args.sql,
        params=_json_or_none(args.params, "--params"),
        if_not_exists=args.if_not_exists.lower() != "false",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    sys.exit(0 if result.get("status") == "success" else 1)


if __name__ == "__main__":
    main()
