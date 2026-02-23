"""Configuration loading and validation for SDC Agents.

Loads YAML config with ${VAR} environment variable substitution.
Fails closed: missing env vars raise KeyError immediately.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Literal, Optional

import yaml
from pydantic import BaseModel, Field

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env_vars(value: str) -> str:
    """Replace ${VAR} placeholders with environment variable values.

    Raises KeyError if an environment variable is not set (fail closed).
    """

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ[var_name]  # KeyError if missing — intentional

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _walk_and_substitute(obj: object) -> object:
    """Recursively substitute env vars in strings within nested dicts/lists."""
    if isinstance(obj, str):
        return _substitute_env_vars(obj)
    if isinstance(obj, dict):
        return {k: _walk_and_substitute(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_substitute(item) for item in obj]
    return obj


class SDCStudioConfig(BaseModel):
    """SDCStudio API connection settings."""

    base_url: str = "https://sdcstudio.example.com"


class CacheConfig(BaseModel):
    """Local cache settings."""

    root: str = ".sdc-cache"
    ttl_hours: int = 24


class AuditConfig(BaseModel):
    """Audit logging settings."""

    path: str = ".sdc-cache/audit.jsonl"
    log_level: Literal["standard", "verbose"] = "standard"


class DatasourceConfig(BaseModel):
    """A single datasource definition."""

    type: Literal["sql", "csv", "json", "mongodb"]
    connection_string: Optional[str] = None
    path: Optional[str] = None


class OutputConfig(BaseModel):
    """Output generation settings."""

    directory: str = "./output"
    formats: list[str] = Field(default_factory=lambda: ["xml"])


class SDCAgentsConfig(BaseModel):
    """Top-level configuration for SDC Agents."""

    sdcstudio: SDCStudioConfig = Field(default_factory=SDCStudioConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    datasources: Dict[str, DatasourceConfig] = Field(default_factory=dict)
    output: OutputConfig = Field(default_factory=OutputConfig)


def load_config(path: str | Path) -> SDCAgentsConfig:
    """Load and validate configuration from a YAML file.

    Environment variables in ${VAR} syntax are substituted before validation.
    Missing environment variables cause an immediate KeyError (fail closed).

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated SDCAgentsConfig instance.

    Raises:
        FileNotFoundError: If the config file doesn't exist.
        KeyError: If a referenced environment variable is not set.
    """
    raw = Path(path).read_text()
    data = yaml.safe_load(raw)
    substituted = _walk_and_substitute(data)
    return SDCAgentsConfig.model_validate(substituted)
