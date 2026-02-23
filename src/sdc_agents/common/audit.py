"""Append-only JSONL audit logger for SDC Agent tool invocations.

Every tool call is logged with agent, tool, sanitized inputs/outputs,
timestamp, and duration. Sensitive keys are redacted automatically.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal

_SENSITIVE_KEY_FRAGMENTS = {"connection", "token", "key", "password", "secret"}


class AuditLogger:
    """Append-only audit logger writing JSONL records."""

    def __init__(self, path: str | Path, log_level: Literal["standard", "verbose"] = "standard"):
        self._path = Path(path)
        self._log_level = log_level
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def log(
        self,
        *,
        agent: str,
        tool: str,
        inputs: Dict[str, Any],
        outputs: Any,
        start_time: float,
    ) -> None:
        """Write a single audit record.

        Args:
            agent: Name of the agent that invoked the tool.
            tool: Name of the tool function.
            inputs: Tool input arguments (will be sanitized).
            outputs: Tool return value (will be sanitized/summarized).
            start_time: ``time.monotonic()`` value captured before tool execution.
        """
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": agent,
            "tool": tool,
            "inputs": self._sanitize(inputs),
            "outputs": self._process_outputs(outputs),
            "duration_ms": duration_ms,
        }
        line = json.dumps(record, default=str) + "\n"
        with open(self._path, "a") as f:
            f.write(line)

    def _sanitize(self, obj: Any) -> Any:
        """Redact values for keys containing sensitive fragments."""
        if isinstance(obj, dict):
            return {
                k: "***REDACTED***" if self._is_sensitive_key(k) else self._sanitize(v)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [self._sanitize(item) for item in obj]
        return obj

    def _is_sensitive_key(self, key: str) -> bool:
        """Check if a key name contains any sensitive fragment."""
        lower = key.lower()
        return any(frag in lower for frag in _SENSITIVE_KEY_FRAGMENTS)

    def _process_outputs(self, outputs: Any) -> Any:
        """Sanitize and optionally summarize outputs based on log level."""
        sanitized = self._sanitize(outputs)
        if self._log_level == "verbose":
            return sanitized
        return self._summarize(sanitized)

    def _summarize(self, obj: Any) -> Any:
        """Reduce outputs to counts for standard log level."""
        if isinstance(obj, list):
            return {"_type": "list", "_count": len(obj)}
        if isinstance(obj, dict):
            return {"_type": "dict", "_keys": list(obj.keys())}
        if isinstance(obj, str) and len(obj) > 200:
            return {"_type": "str", "_length": len(obj)}
        return obj
