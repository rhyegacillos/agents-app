from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
API_INDEX = ROOT / "api" / "index.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_route_paths(source: str) -> set[str]:
    return {
        path
        for _, path in re.findall(r'@app\.(get|post|delete)\("([^"]+)"', source)
        if path.startswith("/api/") or path == "/health"
    }


def _normalize_route_template(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{id}", path)


def _extract_literal_assignment(source: str, name: str) -> str:
    pattern = rf"^{name}\s*=\s*\"([^\"]+)\""
    match = re.search(pattern, source, flags=re.MULTILINE)
    assert match, f"Could not find literal assignment for {name} in api/index.py"
    return match.group(1)


def test_architecture_doc_lists_all_current_api_routes() -> None:
    api_source = _read(API_INDEX)
    architecture_text = _read(ARCHITECTURE)

    documented_routes = {_normalize_route_template(route) for route in _extract_route_paths(api_source)}

    missing = [route for route in sorted(documented_routes) if route not in architecture_text]
    assert not missing, f"ARCHITECTURE.md is missing current routes: {missing}"


def test_architecture_doc_lists_current_generation_models() -> None:
    api_source = _read(API_INDEX)
    architecture_text = _read(ARCHITECTURE)

    model_constant_names = [
        "GROK_MODEL",
        "GEMINI_MODEL",
        "OPENAI_MODEL",
        "DEEPSEEK_MODEL",
        "GROK_MODEL_FALLBACK",
        "GEMINI_MODEL_FALLBACK",
        "OPENAI_MODEL_FALLBACK",
        "DEEPSEEK_MODEL_FALLBACK",
    ]

    missing = []
    for name in model_constant_names:
        model_id = _extract_literal_assignment(api_source, name)
        if f"`{model_id}`" not in architecture_text:
            missing.append(model_id)

    assert not missing, f"ARCHITECTURE.md is missing current model IDs: {missing}"


def test_recommendation_flow_is_documented_in_readme_and_architecture() -> None:
    readme_text = _read(README)
    architecture_text = _read(ARCHITECTURE)

    assert "premium recommendation helper" in readme_text
    assert "POST /api/recommend-combination" in architecture_text
    assert "premium access" in architecture_text
    assert "input-shaping step" in architecture_text


def test_execution_plan_constraints_and_current_behavior_are_documented() -> None:
    api_source = _read(API_INDEX)
    architecture_text = _read(ARCHITECTURE)

    assert 'if scenario_profile not in {"conservative", "base", "aggressive", "all"}:' in api_source
    assert 'if finance_mode not in {"grounded_v2", "llm_v1"}:' in api_source
    assert 'if currency != "USD":' in api_source
    assert 'if region != "US":' in api_source
    assert 'selected_profile = "base" if scenario_profile == "all" else scenario_profile' in api_source

    assert "`scenario_profile` must be `conservative`, `base`, `aggressive`, or `all`" in architecture_text
    assert "`finance_mode` must be `grounded_v2` or `llm_v1`" in architecture_text
    assert "`currency` must be `USD`" in architecture_text
    assert "`region` must be `US`" in architecture_text
    assert "normalize it to `base`" in architecture_text


def test_docs_match_current_execution_plan_delivery_contract() -> None:
    readme_text = _read(README)
    architecture_text = _read(ARCHITECTURE)
    api_source = _read(API_INDEX)

    assert "/api/stakeholder-reports/{report_id}/presentation" in api_source
    assert "/api/stakeholder-reports/{report_id}/pdf" in api_source
    assert "/api/stakeholder-reports/{report_id}/email" not in api_source

    assert "execution plans currently support PDF and presentation export, but not email delivery" in readme_text
    assert "Execution-plan email delivery is not implemented" in architecture_text
    assert "`GET /api/stakeholder-reports/{id}/presentation`" in architecture_text
