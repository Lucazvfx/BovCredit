from __future__ import annotations

from .contracts import EngineVersion

SCHEMA_VERSION = "1"
RULES_VERSION = "2026-08-10"
PARAMETERS_VERSION = "2026-08-10"
MODEL_VERSION = "2026-08-10"


def engine_version() -> dict:
    version = EngineVersion(
        rules=RULES_VERSION,
        parameters=PARAMETERS_VERSION,
        model=MODEL_VERSION,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "rules": version.rules,
        "parameters": version.parameters,
        "model": version.model,
    }
