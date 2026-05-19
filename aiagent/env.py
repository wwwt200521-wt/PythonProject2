from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aiagent.tools.anythingllm import DEFAULT_BASE_URL


@dataclass(frozen=True)
class RuntimeConfig:
    project_root: Path
    base_url: str
    model: str
    api_key: str
    max_tokens: int
    anythingllm_key: str
    anythingllm_url: str
    max_tool_iterations: int
    restrict_filesystem_to_workspace: bool
    enable_tool_call_audit: bool
    tool_call_log_path: Path


def load_env(env_path: Path) -> dict:
    env_data = {}
    if not env_path.exists():
        raise FileNotFoundError(f"Missing .env file at: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env_data[key] = value
    return env_data


def parse_int_env(value: str | None, default: int, *, minimum: int = 1) -> int:
    if value is None or not str(value).strip():
        return default
    parsed = int(str(value).strip())
    if parsed < minimum:
        raise ValueError(f"Integer setting must be >= {minimum}")
    return parsed


def parse_bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if not normalized:
        return default
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def resolve_project_path(project_root: Path, value: str | None, default_relative_path: str) -> Path:
    raw = (value or "").strip()
    candidate = Path(raw) if raw else Path(default_relative_path)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    return candidate.expanduser().resolve()


def load_runtime_config(project_root: Path) -> RuntimeConfig:
    env_data = load_env(project_root / ".env")

    base_url = env_data.get("OPENAI_BASE_URL", "")
    model = env_data.get("OPENAI_MODEL", "")
    if not base_url or not model:
        raise ValueError("OPENAI_BASE_URL and OPENAI_MODEL are required in .env")

    return RuntimeConfig(
        project_root=project_root,
        base_url=base_url,
        model=model,
        api_key=env_data.get("OPENAI_API_KEY", ""),
        max_tokens=parse_int_env(env_data.get("OPENAI_MAX_TOKENS"), 2048, minimum=1),
        anythingllm_key=env_data.get("ANYTHINGLLMAPIKEY", ""),
        anythingllm_url=env_data.get("ANYTHINGLLM_BASE_URL", DEFAULT_BASE_URL),
        max_tool_iterations=parse_int_env(env_data.get("TOOL_CALL_MAX_ITERATIONS"), 8, minimum=1),
        restrict_filesystem_to_workspace=parse_bool_env(env_data.get("FILESYSTEM_WORKSPACE_ONLY"), True),
        enable_tool_call_audit=parse_bool_env(env_data.get("TOOL_CALL_AUDIT_ENABLED"), True),
        tool_call_log_path=resolve_project_path(
            project_root,
            env_data.get("TOOL_CALL_AUDIT_LOG_PATH"),
            "runtime/tool_calls.jsonl",
        ),
    )
