"""F-A: introspect_sql is read-only by construction, not by accident.

Replays the bypass cases from the 4.5.1 read-only assessment through the real
toolset against a file-backed SQLite database, then checks each layer on its
own: the statement parser, and the read-only connection beneath it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from sdc_agents.common import sql_guard
from sdc_agents.common.config import SDCAgentsConfig
from sdc_agents.common.sql_guard import check_read_only_query, read_only_session_statements
from sdc_agents.toolsets import introspect as introspect_mod
from sdc_agents.toolsets.introspect import IntrospectToolset


@pytest.fixture
async def db(tmp_path: Path) -> Path:
    path = tmp_path / "source.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)"))
        await conn.execute(sqlalchemy.text("INSERT INTO t (v) VALUES ('a'), ('b')"))
    await engine.dispose()
    return path


@pytest.fixture
def toolset(tmp_path: Path, db: Path) -> IntrospectToolset:
    config = SDCAgentsConfig(
        cache={"root": str(tmp_path / ".sdc-cache")},
        audit={"path": str(tmp_path / ".sdc-cache" / "audit.jsonl"), "log_level": "verbose"},
        datasources={
            "src": {"type": "sql", "connection_string": f"sqlite+aiosqlite:///{db}"},
        },
    )
    return IntrospectToolset(config=config)


async def _snapshot(db: Path) -> dict:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
    async with engine.connect() as conn:
        rows = (await conn.execute(sqlalchemy.text("SELECT id, v FROM t ORDER BY id"))).all()
        tables = (
            await conn.execute(
                sqlalchemy.text("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            )
        ).all()
        user_version = (await conn.execute(sqlalchemy.text("PRAGMA user_version"))).scalar()
    await engine.dispose()
    return {"rows": [tuple(r) for r in rows], "tables": [r[0] for r in tables], "uv": user_version}


# --- The assessment's cases, through the real tool ---------------------------

ASSESSMENT_CASES = [
    "/*x*/ UPDATE t SET v='z'",
    "-- c\nDELETE FROM t",
    "WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x",
    "SELECT 1; DROP TABLE t",
    "SELECT 1; CREATE TABLE evil (x INT)",
    "SELECT 1; INSERT INTO t (v) VALUES ('x')",
    "ATTACH DATABASE '{attach}' AS a",
    "PRAGMA user_version = 42",
    "\n\t  UPDATE t SET v='z'",
    "InSeRt INTO t (v) VALUES ('x')",
]


@pytest.mark.parametrize("query", ASSESSMENT_CASES)
async def test_assessment_bypasses_are_refused_and_change_nothing(
    toolset: IntrospectToolset, db: Path, tmp_path: Path, query: str
):
    attach = tmp_path / "attached.db"
    before = await _snapshot(db)
    with pytest.raises(PermissionError, match="Write operations are not allowed"):
        await toolset.introspect_sql("src", query.format(attach=attach))
    assert await _snapshot(db) == before
    assert not attach.exists()


async def test_plain_select_still_works(toolset: IntrospectToolset):
    rows = await toolset.introspect_sql("src", "SELECT id, v FROM t ORDER BY id")
    assert rows == [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]


# --- Layer 2 on its own: the connection refuses writes ----------------------


async def test_connection_is_read_only_even_if_the_parser_is_bypassed(
    toolset: IntrospectToolset, db: Path, tmp_path: Path, monkeypatch
):
    """With the parser disabled, SQLite query_only still blocks the write."""
    monkeypatch.setattr(introspect_mod, "check_read_only_query", lambda q, d="": None)
    before = await _snapshot(db)
    for q in ("UPDATE t SET v = 'z'", "DELETE FROM t", "CREATE TABLE evil (x INT)"):
        with pytest.raises(Exception, match="readonly|read-only|query_only|attempt to write"):
            await toolset.introspect_sql("src", q)
    with pytest.raises(Exception):
        await toolset.introspect_sql("src", "PRAGMA user_version = 42")
    assert await _snapshot(db) == before


def test_session_statements_per_dialect():
    assert read_only_session_statements("sqlite", 30) == ["PRAGMA query_only = ON"]
    assert read_only_session_statements("postgresql", 30) == [
        "SET TRANSACTION READ ONLY",
        "SET LOCAL statement_timeout = 30000",
    ]
    assert read_only_session_statements("mysql", 5) == [
        "SET SESSION TRANSACTION READ ONLY",
        "SET SESSION max_execution_time = 5000",
    ]


@pytest.mark.parametrize("dialect", ["mssql", "oracle", "snowflake", ""])
def test_unknown_dialect_fails_closed(dialect):
    with pytest.raises(PermissionError, match="not implemented"):
        read_only_session_statements(dialect, 30)


def test_unknown_dialect_runs_only_with_a_declared_read_only_role():
    assert read_only_session_statements("mssql", 30, read_only_role=True) == []
    # Known dialects keep their session settings either way.
    assert read_only_session_statements("sqlite", 30, read_only_role=True) == [
        "PRAGMA query_only = ON"
    ]


def test_timeout_must_be_positive():
    with pytest.raises(ValueError):
        SDCAgentsConfig(datasources={"x": {"type": "sql", "query_timeout_seconds": 0}})


# --- Layer 1 on its own: the parser ------------------------------------------

ACCEPTED = [
    "SELECT * FROM t",
    "select id from t;",
    "  SELECT 1  ;  ",
    "(SELECT id FROM t) UNION (SELECT id FROM t)",
    "WITH x AS (SELECT * FROM t) SELECT * FROM x",
    "SELECT REPLACE(v, 'a', 'b') FROM t",
    "SELECT 'DROP TABLE t; DELETE FROM t' AS s",
    'SELECT "update", "insert" FROM t',
    "SELECT `delete` FROM t",
    "SELECT 1 -- trailing comment with DELETE in it",
    "SELECT /* INSERT */ 1",
    "SELECT CAST(v AS CHAR CHARACTER SET utf8) FROM t",
    "SELECT 'it''s' AS s",
    "SELECT count (*) FROM t",
    'SELECT "nextval" FROM t',
    "SELECT 'a\\\\' AS s",
    "SELECT * FROM t WHERE v LIKE 'a\\_b'",
]


@pytest.mark.parametrize("query", ACCEPTED)
def test_parser_accepts_read_only_selects(query):
    check_read_only_query(query, "sqlite")


REJECTED = [
    # not a SELECT
    "UPDATE t SET v = 1",
    "EXPLAIN ANALYZE DELETE FROM t",
    "VALUES (1)",
    "ATTACH DATABASE 'x.db' AS a",
    "PRAGMA writable_schema = 1",
    "SET ROLE admin",
    # stacked
    "SELECT 1; SELECT 2",
    "SELECT 1;; ",
    "SELECT 1; -- \nDROP TABLE t",
    # writes hidden inside a SELECT
    "WITH x AS (UPDATE t SET v='z' RETURNING *) SELECT * FROM x",
    "WITH x AS (INSERT INTO t (v) VALUES ('x') RETURNING *) SELECT * FROM x",
    "SELECT * INTO evil FROM t",
    "SELECT * FROM t FOR UPDATE",
    "SELECT * FROM t INTO OUTFILE '/tmp/x'",
    # side-effect functions
    "SELECT nextval('s')",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_terminate_backend (123)",
    "SELECT load_extension('evil')",
    "SELECT LOAD_FILE('/etc/passwd')",
    "SELECT set_config('x', 'y', false)",
    "SELECT nextval/**/('s')",
    "SELECT nextval -- c\n('s')",
    "SELECT \"nextval\"('s')",
    "SELECT pg_catalog.pg_read_file('/etc/passwd')",
    # MySQL: \' escapes the quote, so the call below sits outside any string there
    "SELECT 'a\\'', load_file('/etc/passwd') -- '",
    # ambiguous or hidden text
    "SELECT 'a\\' , pg_read_file('/etc/passwd') , '",
    "SELECT 1--1, load_file('/etc/passwd')",
    "SELECT /*! 1; DROP TABLE t */ 1",
    "SELECT /* unterminated",
    "SELECT 'unterminated",
    "",
    "   ",
]


@pytest.mark.parametrize("query", REJECTED)
def test_parser_rejects(query):
    with pytest.raises(PermissionError, match="Write operations are not allowed"):
        check_read_only_query(query, "postgresql")


def test_dollar_quotes_hide_nothing_outside_postgresql():
    """In MySQL $a$ is an identifier, so a call between two of them is seen."""
    q = "SELECT $a$, load_file('/etc/passwd'), $a$"
    with pytest.raises(PermissionError):
        check_read_only_query(q, "mysql")
    # In PostgreSQL the same text is one dollar-quoted string.
    check_read_only_query("SELECT $a$ load_file('x') $a$", "postgresql")


def test_hash_is_not_treated_as_a_comment():
    """'#' is XOR in PostgreSQL, so the rest of the line must still be checked."""
    with pytest.raises(PermissionError):
        check_read_only_query("SELECT 1 # 1, pg_read_file('/etc/passwd')", "postgresql")


def test_no_prefix_regex_left():
    """The 4.5.1 denylist regex is gone; enforcement lives in sql_guard."""
    assert not hasattr(introspect_mod, "_WRITE_PATTERN")
    assert sql_guard.check_read_only_query is introspect_mod.check_read_only_query
