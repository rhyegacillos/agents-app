import copy
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


SCENARIO_PROFILES = {
    "conservative": {
        "probability": 0.30,
        "growth_rate": 0.12,
        "arpu_multiplier": 0.9,
        "cogs_multiplier": 1.1,
        "opex_multiplier": 1.05,
        "churn_multiplier": 1.25,
    },
    "base": {
        "probability": 0.50,
        "growth_rate": 0.18,
        "arpu_multiplier": 1.0,
        "cogs_multiplier": 1.0,
        "opex_multiplier": 1.0,
        "churn_multiplier": 1.0,
    },
    "aggressive": {
        "probability": 0.20,
        "growth_rate": 0.24,
        "arpu_multiplier": 1.15,
        "cogs_multiplier": 0.93,
        "opex_multiplier": 0.98,
        "churn_multiplier": 0.85,
    },
}

ASSUMPTION_SOURCE_MAP = {
    "start_customers": "Industry benchmark proxy (launch cohort baseline, public SMB SaaS comps; refreshed 2026-02)",
    "default_arpu_monthly": "Industry benchmark proxy (pricing comps and packaging scans; refreshed 2026-02)",
    "ai_cost_per_customer_monthly": "Vendor benchmark proxy (LLM/API usage cost envelopes; refreshed 2026-02)",
    "support_cost_per_customer_monthly": "Ops benchmark proxy (support burden per active customer; refreshed 2026-02)",
    "infra_cost_per_customer_monthly": "Cloud benchmark proxy (infra unit cost per customer; refreshed 2026-02)",
}

ASSUMPTION_PACK = {
    "default": {
        "start_customers": 40,
        "default_arpu_monthly": 349.0,
        "salary_unit": "annual",
        "setup_costs": {
            "engineering": 38000.0,
            "legal_compliance": 6000.0,
            "launch_marketing": 12000.0,
            "other": 4000.0,
        },
        "salary_bands_monthly": {
            "Product Manager": 120000.0,
            "Senior Engineer": 160000.0,
            "AI Engineer": 180000.0,
            "Designer": 90000.0,
            "GTM Lead": 110000.0,
            "Customer Success": 75000.0,
        },
        "infra_cost_base_monthly": 1200.0,
        "tooling_base_monthly": 900.0,
        "sales_marketing_base_monthly": 4500.0,
        "ai_cost_per_customer_monthly": 2.8,
        "support_cost_per_customer_monthly": 1.4,
        "infra_cost_per_customer_monthly": 0.9,
        "monthly_churn_rate": 0.03,
    },
    "fintech": {
        "start_customers": 32,
        "default_arpu_monthly": 499.0,
        "salary_unit": "annual",
        "setup_costs": {
            "engineering": 42000.0,
            "legal_compliance": 10000.0,
            "launch_marketing": 14000.0,
            "other": 5000.0,
        },
        "salary_bands_monthly": {
            "Product Manager": 130000.0,
            "Senior Engineer": 175000.0,
            "AI Engineer": 195000.0,
            "Designer": 95000.0,
            "GTM Lead": 120000.0,
            "Customer Success": 85000.0,
        },
        "infra_cost_base_monthly": 1400.0,
        "tooling_base_monthly": 1100.0,
        "sales_marketing_base_monthly": 5000.0,
        "ai_cost_per_customer_monthly": 3.1,
        "support_cost_per_customer_monthly": 1.8,
        "infra_cost_per_customer_monthly": 1.1,
        "monthly_churn_rate": 0.025,
    },
    "healthtech": {
        "start_customers": 24,
        "default_arpu_monthly": 599.0,
        "salary_unit": "annual",
        "setup_costs": {
            "engineering": 44000.0,
            "legal_compliance": 12000.0,
            "launch_marketing": 13000.0,
            "other": 6000.0,
        },
        "salary_bands_monthly": {
            "Product Manager": 130000.0,
            "Senior Engineer": 180000.0,
            "AI Engineer": 205000.0,
            "Designer": 95000.0,
            "GTM Lead": 120000.0,
            "Customer Success": 90000.0,
        },
        "infra_cost_base_monthly": 1500.0,
        "tooling_base_monthly": 1200.0,
        "sales_marketing_base_monthly": 4500.0,
        "ai_cost_per_customer_monthly": 3.3,
        "support_cost_per_customer_monthly": 2.0,
        "infra_cost_per_customer_monthly": 1.2,
        "monthly_churn_rate": 0.02,
    },
    "edtech": {
        "start_customers": 55,
        "default_arpu_monthly": 179.0,
        "salary_unit": "annual",
        "setup_costs": {
            "engineering": 35000.0,
            "legal_compliance": 4000.0,
            "launch_marketing": 10000.0,
            "other": 3500.0,
        },
        "salary_bands_monthly": {
            "Product Manager": 110000.0,
            "Senior Engineer": 145000.0,
            "AI Engineer": 165000.0,
            "Designer": 85000.0,
            "GTM Lead": 100000.0,
            "Customer Success": 70000.0,
        },
        "infra_cost_base_monthly": 1000.0,
        "tooling_base_monthly": 850.0,
        "sales_marketing_base_monthly": 4200.0,
        "ai_cost_per_customer_monthly": 2.4,
        "support_cost_per_customer_monthly": 1.2,
        "infra_cost_per_customer_monthly": 0.8,
        "monthly_churn_rate": 0.035,
    },
}


def merge_assumptions(industry: str) -> Dict[str, Any]:
    key = str(industry or "").strip().lower()
    base = ASSUMPTION_PACK["default"]
    overlay = ASSUMPTION_PACK.get(key, {})
    merged = dict(base)
    for field in ("setup_costs", "salary_bands_monthly"):
        merged[field] = dict(base.get(field, {}))
        merged[field].update(overlay.get(field, {}))
    for field, value in overlay.items():
        if field in {"setup_costs", "salary_bands_monthly"}:
            continue
        merged[field] = value
    return merged


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _resolve_monthly_salary(assumptions: Dict[str, Any], salary_value: float) -> float:
    unit = str(assumptions.get("salary_unit") or "monthly").strip().lower()
    salary = float(salary_value or 0.0)
    if unit == "annual":
        return salary / 12.0
    return salary


def build_run_conditioned_assumptions(
    industry: str,
    run: Dict[str, Any],
    selected_model: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    assumptions = merge_assumptions(industry)
    constraints = {str(item or "").strip().lower() for item in (run.get("constraints") or []) if str(item or "").strip()}
    persona = str(run.get("tone") or "").strip().lower()
    output_text = f"{selected_model.get('title') or ''} {str(selected_model.get('output_html') or '')}".lower()
    confidence = _clamp_float(float(selected_model.get("confidence") or 0.62), 0.0, 1.0)

    start_mult = 1.0
    arpu_mult = 1.0
    setup_mult = 1.0
    eng_mult = 1.0
    legal_mult = 1.0
    marketing_mult = 1.0
    salary_mult = 1.0
    infra_base_mult = 1.0
    tooling_mult = 1.0
    sales_mult = 1.0
    ai_unit_mult = 1.0
    support_unit_mult = 1.0
    infra_unit_mult = 1.0
    fte_mult = 1.0
    churn_mult = 1.0
    risk_bias = 0.0
    applied_tags: List[str] = []

    if "b2c mobile app" in constraints:
        start_mult *= 1.30
        arpu_mult *= 0.72
        support_unit_mult *= 1.22
        sales_mult *= 1.20
        infra_unit_mult *= 1.15
        churn_mult *= 1.18
        risk_bias += 0.35
        applied_tags.append("b2c_mobile")
    if "b2b saas" in constraints:
        start_mult *= 0.95
        arpu_mult *= 1.08
        sales_mult *= 1.05
        applied_tags.append("b2b_saas")
    if "enterprise scale" in constraints:
        start_mult *= 0.84
        arpu_mult *= 1.18
        setup_mult *= 1.10
        legal_mult *= 1.15
        sales_mult *= 1.08
        fte_mult *= 1.10
        churn_mult *= 0.92
        risk_bias += 0.22
        applied_tags.append("enterprise_scale")
    if "low startup cost (<$5k)" in constraints:
        setup_mult *= 0.74
        salary_mult *= 0.90
        sales_mult *= 0.85
        arpu_mult *= 0.92
        applied_tags.append("low_startup_cost")
    if "bootstrapped friendly" in constraints:
        setup_mult *= 0.84
        salary_mult *= 0.90
        tooling_mult *= 0.88
        sales_mult *= 0.88
        fte_mult *= 0.82
        risk_bias += 0.08
        applied_tags.append("bootstrapped")
    if "regulated environment (hipaa, soc2, gdpr)" in constraints:
        start_mult *= 0.88
        arpu_mult *= 1.10
        legal_mult *= 1.35
        eng_mult *= 1.08
        support_unit_mult *= 1.08
        churn_mult *= 0.95
        risk_bias += 0.32
        applied_tags.append("regulated")
    if "human-in-the-loop required" in constraints:
        support_unit_mult *= 1.20
        ai_unit_mult *= 0.92
        risk_bias += 0.10
        applied_tags.append("human_in_loop")
    if "long sales cycle (6+ months)" in constraints:
        start_mult *= 0.78
        arpu_mult *= 1.08
        sales_mult *= 1.12
        churn_mult *= 0.92
        risk_bias += 0.30
        applied_tags.append("long_sales_cycle")
    if "single-person buyer (founder / manager)" in constraints:
        start_mult *= 1.08
        arpu_mult *= 0.96
        sales_mult *= 0.92
        fte_mult *= 0.90
        risk_bias -= 0.08
        applied_tags.append("single_buyer")
    if "usage-based pricing required" in constraints:
        arpu_mult *= 0.93
        start_mult *= 1.05
        ai_unit_mult *= 1.10
        infra_unit_mult *= 1.08
        risk_bias += 0.08
        applied_tags.append("usage_pricing")
    if "data cannot leave customer environment" in constraints:
        setup_mult *= 1.10
        legal_mult *= 1.12
        infra_base_mult *= 1.25
        infra_unit_mult *= 1.16
        risk_bias += 0.24
        applied_tags.append("data_residency")
    if "api-first (no ui mvp)" in constraints:
        setup_mult *= 0.94
        eng_mult *= 0.96
        support_unit_mult *= 0.90
        sales_mult *= 0.96
        applied_tags.append("api_first")
    if "legacy systems only (email, excel, pdfs)" in constraints:
        setup_mult *= 1.08
        eng_mult *= 1.10
        support_unit_mult *= 1.10
        risk_bias += 0.18
        applied_tags.append("legacy_systems")
    if "international / multi-language users" in constraints:
        setup_mult *= 1.06
        support_unit_mult *= 1.12
        sales_mult *= 1.08
        arpu_mult *= 1.04
        risk_bias += 0.10
        applied_tags.append("intl_multilang")

    if "critical vc" in persona:
        start_mult *= 0.95
        fte_mult *= 0.94
        risk_bias += 0.12
        applied_tags.append("persona_critical_vc")
    elif "optimistic visionary" in persona:
        start_mult *= 1.06
        arpu_mult *= 1.04
        fte_mult *= 1.06
        risk_bias -= 0.08
        applied_tags.append("persona_visionary")
    elif "operator" in persona:
        salary_mult *= 0.96
        support_unit_mult *= 0.96
        fte_mult *= 0.92
        risk_bias -= 0.05
        applied_tags.append("persona_operator")
    elif "compliance" in persona or "risk officer" in persona:
        legal_mult *= 1.16
        start_mult *= 0.92
        churn_mult *= 0.95
        risk_bias += 0.16
        applied_tags.append("persona_compliance")
    elif "solo founder" in persona:
        setup_mult *= 0.86
        salary_mult *= 0.88
        sales_mult *= 0.86
        fte_mult *= 0.72
        risk_bias += 0.06
        applied_tags.append("persona_solo_founder")
    elif "enterprise buyer" in persona:
        start_mult *= 0.90
        arpu_mult *= 1.12
        legal_mult *= 1.08
        churn_mult *= 0.92
        risk_bias += 0.12
        applied_tags.append("persona_enterprise_buyer")
    elif "growth marketer" in persona:
        start_mult *= 1.10
        sales_mult *= 1.15
        churn_mult *= 1.05
        risk_bias -= 0.04
        applied_tags.append("persona_growth_marketer")

    if any(token in output_text for token in ("enterprise", "procurement", "governance")):
        start_mult *= 0.95
        arpu_mult *= 1.06
        churn_mult *= 0.93
        risk_bias += 0.06
        applied_tags.append("signal_enterprise_text")
    if any(token in output_text for token in ("smb", "small business", "bootstrapped", "founder")):
        start_mult *= 1.05
        arpu_mult *= 0.95
        fte_mult *= 0.92
        risk_bias -= 0.03
        applied_tags.append("signal_smb_text")
    if any(token in output_text for token in ("compliance", "audit", "regulated", "soc2", "hipaa", "gdpr")):
        legal_mult *= 1.12
        setup_mult *= 1.04
        risk_bias += 0.09
        applied_tags.append("signal_compliance_text")
    if any(token in output_text for token in ("mobile", "consumer", "app")):
        start_mult *= 1.08
        arpu_mult *= 0.94
        support_unit_mult *= 1.07
        churn_mult *= 1.12
        applied_tags.append("signal_consumer_text")

    quality_shift = _clamp_float((confidence - 0.62) / 0.25, -0.8, 0.8)
    start_mult *= 1.0 + (0.07 * quality_shift)
    arpu_mult *= 1.0 + (0.05 * quality_shift)
    sales_mult *= 1.0 - (0.03 * quality_shift)
    risk_bias -= 0.12 * quality_shift

    start_mult = _clamp_float(start_mult, 0.55, 1.75)
    arpu_mult = _clamp_float(arpu_mult, 0.65, 1.65)
    setup_mult = _clamp_float(setup_mult, 0.70, 1.55)
    eng_mult = _clamp_float(eng_mult, 0.80, 1.40)
    legal_mult = _clamp_float(legal_mult, 0.85, 1.70)
    marketing_mult = _clamp_float(marketing_mult, 0.80, 1.45)
    salary_mult = _clamp_float(salary_mult, 0.82, 1.25)
    infra_base_mult = _clamp_float(infra_base_mult, 0.80, 1.55)
    tooling_mult = _clamp_float(tooling_mult, 0.80, 1.40)
    sales_mult = _clamp_float(sales_mult, 0.75, 1.65)
    ai_unit_mult = _clamp_float(ai_unit_mult, 0.75, 1.45)
    support_unit_mult = _clamp_float(support_unit_mult, 0.75, 1.50)
    infra_unit_mult = _clamp_float(infra_unit_mult, 0.75, 1.55)
    fte_mult = _clamp_float(fte_mult, 0.55, 1.40)
    churn_mult = _clamp_float(churn_mult, 0.70, 1.35)
    risk_bias = _clamp_float(risk_bias, -1.0, 1.0)

    setup_costs = assumptions.get("setup_costs") if isinstance(assumptions.get("setup_costs"), dict) else {}
    salary_bands = assumptions.get("salary_bands_monthly") if isinstance(assumptions.get("salary_bands_monthly"), dict) else {}
    adjusted = copy.deepcopy(assumptions)
    adjusted["start_customers"] = max(1, int(round(float(assumptions.get("start_customers") or 1.0) * start_mult)))
    adjusted["default_arpu_monthly"] = round(max(25.0, float(assumptions.get("default_arpu_monthly") or 0.0) * arpu_mult), 2)
    adjusted["setup_costs"] = {
        "engineering": round(max(0.0, float(setup_costs.get("engineering") or 0.0) * setup_mult * eng_mult), 2),
        "legal_compliance": round(max(0.0, float(setup_costs.get("legal_compliance") or 0.0) * setup_mult * legal_mult), 2),
        "launch_marketing": round(max(0.0, float(setup_costs.get("launch_marketing") or 0.0) * setup_mult * marketing_mult), 2),
        "other": round(max(0.0, float(setup_costs.get("other") or 0.0) * setup_mult), 2),
    }
    adjusted["salary_bands_monthly"] = {key: round(max(0.0, float(value or 0.0) * salary_mult), 2) for key, value in salary_bands.items()}
    adjusted["infra_cost_base_monthly"] = round(max(0.0, float(assumptions.get("infra_cost_base_monthly") or 0.0) * infra_base_mult), 2)
    adjusted["tooling_base_monthly"] = round(max(0.0, float(assumptions.get("tooling_base_monthly") or 0.0) * tooling_mult), 2)
    adjusted["sales_marketing_base_monthly"] = round(max(0.0, float(assumptions.get("sales_marketing_base_monthly") or 0.0) * sales_mult), 2)
    adjusted["ai_cost_per_customer_monthly"] = round(max(0.0, float(assumptions.get("ai_cost_per_customer_monthly") or 0.0) * ai_unit_mult), 3)
    adjusted["support_cost_per_customer_monthly"] = round(max(0.0, float(assumptions.get("support_cost_per_customer_monthly") or 0.0) * support_unit_mult), 3)
    adjusted["infra_cost_per_customer_monthly"] = round(max(0.0, float(assumptions.get("infra_cost_per_customer_monthly") or 0.0) * infra_unit_mult), 3)
    adjusted["fte_multiplier"] = round(fte_mult, 3)
    adjusted["monthly_churn_rate"] = round(
        _clamp_float(float(assumptions.get("monthly_churn_rate") or 0.03) * churn_mult, 0.005, 0.18),
        4,
    )

    conservative = _clamp_float(0.30 + (0.11 * risk_bias), 0.20, 0.46)
    aggressive = _clamp_float(0.20 - (0.09 * risk_bias), 0.10, 0.34)
    base_prob = max(0.22, 1.0 - conservative - aggressive)
    prob_total = conservative + base_prob + aggressive
    scenario_probabilities = {
        "conservative": round(conservative / prob_total, 4),
        "base": round(base_prob / prob_total, 4),
        "aggressive": round(max(0.0, 1.0 - round(conservative / prob_total, 4) - round(base_prob / prob_total, 4)), 4),
    }
    funnel_bias = _clamp_float(risk_bias * 0.18, -0.14, 0.14)
    funnel_assumptions = {
        "traffic_to_lead": round(_clamp_float(0.03 * (1.0 - 0.5 * funnel_bias), 0.015, 0.06), 4),
        "lead_to_sql": round(_clamp_float(0.20 * (1.0 - 0.8 * funnel_bias), 0.10, 0.32), 4),
        "sql_to_customer": round(_clamp_float(0.18 * (1.0 - 0.9 * funnel_bias), 0.08, 0.30), 4),
    }
    profile = {
        "selected_model_confidence": round(confidence, 3),
        "risk_bias": round(risk_bias, 3),
        "scenario_probabilities": scenario_probabilities,
        "funnel_assumptions": funnel_assumptions,
        "applied_tags": applied_tags[:12],
    }
    return adjusted, profile


def _fte_for_role(role: str, month: int, fte_multiplier: float = 1.0) -> float:
    if role == "Product Manager":
        base = 0.2 if month <= 3 else (0.35 if month <= 6 else 0.5)
    elif role == "Senior Engineer":
        base = 0.8 if month <= 6 else 1.2
    elif role == "AI Engineer":
        base = 0.5 if month <= 6 else (0.6 if month <= 9 else 0.75)
    elif role == "Designer":
        base = 0.1 if month <= 4 else 0.2
    elif role == "GTM Lead":
        base = 0.1 if month <= 6 else 0.4
    elif role == "Customer Success":
        base = 0.0 if month <= 8 else 0.3
    else:
        base = 0.2
    return round(max(0.0, base * float(fte_multiplier or 1.0)), 3)


def project_financials(
    assumptions: Dict[str, Any],
    scenario_name: str,
    horizon_months: int,
    start_customers_factor: float = 1.0,
    growth_rate_factor: float = 1.0,
    arpu_factor: float = 1.0,
    opex_factor: float = 1.0,
) -> Dict[str, Any]:
    profile = SCENARIO_PROFILES[scenario_name]
    growth_rate = float(profile["growth_rate"]) * float(growth_rate_factor)
    churn_rate = _clamp_float(
        float(assumptions.get("monthly_churn_rate") or 0.03) * float(profile.get("churn_multiplier") or 1.0),
        0.005,
        0.20,
    )
    arpu = float(assumptions["default_arpu_monthly"]) * float(profile["arpu_multiplier"]) * float(arpu_factor)
    cogs_multiplier = float(profile["cogs_multiplier"])
    opex_multiplier = float(profile["opex_multiplier"]) * float(opex_factor)
    start_customers = float(assumptions["start_customers"]) * float(start_customers_factor)
    fte_multiplier = float(assumptions.get("fte_multiplier") or 1.0)

    monthly_projection = []
    cumulative = 0.0
    break_even_month = horizon_months + 1
    customers = max(0.0, start_customers)
    for month in range(1, horizon_months + 1):
        if month > 1:
            new_customers = customers * growth_rate
            churned_customers = customers * churn_rate
            customers = max(0.0, customers + new_customers - churned_customers)
        customers = round(customers, 2)
        ai_inference = customers * float(assumptions["ai_cost_per_customer_monthly"]) * cogs_multiplier
        infra_base = float(assumptions["infra_cost_base_monthly"])
        infra_variable = customers * float(assumptions["infra_cost_per_customer_monthly"]) * cogs_multiplier
        support_variable = customers * float(assumptions["support_cost_per_customer_monthly"]) * cogs_multiplier
        cogs = ai_inference + support_variable + infra_variable
        revenue = customers * arpu

        payroll = 0.0
        for role_name, salary in assumptions["salary_bands_monthly"].items():
            payroll += _resolve_monthly_salary(assumptions, float(salary)) * _fte_for_role(role_name, month, fte_multiplier)
        payroll *= opex_multiplier
        tools = float(assumptions["tooling_base_monthly"]) * opex_multiplier
        sales_marketing = float(assumptions["sales_marketing_base_monthly"]) * (opex_multiplier * (1.0 if month <= 3 else 1.1))
        other_opex = 1200.0 * opex_multiplier
        opex = payroll + tools + sales_marketing + infra_base + other_opex
        gross_profit = revenue - cogs
        net_profit = gross_profit - opex
        cumulative += net_profit
        if break_even_month == horizon_months + 1 and cumulative >= 0:
            break_even_month = month
        monthly_projection.append(
            {
                "month": month,
                "customers": round(customers, 2),
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "gross_profit": round(gross_profit, 2),
                "opex": round(opex, 2),
                "net_profit": round(net_profit, 2),
                "cumulative_net_profit": round(cumulative, 2),
            }
        )

    year_1_rows = monthly_projection[: min(12, len(monthly_projection))]
    year_1_revenue = round(sum(r["revenue"] for r in year_1_rows), 2)
    year_1_net_profit = round(sum(r["net_profit"] for r in year_1_rows), 2)
    return {
        "monthly_projection": monthly_projection,
        "break_even_month": break_even_month,
        "year_1_revenue": year_1_revenue,
        "year_1_net_profit": year_1_net_profit,
        "arpu": round(arpu, 2),
    }


def build_sensitivity_analysis(
    assumptions: Dict[str, Any],
    scenario_name: str,
    horizon_months: int,
) -> Dict[str, Any]:
    baseline = project_financials(assumptions, scenario_name, horizon_months)
    tests = [
        ("ARPU -20%", {"arpu_factor": 0.8}),
        ("ARPU +20%", {"arpu_factor": 1.2}),
        ("Conversion -30%", {"start_customers_factor": 0.7, "growth_rate_factor": 0.75}),
        ("Conversion +20%", {"start_customers_factor": 1.2, "growth_rate_factor": 1.15}),
        ("Churn +25%", {"growth_rate_factor": 0.92}),
        ("Churn -25%", {"growth_rate_factor": 1.08}),
        ("OpEx +15%", {"opex_factor": 1.15}),
        ("OpEx -15%", {"opex_factor": 0.85}),
    ]
    rows: List[Dict[str, Any]] = []
    for label, factors in tests:
        projection = project_financials(
            assumptions=assumptions,
            scenario_name=scenario_name,
            horizon_months=horizon_months,
            start_customers_factor=float(factors.get("start_customers_factor", 1.0)),
            growth_rate_factor=float(factors.get("growth_rate_factor", 1.0)),
            arpu_factor=float(factors.get("arpu_factor", 1.0)),
            opex_factor=float(factors.get("opex_factor", 1.0)),
        )
        rows.append(
            {
                "name": label,
                "year_1_revenue": projection["year_1_revenue"],
                "year_1_net_profit": projection["year_1_net_profit"],
                "break_even_month": projection["break_even_month"],
            }
        )
    return {
        "baseline": {
            "year_1_revenue": baseline["year_1_revenue"],
            "year_1_net_profit": baseline["year_1_net_profit"],
            "break_even_month": baseline["break_even_month"],
        },
        "tests": rows,
        "interpretation": (
            "Sensitivity checks stress-test pricing (ARPU), demand conversion, and operating cost assumptions "
            "to show how recommendation stability changes under realistic benchmark variance."
        ),
    }


def build_stakeholder_dossier(
    source_ctx: Dict[str, Any],
    scenario_profile: str,
    horizon_months: int,
    currency: str,
    region: str,
    selected_model: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    run = source_ctx["run"]
    industry = str(run.get("industry") or "General")
    assumptions, finance_profile = build_run_conditioned_assumptions(industry, run, selected_model)

    selected_profile = scenario_profile if scenario_profile in SCENARIO_PROFILES else "base"
    selected_projection = project_financials(assumptions, selected_profile, horizon_months)
    all_scenarios = {}
    for name in ("conservative", "base", "aggressive"):
        all_scenarios[name] = project_financials(assumptions, name, horizon_months)

    role_rows = []
    monthly_opex_rows = []
    fte_multiplier = float(assumptions.get("fte_multiplier") or 1.0)
    for role_name, salary in assumptions["salary_bands_monthly"].items():
        monthly_salary = _resolve_monthly_salary(assumptions, float(salary))
        fte_by_month = []
        cost_by_month = []
        for month in range(1, horizon_months + 1):
            fte = _fte_for_role(role_name, month, fte_multiplier)
            fte_by_month.append(round(fte, 2))
            cost_by_month.append(round(monthly_salary * fte, 2))
        role_rows.append(
            {
                "role": role_name,
                "fte_by_month": fte_by_month,
                "employment_type": "full_time" if role_name in {"Product Manager", "Senior Engineer", "AI Engineer"} else "hybrid",
                "cost_monthly": cost_by_month,
            }
        )

    for row in selected_projection["monthly_projection"]:
        month = int(row["month"])
        payroll = 0.0
        for role_name, salary in assumptions["salary_bands_monthly"].items():
            payroll += _resolve_monthly_salary(assumptions, float(salary)) * _fte_for_role(role_name, month, fte_multiplier) * SCENARIO_PROFILES[selected_profile]["opex_multiplier"]
        infra_base = float(assumptions["infra_cost_base_monthly"])
        infra_variable = float(row["customers"]) * float(assumptions["infra_cost_per_customer_monthly"]) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"]
        ai_inference = float(row["customers"]) * float(assumptions["ai_cost_per_customer_monthly"]) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"]
        tools = float(assumptions["tooling_base_monthly"]) * SCENARIO_PROFILES[selected_profile]["opex_multiplier"]
        sales_marketing = float(assumptions["sales_marketing_base_monthly"]) * (
            SCENARIO_PROFILES[selected_profile]["opex_multiplier"] * (1.0 if month <= 3 else 1.1)
        )
        other = 1200.0 * SCENARIO_PROFILES[selected_profile]["opex_multiplier"]
        # OpEx total excludes per-customer infra and AI inference (counted in COGS).
        opex_total = payroll + infra_base + tools + sales_marketing + other
        monthly_opex_rows.append(
            {
                "month": month,
                "payroll": round(payroll, 2),
                "infra": round(infra_base, 2),
                "ai_inference": round(ai_inference, 2),
                "infra_variable": round(infra_variable, 2),
                "tools": round(tools, 2),
                "sales_marketing": round(sales_marketing, 2),
                "other": round(other, 2),
                "total": round(opex_total, 2),
            }
        )

    setup_costs = assumptions["setup_costs"]
    setup_total = float(setup_costs["engineering"]) + float(setup_costs["legal_compliance"]) + float(setup_costs["launch_marketing"]) + float(setup_costs["other"])

    scenario_rows = []
    for name in ("conservative", "base", "aggressive"):
        projection = all_scenarios[name]
        scenario_probability = float((finance_profile.get("scenario_probabilities") or {}).get(name) or SCENARIO_PROFILES[name]["probability"])
        scenario_rows.append(
            {
                "name": name,
                "probability": round(scenario_probability, 4),
                "key_assumptions": [
                    f"growth_rate={SCENARIO_PROFILES[name]['growth_rate']}",
                    f"arpu_multiplier={SCENARIO_PROFILES[name]['arpu_multiplier']}",
                    f"opex_multiplier={SCENARIO_PROFILES[name]['opex_multiplier']}",
                    f"churn_multiplier={SCENARIO_PROFILES[name].get('churn_multiplier', 1.0)}",
                ],
                "year_1_revenue": projection["year_1_revenue"],
                "year_1_net_profit": projection["year_1_net_profit"],
            }
        )

    expected_profit = round(sum(float(item["probability"]) * float(item["year_1_net_profit"]) for item in scenario_rows), 2)
    go_no_go = "go" if expected_profit > 0 else "conditional_go"
    thesis = source_ctx["evidence"].get("summary") or (
        f"{industry} execution opportunity selected from saved evidence. Focus on operational pain, fast deployment, and measurable ROI."
    )

    dossier = {
        "meta": {
            "report_version": "stakeholder_v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "currency": currency,
            "horizon_months": horizon_months,
        },
        "decision": {
            "winner": {
                "run_id": int(run.get("id")),
                "model_id": selected_model["model_id"],
                "title": selected_model["title"],
            },
            "thesis": thesis,
            "go_no_go": go_no_go,
            "confidence": selected_model["confidence"],
        },
        "execution_blueprint": {
            "phases": [
                {
                    "name": "Phase 1: Discovery and Validation",
                    "start_month": 1,
                    "end_month": min(3, horizon_months),
                    "workstreams": ["Product", "User Research", "Data/AI"],
                    "deliverables": ["ICP brief", "MVP scope", "pilot design"],
                    "dependencies": ["stakeholder alignment", "data access"],
                    "owner_roles": ["Product Manager", "AI Engineer"],
                },
                {
                    "name": "Phase 2: Build and Pilot",
                    "start_month": 4 if horizon_months >= 4 else 1,
                    "end_month": min(8, horizon_months),
                    "workstreams": ["Engineering", "ModelOps", "Compliance"],
                    "deliverables": ["MVP release", "pilot rollout", "risk controls"],
                    "dependencies": ["pilot customers", "tooling procurement"],
                    "owner_roles": ["Senior Engineer", "AI Engineer", "Designer"],
                },
                {
                    "name": "Phase 3: Scale and Optimize",
                    "start_month": 9 if horizon_months >= 9 else max(1, horizon_months - 2),
                    "end_month": horizon_months,
                    "workstreams": ["GTM", "Customer Success", "Operations"],
                    "deliverables": ["pricing iteration", "sales playbook", "retention program"],
                    "dependencies": ["pilot metrics", "support process readiness"],
                    "owner_roles": ["GTM Lead", "Customer Success", "Product Manager"],
                },
            ],
            "critical_path": [
                "Pilot requirements sign-off",
                "MVP release",
                "First paid customer cohort",
                "Retention and expansion loop",
            ],
            "gates": [
                "Gate 1: Pilot readiness (Month 3)",
                "Gate 2: Revenue validation (Month 6)",
                "Gate 3: Scale readiness (Month 9)",
            ],
            "kill_criteria": [
                "No pilot conversion by Month 6",
                "Gross margin below 45% by Month 9",
                "Retention below target for 2 consecutive months",
            ],
        },
        "resources": {
            "roles": role_rows,
            "tooling": [
                {"name": "LLM API stack", "category": "AI", "monthly_cost": round(float(assumptions["tooling_base_monthly"]) * 0.45, 2)},
                {"name": "Cloud hosting", "category": "Infra", "monthly_cost": round(float(assumptions["tooling_base_monthly"]) * 0.35, 2)},
                {"name": "Analytics + CRM", "category": "Ops", "monthly_cost": round(float(assumptions["tooling_base_monthly"]) * 0.20, 2)},
            ],
            "external_dependencies": [
                "Pilot design partners",
                "Cloud/vendor SLA compliance",
                "Go-to-market channel access",
            ],
        },
        "costs": {
            "setup_cost": {
                "engineering": round(float(setup_costs["engineering"]), 2),
                "legal_compliance": round(float(setup_costs["legal_compliance"]), 2),
                "launch_marketing": round(float(setup_costs["launch_marketing"]), 2),
                "other": round(float(setup_costs["other"]), 2),
                "total": round(setup_total, 2),
            },
            "monthly_opex": monthly_opex_rows,
            "unit_cogs": {
                "per_customer_monthly": round(
                    (float(assumptions["ai_cost_per_customer_monthly"]) + float(assumptions["support_cost_per_customer_monthly"]) + float(assumptions["infra_cost_per_customer_monthly"])) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"],
                    2,
                ),
                "components": [
                    {"name": "ai_inference", "amount": round(float(assumptions["ai_cost_per_customer_monthly"]) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"], 2)},
                    {"name": "support_variable", "amount": round(float(assumptions["support_cost_per_customer_monthly"]) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"], 2)},
                    {"name": "infra_variable", "amount": round(float(assumptions["infra_cost_per_customer_monthly"]) * SCENARIO_PROFILES[selected_profile]["cogs_multiplier"], 2)},
                ],
            },
        },
        "revenue_profit": {
            "pricing": {"model": "B2B subscription", "arpu_monthly": selected_projection["arpu"]},
            "funnel_assumptions": finance_profile.get("funnel_assumptions") or {"traffic_to_lead": 0.03, "lead_to_sql": 0.20, "sql_to_customer": 0.18},
            "monthly_projection": selected_projection["monthly_projection"],
            "break_even_month": selected_projection["break_even_month"],
        },
        "scenarios": scenario_rows,
        "risks": [
            {
                "category": "Execution",
                "description": "MVP delivery delays reduce pilot momentum.",
                "impact": "high",
                "probability": "medium",
                "mitigation": "Lock critical path and enforce weekly milestone review.",
                "owner_role": "Product Manager",
                "trigger": "Two consecutive sprint misses.",
            },
            {
                "category": "Go-to-Market",
                "description": "Conversion below plan in first two cohorts.",
                "impact": "high",
                "probability": "medium",
                "mitigation": "Reposition packaging and pricing with pilot feedback.",
                "owner_role": "GTM Lead",
                "trigger": "SQL-to-customer < 12% for two months.",
            },
            {
                "category": "AI Reliability",
                "description": "Model output variance affects user trust.",
                "impact": "medium",
                "probability": "medium",
                "mitigation": "Use ranking and fallback pipeline with quality checks.",
                "owner_role": "AI Engineer",
                "trigger": "Support tickets referencing low output quality > threshold.",
            },
            {
                "category": "Compliance",
                "description": "Data handling requirements extend implementation time.",
                "impact": "high",
                "probability": "low",
                "mitigation": "Early compliance checklist and staged control rollout.",
                "owner_role": "Product Manager",
                "trigger": "Security/legal review flags unresolved blockers.",
            },
        ],
        "stakeholder_ask": {
            "budget_required": round(setup_total + max(0.0, -selected_projection["monthly_projection"][0]["net_profit"] * 3), 2),
            "team_required": ["Product Manager", "Senior Engineer", "AI Engineer", "GTM Lead"],
            "decision_required": "Approve Phase 1-2 budget and staffing for a 12-month execution cycle.",
            "next_30_days": [
                "Finalize pilot partner shortlist",
                "Lock MVP scope and launch plan",
                "Stand up instrumentation and reporting baseline",
            ],
        },
        "proposal_disclaimer": {
            "title": "Proposal estimate notice",
            "message": (
                "This execution plan is a benchmark-grounded proposal estimate and not client actual financials. "
                "Use it for directional decision support before replacing assumptions with client data."
            ),
            "data_basis": "industry benchmark proxies + deterministic run-conditioned adjustment rules",
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
        "sensitivity_analysis": build_sensitivity_analysis(
            assumptions=assumptions,
            scenario_name=selected_profile,
            horizon_months=horizon_months,
        ),
        "assumptions": [],
        "provenance": {
            "source_artifacts": [{"type": source_ctx["source_type"], "id": source_ctx["source_id"]}],
            "formula_version": "stakeholder_finance_v2",
            "generator_version": "deterministic_dossier_v2",
        },
    }

    assumptions_list = [
        {"key": "industry", "value": industry, "unit": "label", "source": "saved run configuration", "confidence": "high"},
        {"key": "scenario_profile", "value": selected_profile, "unit": "label", "source": "user-selected scenario", "confidence": "high"},
        {"key": "selected_output_title", "value": selected_model["title"], "unit": "label", "source": "selected ranked model output", "confidence": "high"},
        {"key": "selected_model_confidence", "value": finance_profile.get("selected_model_confidence"), "unit": "ratio", "source": "rank_result-derived confidence", "confidence": "medium"},
        {
            "key": "scenario_probability_mix",
            "value": (
                f"conservative={finance_profile.get('scenario_probabilities', {}).get('conservative')},"
                f"base={finance_profile.get('scenario_probabilities', {}).get('base')},"
                f"aggressive={finance_profile.get('scenario_probabilities', {}).get('aggressive')}"
            ),
            "unit": "mix",
            "source": "deterministic risk-adjusted probability rules",
            "confidence": "medium",
        },
        {
            "key": "finance_adjustment_tags",
            "value": ", ".join(finance_profile.get("applied_tags") or []) or "none",
            "unit": "labels",
            "source": "deterministic rules from constraints/persona/output signals",
            "confidence": "medium",
        },
        {
            "key": "start_customers",
            "value": assumptions["start_customers"],
            "unit": "customers",
            "source": f"{ASSUMPTION_SOURCE_MAP['start_customers']} + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "default_arpu_monthly",
            "value": assumptions["default_arpu_monthly"],
            "unit": currency,
            "source": f"{ASSUMPTION_SOURCE_MAP['default_arpu_monthly']} + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "salary_unit",
            "value": assumptions.get("salary_unit") or "monthly",
            "unit": "label",
            "source": "assumption pack + deterministic normalization",
            "confidence": "high",
        },
        {
            "key": "fte_multiplier",
            "value": assumptions.get("fte_multiplier") or 1.0,
            "unit": "ratio",
            "source": "deterministic staffing profile rules",
            "confidence": "medium",
        },
        {
            "key": "monthly_churn_rate",
            "value": assumptions.get("monthly_churn_rate") or 0.03,
            "unit": "ratio",
            "source": "industry benchmark proxy + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "ai_cost_per_customer_monthly",
            "value": assumptions["ai_cost_per_customer_monthly"],
            "unit": currency,
            "source": f"{ASSUMPTION_SOURCE_MAP['ai_cost_per_customer_monthly']} + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "support_cost_per_customer_monthly",
            "value": assumptions["support_cost_per_customer_monthly"],
            "unit": currency,
            "source": f"{ASSUMPTION_SOURCE_MAP['support_cost_per_customer_monthly']} + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "infra_cost_per_customer_monthly",
            "value": assumptions["infra_cost_per_customer_monthly"],
            "unit": currency,
            "source": f"{ASSUMPTION_SOURCE_MAP['infra_cost_per_customer_monthly']} + deterministic run-conditioned adjustment",
            "confidence": "medium",
        },
        {
            "key": "expected_year_1_net_profit",
            "value": expected_profit,
            "unit": currency,
            "source": "deterministic scenario-weighted projection (stakeholder_finance_v2)",
            "confidence": "medium",
        },
    ]
    dossier["assumptions"] = assumptions_list
    return dossier, assumptions_list
