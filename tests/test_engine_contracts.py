import importlib
import subprocess
import sys

import pytest

from services.engine.contracts import AnalysisContext, EngineVersion, HerdState
from services.engine.versions import engine_version


def test_herd_state_accepts_valid_ten_value_vector():
    state = HerdState(
        values=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        source="MANUAL",
        farm_id=42,
        metadata={"note": "ok"},
    )

    assert state.values == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0)
    assert state.source == "MANUAL"
    assert state.farm_id == 42
    assert dict(state.metadata) == {"note": "ok"}


@pytest.mark.parametrize(
    "values, match",
    [
        ([1, 2, 3], "exactly ten"),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, -1], "non-negative"),
        ([1, 2, 3, 4, 5, 6, 7, 8, 9, "x"], "numeric"),
    ],
)
def test_herd_state_rejects_invalid_values(values, match):
    with pytest.raises(ValueError, match=match):
        HerdState(values=values, source="MANUAL", farm_id=None, metadata={})


@pytest.mark.parametrize("source", ["MANUAL", "PDF", "EXCEL", "API"])
def test_herd_state_accepts_known_sources(source):
    state = HerdState(values=[0] * 10, source=source, farm_id=None, metadata={})

    assert state.source == source


def test_herd_state_rejects_unknown_source():
    with pytest.raises(ValueError, match="source"):
        HerdState(values=[0] * 10, source="EMAIL", farm_id=None, metadata={})


def test_contracts_are_immutable_after_construction():
    state = HerdState(values=[0] * 10, source="API", farm_id=None, metadata={})
    context = AnalysisContext(
        organization_id=1,
        user_id=2,
        input_data={"x": 1},
        source_documents=[{"kind": "pdf"}],
    )

    with pytest.raises((AttributeError, TypeError)):
        state.source = "MANUAL"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        context.input_data["x"] = 2


def test_contracts_deep_freeze_nested_mutations():
    nested_metadata = {"nested": {"items": [1, {"x": 2}]}}
    nested_input_data = {"payload": {"items": [1, {"x": 2}]}}
    nested_source_documents = [{"payload": {"items": [1, {"x": 2}]}}]

    state = HerdState(values=[0] * 10, source="API", farm_id=None, metadata=nested_metadata)
    context = AnalysisContext(
        organization_id=1,
        user_id=2,
        input_data=nested_input_data,
        source_documents=nested_source_documents,
    )

    nested_metadata["nested"]["items"].append(3)
    nested_input_data["payload"]["items"].append(3)
    nested_source_documents[0]["payload"]["items"].append(3)

    assert state.metadata["nested"]["items"] == (
        1,
        {"x": 2},
    )
    assert context.input_data["payload"]["items"] == (
        1,
        {"x": 2},
    )
    assert context.source_documents[0]["payload"]["items"] == (
        1,
        {"x": 2},
    )

    with pytest.raises(TypeError):
        state.metadata["nested"]["items"][1]["x"] = 3  # type: ignore[index]
    with pytest.raises(TypeError):
        context.input_data["payload"]["items"][1]["x"] = 3  # type: ignore[index]
    with pytest.raises(TypeError):
        context.source_documents[0]["payload"]["items"][1]["x"] = 3  # type: ignore[index]


def test_analysis_context_normalizes_nested_inputs():
    context = AnalysisContext(
        organization_id=None,
        user_id=7,
        input_data={"x": 1},
        source_documents=[{"kind": "pdf"}],
    )

    assert context.organization_id is None
    assert context.user_id == 7
    assert dict(context.input_data) == {"x": 1}
    assert len(context.source_documents) == 1
    assert dict(context.source_documents[0]) == {"kind": "pdf"}


def test_engine_version_metadata_is_stable_and_complete():
    version = engine_version()

    assert version == {
        "schema_version": "1",
        "rules": "2026-08-10",
        "parameters": "2026-08-10",
        "model": "2026-08-10",
    }


def test_engine_version_dataclass_round_trips():
    version = EngineVersion(rules="r1", parameters="p1", model="m1")

    assert version.rules == "r1"
    assert version.parameters == "p1"
    assert version.model == "m1"


def test_engine_package_imports_without_flask_or_database():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import services.engine; import sys; sys.stdout.write(','.join(services.engine.__all__))",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout == "AnalysisContext,EngineVersion,HerdState,engine_version"
