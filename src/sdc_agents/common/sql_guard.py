"""Read-only enforcement for agent-supplied SQL.

Two layers, both required:

1. ``check_read_only_query`` parses the statement (comments and quoted text
   removed) and accepts exactly one ``SELECT`` or ``WITH ... SELECT``
   statement. It rejects stacked statements, data-modifying keywords anywhere
   in the statement (CTE writes, ``SELECT INTO``, ``FOR UPDATE``), and a short
   list of side-effect functions. It is an allowlist, not a prefix denylist.
2. ``apply_read_only_session`` makes the database connection itself
   read-only before the query runs (SQLite ``query_only``, PostgreSQL and
   MySQL read-only transactions) and sets a statement timeout. The caller
   always rolls back. Dialects with no known read-only setting are refused.

Neither layer replaces a least-privilege database role. Point SQL datasources
at a role that can only ``SELECT`` the tables the agents need.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_REJECT_PREFIX = "Write operations are not allowed. Only a single SELECT query is permitted."

# Statements must start with one of these keywords.
_ALLOWED_FIRST = {"SELECT", "WITH"}

# Keywords that never belong in a read-only query, wherever they appear.
# REPLACE and SET are deliberately absent: REPLACE() is a common string
# function and SET appears in MySQL "CHARACTER SET". Statements that start
# with them are already refused by the first-keyword rule.
_FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "UPSERT",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "ATTACH",
    "DETACH",
    "PRAGMA",
    "COPY",
    "CALL",
    "EXEC",
    "EXECUTE",
    "INTO",
    "LOCK",
    "VACUUM",
    "REINDEX",
    "LOAD",
    "OUTFILE",
    "DUMPFILE",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT",
}

# Functions with side effects outside the transaction, or that read the
# server's file system. Defence in depth: the read-only transaction blocks
# most of these, but not all (e.g. pg_terminate_backend, pg_read_file).
_FORBIDDEN_FUNCTIONS = {
    # PostgreSQL
    "nextval",
    "setval",
    "lo_import",
    "lo_export",
    "lo_unlink",
    "lo_from_bytea",
    "lo_put",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_advisory_lock",
    "pg_advisory_xact_lock",
    "pg_try_advisory_lock",
    "pg_try_advisory_xact_lock",
    "pg_notify",
    "pg_sleep",
    "set_config",
    "dblink",
    "dblink_exec",
    "dblink_connect",
    "query_to_xml",
    # SQLite
    "load_extension",
    "writefile",
    "readfile",
    "edit",
    # MySQL
    "load_file",
    "sleep",
    "benchmark",
    "get_lock",
    "sys_exec",
    "sys_eval",
}


@dataclass
class _Scan:
    words: list[str] = field(default_factory=list)  # upper-cased bare words, in order
    calls: list[str] = field(default_factory=list)  # lower-cased bare words followed by "("
    semicolons: list[int] = field(default_factory=list)  # indexes into ``words`` at each ";"
    first_token: str = ""  # first non-paren token, upper-cased


def _scan(sql: str, dialect: str) -> _Scan:
    """Tokenise ``sql`` outside comments, string literals and quoted identifiers.

    Where databases disagree on what is a comment or a quote, the scanner
    either takes the reading that hides nothing or refuses the query. Text the
    scanner skips must be text every supported database also skips; otherwise
    a call could run unseen. Raises PermissionError on an unterminated or
    ambiguous comment or quote.
    """
    out = _Scan()
    i, n = 0, len(sql)
    pending_word: str | None = None
    # The last name seen, bare or quoted, with only whitespace or comments
    # since. A "(" after it makes it a function call.
    last_name: str | None = None

    def flush_word() -> None:
        nonlocal pending_word, last_name
        if pending_word is None:
            return
        out.words.append(pending_word.upper())
        if not out.first_token:
            out.first_token = pending_word.upper()
        last_name = pending_word.lower()
        pending_word = None

    while i < n:
        c = sql[i]

        # Comments
        # "--" opens a comment only before whitespace in MySQL ("1--1" is
        # arithmetic there), so anything else is refused as ambiguous. "#" is
        # a MySQL comment but an operator in PostgreSQL: it isn't skipped, so
        # the rest of the line is still checked.
        if c == "-" and sql.startswith("--", i):
            flush_word()
            if i + 2 < n and not sql[i + 2].isspace():
                raise PermissionError(f"{_REJECT_PREFIX} Put a space after '--' in comments.")
            j = sql.find("\n", i)
            i = n if j == -1 else j + 1
            continue
        if c == "/" and sql.startswith("/*", i):
            flush_word()
            j = sql.find("*/", i + 2)
            if j == -1:
                raise PermissionError(f"{_REJECT_PREFIX} Unterminated comment.")
            # MySQL executes /*! ... */ as code: refuse rather than skip it.
            if sql.startswith("/*!", i) or sql.startswith("/*+", i):
                raise PermissionError(f"{_REJECT_PREFIX} Executable comments are not allowed.")
            i = j + 2
            continue

        # Quoted text: string literals and quoted identifiers are skipped whole.
        if c in ("'", '"', "`"):
            j = i + 1
            while True:
                j = sql.find(c, j)
                if j == -1:
                    raise PermissionError(f"{_REJECT_PREFIX} Unterminated quoted text.")
                if _backslash_escaped(sql, i + 1, j):
                    # MySQL reads \' as an escaped quote, PostgreSQL as the end
                    # of the string. Either reading could hide code.
                    raise PermissionError(
                        f"{_REJECT_PREFIX} A backslash before a closing quote is ambiguous."
                    )
                if j + 1 < n and sql[j + 1] == c:  # doubled quote escapes itself
                    j += 2
                    continue
                break
            flush_word()
            if not out.first_token:
                out.first_token = "<QUOTED>"
            # A quoted identifier can name a function: "nextval"('s').
            last_name = sql[i + 1 : j].replace(c + c, c).lower() if c != "'" else None
            i = j + 1
            continue
        # Dollar quotes exist only in PostgreSQL; elsewhere "$" is a word character.
        if c == "$" and pending_word is None and dialect == "postgresql":
            tag_end = _dollar_tag_end(sql, i)
            if tag_end is not None:
                tag = sql[i : tag_end + 1]
                j = sql.find(tag, tag_end + 1)
                if j == -1:
                    raise PermissionError(f"{_REJECT_PREFIX} Unterminated quoted text.")
                last_name = None
                i = j + len(tag)
                continue

        if (
            c.isalnum()
            or c == "_"
            or (c == "$" and (pending_word is not None or dialect != "postgresql"))
        ):
            pending_word = (pending_word or "") + c
            i += 1
            continue

        # Any other character ends a word.
        flush_word()
        if c == "(" and last_name is not None:
            out.calls.append(last_name)
        if not c.isspace():
            last_name = None
        if c == ";":
            out.semicolons.append(len(out.words))
        elif c != "(" and not c.isspace() and not out.first_token:
            out.first_token = c
        i += 1

    flush_word()
    return out


def _backslash_escaped(sql: str, start: int, quote_pos: int) -> bool:
    """True if the quote at ``quote_pos`` is preceded by an odd run of backslashes."""
    k = quote_pos - 1
    count = 0
    while k >= start and sql[k] == "\\":
        count += 1
        k -= 1
    return count % 2 == 1


def _dollar_tag_end(sql: str, i: int) -> int | None:
    """If ``sql[i]`` opens a PostgreSQL dollar quote ($$ or $tag$), return the closing $ index."""
    j = i + 1
    while j < len(sql) and (sql[j].isalnum() or sql[j] == "_"):
        j += 1
    if j < len(sql) and sql[j] == "$" and not sql[i + 1 : j][:1].isdigit():
        return j
    return None


def check_read_only_query(query: str, dialect: str = "") -> None:
    """Raise PermissionError unless ``query`` is a single read-only SELECT.

    Accepted: one ``SELECT`` or ``WITH ... SELECT`` statement, optionally
    wrapped in parentheses, with at most one trailing semicolon.
    ``dialect`` is the SQLAlchemy backend name; it decides whether
    PostgreSQL dollar quotes are recognised.
    """
    if not query or not query.strip():
        raise PermissionError(f"{_REJECT_PREFIX} Empty query.")

    scan = _scan(query, dialect)

    # One statement only: a single semicolon is allowed, and only at the end.
    if len(scan.semicolons) > 1 or (scan.semicolons and scan.semicolons[0] != len(scan.words)):
        raise PermissionError(f"{_REJECT_PREFIX} Multiple statements are not allowed.")

    if scan.first_token not in _ALLOWED_FIRST:
        raise PermissionError(
            f"{_REJECT_PREFIX} Statement starts with '{scan.first_token or '?'}'. "
            f"Rejected query: {query[:100]}"
        )

    bad_words = sorted(set(scan.words) & _FORBIDDEN_KEYWORDS)
    if bad_words:
        raise PermissionError(
            f"{_REJECT_PREFIX} Found {', '.join(bad_words)}. "
            "(Quote an identifier with that name if it is a column or table.) "
            f"Rejected query: {query[:100]}"
        )

    bad_calls = sorted(set(scan.calls) & _FORBIDDEN_FUNCTIONS)
    if bad_calls:
        raise PermissionError(
            f"{_REJECT_PREFIX} Function not allowed: {', '.join(bad_calls)}. "
            f"Rejected query: {query[:100]}"
        )


def read_only_session_statements(
    dialect: str, timeout_seconds: int, read_only_role: bool = False
) -> list[str]:
    """SQL to run on a fresh connection, before the query, to make it read-only.

    Raises PermissionError for dialects with no known read-only setting, so
    an unrecognised database fails closed instead of running unguarded,
    unless the operator has declared ``read_only_role`` for the datasource.
    """
    ms = max(1, int(timeout_seconds)) * 1000
    if dialect == "sqlite":
        # query_only refuses every write to the database files. It can't be
        # turned off from the query: PRAGMA is a forbidden keyword above.
        return ["PRAGMA query_only = ON"]
    if dialect == "postgresql":
        # First statements of the transaction SQLAlchemy opens implicitly.
        return ["SET TRANSACTION READ ONLY", f"SET LOCAL statement_timeout = {ms}"]
    if dialect in ("mysql", "mariadb"):
        # Session settings apply to the transaction the query itself starts.
        # max_execution_time is MySQL; MariaDB ignores it with a warning.
        return [
            "SET SESSION TRANSACTION READ ONLY",
            f"SET SESSION max_execution_time = {ms}",
        ]
    if read_only_role:
        # The operator has stated the role can only read; the parser still runs.
        return []
    raise PermissionError(
        f"Read-only enforcement is not implemented for the '{dialect}' dialect, "
        "so SQL queries against it are refused. Supported: sqlite, postgresql, mysql, "
        "mariadb. For other databases, connect with a role that can only read and set "
        "read_only_role: true on the datasource."
    )


async def apply_read_only_session(
    conn, timeout_seconds: int, read_only_role: bool = False
) -> None:
    """Run ``read_only_session_statements`` on an open SQLAlchemy AsyncConnection."""
    import sqlalchemy

    stmts = read_only_session_statements(conn.dialect.name, timeout_seconds, read_only_role)
    for stmt in stmts:
        await conn.execute(sqlalchemy.text(stmt))
