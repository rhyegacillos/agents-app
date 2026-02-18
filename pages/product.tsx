"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { Protect, UserButton, useAuth, useUser, useClerk, PricingTable } from "@clerk/nextjs";

const CLERK_JWT_TEMPLATE = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || "";

function tokenOptions(skipCache?: boolean) {
  const opts: { skipCache?: boolean; template?: string } = {};
  if (skipCache) {
    opts.skipCache = true;
  }
  if (CLERK_JWT_TEMPLATE) {
    opts.template = CLERK_JWT_TEMPLATE;
  }
  return opts;
}



const INDUSTRIES = [
  "FinTech",
  "HealthTech",
  "EdTech",
  "AgriTech",
  "E-commerce",
  "Real Estate",
  "Cybersecurity",
  "LegalTech",
  "MarTech",
  "CleanTech",
  "Gaming",
  "Logistics",
  "Travel & Tourism",
  "HR Tech",
  "PropTech",
  "InsuranceTech",
  "Supply Chain & Procurement",
  "Customer Support Operations",
  "Sales Operations & RevOps",
  "Healthcare Operations (Non-Clinical)",
  "Pharma & Life Sciences Ops",
  "Financial Compliance & Audit",
  "Construction & Field Services",
  "Manufacturing Operations",
  "Energy & Utilities Operations",
  "Government & Public Sector Ops",
  "Media & Content Operations",
  "Creator Economy Tools",
  "Retail Operations",
  "SMB Back Office (Accounting, Payroll, Invoicing)",
];

const INDUSTRY_HINTS: Record<string, string> = {
  "FinTech": "Products for payments, lending, banking, and money operations.",
  "HealthTech": "Solutions for healthcare systems, clinics, and patient workflows.",
  "EdTech": "Tools that improve learning, teaching, and education operations.",
  "AgriTech": "Technology for farming, crop planning, and agricultural efficiency.",
  "E-commerce": "Online selling, storefront operations, checkout, and fulfillment.",
  "Real Estate": "Tools for property search, leasing, transactions, and management.",
  "Cybersecurity": "Solutions that protect systems, data, and user access.",
  "LegalTech": "Software for legal research, contracts, compliance, and law operations.",
  "MarTech": "Tools for marketing campaigns, analytics, and customer engagement.",
  "CleanTech": "Technology focused on sustainability, energy efficiency, and emissions reduction.",
  "Gaming": "Products for game creation, player growth, and live operations.",
  "Logistics": "Solutions for shipping, routing, delivery tracking, and warehouse flow.",
  "Travel & Tourism": "Tools for bookings, itineraries, customer support, and travel planning.",
  "HR Tech": "Products for hiring, onboarding, people ops, and workforce management.",
  "PropTech": "Technology for property operations, leasing, and building management.",
  "InsuranceTech": "Tools for underwriting, claims, pricing, and policy servicing.",
  "Supply Chain & Procurement": "Solutions for sourcing, purchasing, inventory, and supplier workflows.",
  "Customer Support Operations": "Tools for ticket handling, helpdesk productivity, and service quality.",
  "Sales Operations & RevOps": "Products for pipeline management, forecasting, and revenue execution.",
  "Healthcare Operations (Non-Clinical)": "Operational tools for healthcare admin, scheduling, and back-office tasks.",
  "Pharma & Life Sciences Ops": "Solutions for pharma workflows, documentation, and regulated operations.",
  "Financial Compliance & Audit": "Tools for controls, reporting, risk checks, and audit readiness.",
  "Construction & Field Services": "Products for jobsite planning, field teams, and service dispatch.",
  "Manufacturing Operations": "Tools for production planning, quality, and factory workflows.",
  "Energy & Utilities Operations": "Solutions for grid, utility operations, and service reliability.",
  "Government & Public Sector Ops": "Tools for public services, agency workflows, and compliance-heavy operations.",
  "Media & Content Operations": "Products for content production, publishing pipelines, and editorial workflows.",
  "Creator Economy Tools": "Tools for creators to grow audience, monetize, and manage work.",
  "Retail Operations": "Solutions for store performance, inventory, and shopper experience.",
  "SMB Back Office (Accounting, Payroll, Invoicing)": "Tools for small-business finance and day-to-day admin operations.",
};

const CONSTRAINTS = [
  "None",
  "Low Startup Cost (<$5k)",
  "No-Code Solution",
  "Enterprise Scale",
  "B2B SaaS",
  "B2C Mobile App",
  "Bootstrapped Friendly",
  "Human-in-the-Loop Required",
  "Regulated Environment (HIPAA, SOC2, GDPR)",
  "Data Cannot Leave Customer Environment",
  "API-First (No UI MVP)",
  "Single-Person Buyer (Founder / Manager)",
  "Long Sales Cycle (6+ months)",
  "Usage-Based Pricing Required",
  "Offline / Low-Connectivity Environment",
  "International / Multi-Language Users",
  "Legacy Systems Only (Email, Excel, PDFs)",
];

const CONSTRAINT_HINTS: Record<string, string> = {
  "None": "No limits. The AI can propose any idea type.",
  "Low Startup Cost (<$5k)": "Ideas should be launchable with about $5,000 or less.",
  "No-Code Solution": "Prefer tools and workflows that do not require custom coding.",
  "Enterprise Scale": "Ideas should support large teams, high volume, and reliability needs.",
  "B2B SaaS": "Focus on software sold to businesses on a subscription model.",
  "B2C Mobile App": "Focus on a mobile app experience for individual consumers.",
  "Bootstrapped Friendly": "Ideas should be practical without heavy outside funding.",
  "Human-in-the-Loop Required": "A person must review or approve key AI decisions.",
  "Regulated Environment (HIPAA, SOC2, GDPR)": "Ideas must work in strict compliance and audit-heavy contexts.",
  "Data Cannot Leave Customer Environment": "Data must stay in the customer's own environment (on-prem or private cloud).",
  "API-First (No UI MVP)": "Prioritize backend/API value first, with minimal or no initial frontend.",
  "Single-Person Buyer (Founder / Manager)": "Design for one clear decision maker with fast buying decisions.",
  "Long Sales Cycle (6+ months)": "Assume enterprise-like procurement with long evaluation and approval timelines.",
  "Usage-Based Pricing Required": "Business model should charge based on usage/consumption.",
  "Offline / Low-Connectivity Environment": "Solution should work with weak internet or partial offline operation.",
  "International / Multi-Language Users": "Plan for localization and multiple language support early.",
  "Legacy Systems Only (Email, Excel, PDFs)": "Assume customers rely on basic tools and older workflows.",
};

const PERSONAS = [
  { id: "Neutral", label: "Neutral / Professional (Execution Focused)" },
  { id: "Critical VC", label: "Critical VC Investor (Risk, Moat, Distribution)" },
  { id: "Optimistic Visionary", label: "Optimistic Visionary (Platform & Expansion)" },
  { id: "Operator", label: "Experienced Operator (Workflow & ROI Focused)" },
  { id: "Compliance Officer", label: "Compliance / Risk Officer (Safety & Controls)" },
  { id: "Solo Founder", label: "Solo Founder (Speed, Simplicity, Cashflow)" },
  { id: "Enterprise Buyer", label: "Enterprise Buyer (Security, Procurement, Governance)" },
  { id: "Growth Marketer", label: "Growth Marketer (Acquisition & Retention)" },
];

const PERSONA_HINTS: Record<string, string> = {
  "Neutral": "Balanced and practical. Focuses on clear execution, feasibility, and tradeoffs.",
  "Critical VC": "Investor mindset. Challenges market size, moat strength, risks, and defensibility.",
  "Optimistic Visionary": "Big-picture mode. Pushes platform potential, expansion, and long-term upside.",
  "Operator": "Execution-first. Emphasizes process, workflow fit, ROI, and operational reality.",
  "Compliance Officer": "Risk-control lens. Prioritizes policy, auditability, security, and safety controls.",
  "Solo Founder": "Lean builder style. Focuses on speed, simplicity, and early cashflow.",
  "Enterprise Buyer": "Procurement mindset. Prioritizes security, governance, integration, and vendor trust.",
  "Growth Marketer": "Go-to-market lens. Focuses on acquisition channels, retention loops, and conversion.",
};

const MODELS = [
  { id: "gpt-5-nano", label: "OpenAI" },
  { id: "gemini-2.5-pro", label: "Gemini" },
  { id: "deepseek-chat", label: "DeepSeek" },
  { id: "grok-4-1-fast-reasoning", label: "Grok" },
];

function getConstraintHint(constraint: string) {
  return CONSTRAINT_HINTS[constraint] || "Applies this rule while generating ideas.";
}

function getIndustryHint(industry: string) {
  return INDUSTRY_HINTS[industry] || "Sets the business domain for the ideas.";
}

function getPersonaHint(personaId: string) {
  return PERSONA_HINTS[personaId] || "Changes the point of view used to evaluate and write ideas.";
}

type HoverBubbleState = {
  text: string;
  top: number;
  left: number;
  side: "right" | "left";
};

function buildHoverBubble(target: HTMLElement, text: string): HoverBubbleState {
  const rect = target.getBoundingClientRect();
  const bubbleWidth = 320;
  const margin = 12;
  const hasRightSpace = rect.right + margin + bubbleWidth < window.innerWidth - 12;
  const side: "right" | "left" = hasRightSpace ? "right" : "left";
  const top = Math.round(Math.max(16, Math.min(window.innerHeight - 16, rect.top + rect.height / 2)));
  const left = side === "right" ? rect.right + margin : rect.left - margin;
  return { text, top, left, side };
}

type IdeaResults = { [key: string]: string };
type SavedResultSummary = {
  id: number;
  created_at: string;
  industry?: string;
  tone?: string;
  constraints?: string[];
  models?: string[];
  model_count?: number;
};
type CompareResult = {
  comparison_id?: number;
  created_at?: string;
  run_a_id: number;
  run_b_id: number;
  winner_run_id: number | null;
  comparison: {
    winner: "A" | "B" | "tie";
    summary: string;
    key_changes: string[];
    winner_rationale: string;
    risks?: string[];
    top_outputs?: {
      run_a?: { title?: string; model_label?: string; model_id?: string; output_html?: string; score?: number | null };
      run_b?: { title?: string; model_label?: string; model_id?: string; output_html?: string; score?: number | null };
    };
  };
  cached?: boolean;
};
type RankResult = {
  summary?: string;
  ranked_models?: Array<{
    model_id: string;
    rank: number;
    score?: number;
    title?: string;
    rationale?: string;
  }>;
  highlights?: string[];
  title_map?: Record<string, string>;
  skipped?: boolean;
  reason?: string;
};
type SavedComparisonSummary = {
  id: number;
  created_at: string;
  run_a_id: number;
  run_b_id: number;
  winner_run_id: number | null;
  top_outputs?: {
    run_a?: { title?: string; model_label?: string; score?: number | null };
    run_b?: { title?: string; model_label?: string; score?: number | null };
  };
};
type SavedReportSummary = {
  id: number;
  created_at: string;
  run_ids: number[];
  summary?: string;
  top_run_id?: number | null;
  model?: string;
};
type DecisionSummaryReport = {
  id: number;
  created_at: string;
  run_ids: number[];
  report?: {
    summary?: string;
    ranked_runs?: Array<{ run_id?: number; score?: number; rationale?: string }>;
    key_insights?: string[];
    risks?: string[];
    next_steps?: string[];
  };
  runs_snapshot?: Array<{
    id?: number;
    created_at?: string;
    industry?: string;
    tone?: string;
    constraints?: string[];
    models?: string[];
    results?: Record<string, string>;
    rank_result?: RankResult;
  }>;
};

type StakeholderReportSummary = {
  id: number;
  created_at: string;
  source_type: string;
  source_id: number;
  title?: string;
  recommendation?: "go" | "conditional_go" | "no_go";
  scenario_profile: string;
  horizon_months: number;
  currency: string;
  region: string;
  model?: string;
};

type StakeholderReport = StakeholderReportSummary & {
  assumptions?: Array<{
    key: string;
    value: string | number;
    unit: string;
    source: string;
    confidence: "low" | "medium" | "high";
  }>;
  dossier?: {
    decision?: {
      thesis?: string;
      go_no_go?: "go" | "conditional_go" | "no_go";
      confidence?: number;
      winner?: { run_id?: number; model_id?: string; title?: string };
    };
    decision_support?: {
      status?: "viable" | "conditional" | "not_viable";
      forced_by_rules?: boolean;
      reasons?: string[];
      required_actions?: string[];
      profitability_recovery?: {
        enabled?: boolean;
        monthly_profit_gap?: number;
        target_year_1_net_profit?: number;
        levers?: Array<{
          name?: string;
          target?: string;
          estimated_monthly_impact?: number;
        }>;
        scenarios?: Array<{
          name?: string;
          moves?: string[];
          estimated_monthly_impact?: number;
          estimated_year_1_net_profit?: number;
          estimated_break_even_month?: number;
        }>;
        experiments_90_days?: Array<{
          name?: string;
          owner?: string;
          target_metric?: string;
          deadline_days?: number;
          expected_monthly_impact?: number;
        }>;
        approval_gate?: string;
      };
      gates?: {
        year_1_net_profit?: number;
        expected_year_1_net_profit?: number | null;
        break_even_month?: number;
        break_even_within_horizon?: boolean;
        gross_margin_ratio?: number | null;
        horizon_months?: number;
      };
    };
    execution_blueprint?: {
      phases?: Array<{
        name?: string;
        start_month?: number;
        end_month?: number;
        workstreams?: string[];
        deliverables?: string[];
        dependencies?: string[];
        owner_roles?: string[];
      }>;
      critical_path?: string[];
      gates?: string[];
      kill_criteria?: string[];
    };
    resources?: {
      roles?: Array<{
        role?: string;
        fte_by_month?: number[];
        employment_type?: string;
        cost_monthly?: number[];
      }>;
      tooling?: Array<{ name?: string; category?: string; monthly_cost?: number }>;
      external_dependencies?: string[];
    };
    costs?: {
      setup_cost?: {
        engineering?: number;
        legal_compliance?: number;
        launch_marketing?: number;
        other?: number;
        total?: number;
      };
      monthly_opex?: Array<{
        month?: number;
        payroll?: number;
        infra?: number;
        ai_inference?: number;
        tools?: number;
        sales_marketing?: number;
        other?: number;
        total?: number;
      }>;
      unit_cogs?: {
        per_customer_monthly?: number;
        components?: Array<{ name?: string; amount?: number }>;
      };
    };
    revenue_profit?: {
      pricing?: { model?: string; arpu_monthly?: number };
      funnel_assumptions?: {
        traffic_to_lead?: number;
        lead_to_sql?: number;
        sql_to_customer?: number;
      };
      break_even_month?: number;
      monthly_projection?: Array<{
        month?: number;
        customers?: number;
        revenue?: number;
        cogs?: number;
        gross_profit?: number;
        opex?: number;
        net_profit?: number;
        cumulative_net_profit?: number;
      }>;
    };
    scenarios?: Array<{
      name?: string;
      probability?: number;
      key_assumptions?: string[];
      year_1_revenue?: number;
      year_1_net_profit?: number;
    }>;
    risks?: Array<{
      category?: string;
      description?: string;
      impact?: string;
      probability?: string;
      mitigation?: string;
      owner_role?: string;
      trigger?: string;
    }>;
    stakeholder_ask?: {
      budget_required?: number;
      team_required?: string[];
      decision_required?: string;
      next_30_days?: string[];
    };
    proposal_disclaimer?: {
      title?: string;
      message?: string;
      data_basis?: string;
      updated_at?: string;
    };
    sensitivity_analysis?: {
      baseline?: {
        year_1_revenue?: number;
        year_1_net_profit?: number;
        break_even_month?: number;
      };
      tests?: Array<{
        name?: string;
        year_1_revenue?: number;
        year_1_net_profit?: number;
        break_even_month?: number;
      }>;
      interpretation?: string;
    };
    provenance?: {
      source_artifacts?: Array<{ type?: string; id?: number }>;
      formula_version?: string;
      generator_version?: string;
    };
  };
};

type RunSnapshot = NonNullable<DecisionSummaryReport["runs_snapshot"]>[number];

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  );
}

function LoadingDots({ className = "" }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-0.5", className)} aria-hidden="true">
      <span className="h-1 w-1 rounded-full bg-current animate-pulse [animation-delay:0ms]" />
      <span className="h-1 w-1 rounded-full bg-current animate-pulse [animation-delay:180ms]" />
      <span className="h-1 w-1 rounded-full bg-current animate-pulse [animation-delay:360ms]" />
    </span>
  );
}

function HelpTooltip({ content }: { content: React.ReactNode }) {
  const [show, setShow] = useState(false);

  return (
    <div className="relative inline-flex items-center ml-1.5 align-middle">
      <button
        type="button"
        className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors focus:outline-none"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onClick={() => setShow(!show)}
        aria-label="More info"
      >
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM8.94 6.94a.75.75 0 11-1.061-1.061 3 3 0 112.871 5.026v.345a.75.75 0 01-1.5 0v-.5c0-.72.57-1.172 1.081-1.287A1.5 1.5 0 108.94 6.94zM10 15a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
        </svg>
      </button>
      {show && (
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 p-2.5 text-xs leading-relaxed text-white bg-slate-800 border border-white/10 rounded-lg shadow-xl z-50 pointer-events-none">
          {content}
          <div className="absolute bottom-full left-1/2 -translate-x-1/2 border-4 border-transparent border-b-slate-800" />
        </div>
      )}
    </div>
  );
}

function InfoPillTooltip({ content }: { content: React.ReactNode }) {
  const [show, setShow] = useState(false);

  return (
    <div className="relative inline-flex items-start">
      <button
        type="button"
        className="inline-flex -translate-y-1 items-center rounded-full border border-sky-400/35 bg-sky-500/10 px-1.5 py-[1px] text-[9px] font-semibold uppercase tracking-[0.08em] leading-none text-sky-200 transition-colors hover:bg-sky-500/20 focus:outline-none"
        onMouseEnter={() => setShow(true)}
        onMouseLeave={() => setShow(false)}
        onFocus={() => setShow(true)}
        onBlur={() => setShow(false)}
        onClick={() => setShow((prev) => !prev)}
        aria-label="Panel info"
      >
        Info
      </button>
      {show ? (
        <div className="absolute left-0 top-full z-50 mt-2 w-[22rem] max-w-[82vw] rounded-lg border border-sky-400/30 bg-slate-950/95 p-3 text-[11px] leading-relaxed text-sky-50 shadow-xl pointer-events-none">
          {content}
          <div className="absolute -top-2 left-4 h-2 w-2 rotate-45 border-l border-t border-sky-400/30 bg-slate-950/95" />
        </div>
      ) : null}
    </div>
  );
}

function TechnicalLabel({
  label,
  tooltip,
  className = "",
}: {
  label: string;
  tooltip: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cx("inline-flex items-center gap-1", className)}>
      <span>{label}</span>
      <HelpTooltip content={tooltip} />
    </span>
  );
}

function UsageLabel({ label, tooltip }: { label: string; tooltip: string }) {
  return (
    <span className="relative inline-flex items-center group">
      <span
        tabIndex={0}
        className="cursor-help font-semibold text-gray-700 dark:text-gray-300 focus:outline-none"
      >
        {label}
      </span>
      <span
        className={cx(
          "pointer-events-none absolute left-1/2 top-full z-30 mt-1 w-max -translate-x-1/2 rounded-md",
          "border border-black/10 bg-white/90 px-2 py-1 text-[10px] text-gray-700 shadow",
          "opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100",
          "dark:border-white/10 dark:bg-slate-950/95 dark:text-gray-200"
        )}
      >
        {tooltip}
      </span>
    </span>
  );
}

function recommendationLabel(value?: string) {
  if (value === "go") return "Go";
  if (value === "no_go") return "No-Go";
  return "Conditional Go";
}

function recommendationTone(value?: string) {
  if (value === "go") {
    return "border-emerald-500/40 bg-emerald-500/12 text-emerald-300";
  }
  if (value === "no_go") {
    return "border-rose-500/40 bg-rose-500/12 text-rose-300";
  }
  return "border-amber-500/40 bg-amber-500/12 text-amber-300";
}

function FullPageLoader({
  title,
  subtitle,
  chips,
  note,
  tip,
}: {
  title: string;
  subtitle?: string;
  chips?: string[];
  note?: string;
  tip?: string;
}) {
  const resolvedNote =
    note === undefined
      ? "Reasoning models may take longer. Keep this tab open — results will appear automatically."
      : note;
  const resolvedTip =
    tip === undefined
      ? "Tip: selecting fewer models returns faster."
      : tip;

  return (
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/55 backdrop-blur-lg p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Loading"
    >
      <div className="relative w-full max-w-3xl">
        {/* outer glow */}
        <div className="pointer-events-none absolute -inset-10 rounded-[40px] bg-[radial-gradient(closest-side,rgba(99,102,241,0.30),transparent_70%)]" />

        {/* gradient hairline border */}
        <div className="relative rounded-[28px] p-[1px] bg-gradient-to-br from-white/20 via-white/10 to-white/5">
          <div className="relative rounded-[27px] border border-white/10 bg-white/10 backdrop-blur-xl shadow-[0_25px_80px_rgba(0,0,0,0.65)] overflow-hidden">
            {/* top highlight */}
            <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-white/10 to-transparent" />

            <div className="relative p-8 sm:p-10">
              <div className="grid grid-cols-1 md:grid-cols-[1fr_220px] gap-8 items-center">
                {/* LEFT: details */}
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="text-2xl sm:text-3xl font-semibold tracking-tight text-white">
                      {title}
                    </h3>
                    <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-white/70">
                      Working…
                    </span>
                  </div>

                  {subtitle ? (
                    <p className="mt-2 text-base sm:text-lg leading-snug text-white/70">
                      {subtitle}
                    </p>
                  ) : null}

                  {chips && chips.length > 0 ? (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {chips.map((c) => (
                        <span
                          key={c}
                          className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-white/80"
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  ) : null}

                  {resolvedNote ? (
                    <div className="mt-6 text-sm text-white/60">
                      {resolvedNote}
                    </div>
                  ) : null}

                  <div className="mt-6 border-t border-white/10 pt-5 flex items-center justify-between">
                    <div className="text-xs text-white/50">
                      {resolvedTip}
                    </div>
                    <div className="text-xs font-semibold text-white/70">IdeaGen</div>
                  </div>
                </div>

                {/* RIGHT: single big spinner */}
                <div className="flex md:justify-end justify-start">
                  <div className="relative h-44 w-44">
                    {/* soft ring */}
                    <div className="absolute inset-0 rounded-full bg-white/5 border border-white/10" />
                    {/* rotating conic ring */}
                    <div className="absolute inset-0 rounded-full bg-[conic-gradient(from_180deg,rgba(59,130,246,0.0),rgba(59,130,246,0.95),rgba(99,102,241,0.0))] animate-[spin_1.1s_linear_infinite] [mask:radial-gradient(farthest-side,transparent_calc(100%-12px),#000_calc(100%-11px))]" />
                    {/* center glow */}
                    <div className="absolute inset-6 rounded-full bg-[radial-gradient(circle,rgba(59,130,246,0.18),transparent_65%)]" />
                    {/* optional tiny label (not a loader) */}
                    <div className="absolute inset-0 grid place-items-center">
                      <div className="text-xs font-semibold tracking-wide text-white/70">
                        Generating…
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}



function GlassCard({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        "rounded-2xl border border-white/10 bg-white/70 backdrop-blur dark:bg-white/5",
        "shadow-[0_1px_0_rgba(255,255,255,0.06)]",
        className
      )}
    >
      {children}
    </div>
  );
}

function UpgradeModal({
  open,
  onClose,
  onUpgrade,
}: {
  open: boolean;
  onClose: () => void;
  onUpgrade?: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
        <div className="text-lg font-semibold">Premium feature</div>
        <p className="mt-2 text-sm text-white/70">
          This action is available on Premium. Upgrade to unlock full constraints, personas, multi-model comparison, recommendations, and exports.
        </p>
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            className="flex-1 rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold hover:bg-blue-700"
            onClick={() => {
              onClose();
              onUpgrade?.();
            }}
          >
            Upgrade
          </button>
          <button
            type="button"
            className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
            onClick={onClose}
          >
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}

function ResultsSkeletonCard() {
  return (
    <div className="mt-4 space-y-4 animate-pulse">
      <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-4 space-y-3">
        <div className="h-4 w-40 rounded bg-black/10 dark:bg-white/10" />
        <div className="h-3 w-2/3 rounded bg-black/10 dark:bg-white/10" />
      </div>
      <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-5 space-y-3">
        <div className="h-4 w-1/3 rounded bg-black/10 dark:bg-white/10" />
        <div className="h-3 w-full rounded bg-black/10 dark:bg-white/10" />
        <div className="h-3 w-11/12 rounded bg-black/10 dark:bg-white/10" />
        <div className="h-3 w-10/12 rounded bg-black/10 dark:bg-white/10" />
      </div>
    </div>
  );
}

function ConstraintMultiSelectDropdown({
  options,
  value,
  onChange,
  maxSelected = 3,
  isPremium = true,
  freeAllowedCount = 3,
  onLimitReached,
  onPremiumOptionSelected,
}: {
  options: string[];
  value: string[];
  onChange: (next: string[]) => void;
  maxSelected?: number;
  isPremium?: boolean;
  freeAllowedCount?: number;
  onLimitReached?: () => void;
  onPremiumOptionSelected?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [hoverBubble, setHoverBubble] = useState<HoverBubbleState | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const NONE = options[0]; // "None" is expected to be first

  useEffect(() => {
    const onDocMouseDown = (e: MouseEvent) => {
      if (!containerRef.current) return;
      if (!containerRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDocMouseDown);
    return () => document.removeEventListener("mousedown", onDocMouseDown);
  }, []);

  useEffect(() => {
    if (!open) setHoverBubble(null);
  }, [open]);

  const toggle = (opt: string, isOptionPremiumLocked: boolean) => {
    if (isOptionPremiumLocked) {
      onPremiumOptionSelected?.();
      return;
    }

    // If user clicks "None": reset everything else
    if (opt === NONE) {
      onChange([NONE]);
      return;
    }

    // work on a list that never includes NONE
    const withoutNone = value.filter((v) => v !== NONE);
    const exists = withoutNone.includes(opt);

    // unselect
    if (exists) {
      const next = withoutNone.filter((v) => v !== opt);
      onChange(next.length ? next : [NONE]);
      return;
    }

    // select (enforce max)
    if (withoutNone.length >= maxSelected) {
      onLimitReached?.();
      return;
    }

    onChange([...withoutNone, opt]);
  };

  const hasNoneOnly = value.length === 1 && value[0] === NONE;
  const buttonLabel =
    value.length === 0 || hasNoneOnly
      ? NONE
      : value.length === 1
      ? value[0]
      : `${value.length} selected`;

  const summary = value?.length ? value.join(", ") : NONE;

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cx(
          "w-full rounded-xl border px-3 py-2.5 text-sm outline-none flex items-center justify-between gap-2",
          "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
          "focus:ring-2 focus:ring-blue-500/40"
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className={cx("text-sm truncate", value.length ? "text-gray-900 dark:text-gray-100" : "text-gray-500")}>
          {buttonLabel}
        </span>

        {/* match Target Industry / Persona caret */}
        <svg
          className={cx(
            "h-4 w-4 shrink-0 text-gray-500 dark:text-gray-300 transition-transform",
            open ? "rotate-180" : "rotate-0"
          )}
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
            clipRule="evenodd"
          />
        </svg>
      </button>

      {open && (
        <div
          className={cx(
            "absolute left-0 right-0 z-50 mt-2 w-full rounded-2xl border border-white/10 shadow-2xl overflow-hidden",
            // match Target Industry background
            "bg-slate-950/95 backdrop-blur pointer-events-auto"
          )}
        >
          <div className="p-2 max-h-64 overflow-y-auto ig-scrollbar bg-slate-950/95">
            {options.map((opt, idx) => {
              const checked = value.includes(opt);
              const optionHint = getConstraintHint(opt);

              // "None" is always allowed; premium lock applies to the rest
              const optionPremiumLocked = opt !== NONE && !isPremium && idx >= freeAllowedCount;

              // enforce max only on non-NONE selections
              const nonNoneCount = value.filter((v) => v !== NONE).length;
              const disabledByCount = opt !== NONE && !checked && nonNoneCount >= maxSelected;

              const disabled = optionPremiumLocked || disabledByCount;

              return (
                <label
                  key={opt}
                  aria-label={`${opt}. ${optionHint}`}
                  onMouseEnter={(e) => setHoverBubble(buildHoverBubble(e.currentTarget, `${opt} — ${optionHint}`))}
                  onMouseMove={(e) => setHoverBubble(buildHoverBubble(e.currentTarget, `${opt} — ${optionHint}`))}
                  onMouseLeave={() => setHoverBubble(null)}
                  onFocus={(e) => setHoverBubble(buildHoverBubble(e.currentTarget, `${opt} — ${optionHint}`))}
                  onBlur={() => setHoverBubble(null)}
                  className={cx(
                    "flex items-center gap-2 px-2 py-2 rounded-xl select-none",
                    disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-white/10"
                  )}
                >
                  <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggle(opt, optionPremiumLocked)} />
                  <span className="text-sm text-white/90 flex-1 whitespace-normal break-words">{opt}</span>

                  {optionPremiumLocked ? (
                    <span className="text-[10px] font-semibold text-white/50">Premium</span>
                  ) : null}
                </label>
              );
            })}
          </div>

          <div className="flex items-center justify-between gap-2 p-2 border-t border-white/10 bg-slate-950/95">
            <div className="text-[11px] text-white/55">Max {maxSelected} • Selected: {summary}</div>
          </div>
        </div>
      )}
      {open && hoverBubble
        ? createPortal(
            <div
              className="fixed z-[120] max-w-[320px] rounded-xl border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[11px] leading-snug text-white/90 shadow-2xl backdrop-blur pointer-events-none"
              style={{
                top: hoverBubble.top,
                left: hoverBubble.left,
                transform: hoverBubble.side === "right" ? "translateY(-50%)" : "translate(-100%, -50%)",
              }}
              role="tooltip"
            >
              {hoverBubble.text}
            </div>,
            document.body
          )
        : null}
    </div>
  );
}


function IdeaGenerator({
  isPremium = false,
  planLoaded = true,
  initialUsage = {},
}: {
  isPremium?: boolean;
  planLoaded?: boolean;
  initialUsage?: any;
}) {
  const { getToken } = useAuth();
  const { openUserProfile, openSignIn } = useClerk();
  const { isSignedIn } = useUser();

  const [results, setResults] = useState<IdeaResults>({});
  const [isLoading, setIsLoading] = useState(false);
  const [resultsHydrating, setResultsHydrating] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("");
  const [resultsView, setResultsView] = useState<"generated" | "insights" | "decision" | "stakeholder">("generated");
  const [loadedSavedId, setLoadedSavedId] = useState<number | null>(null);
  const [loadedSavedSnapshot, setLoadedSavedSnapshot] = useState<string | null>(null);
  const [industry, setIndustry] = useState(INDUSTRIES[0]);
  const [constraints, setConstraints] = useState<string[]>([CONSTRAINTS[0]]);
  const [tone, setTone] = useState(PERSONAS[0].id);
  const [selectedModels, setSelectedModels] = useState<string[]>([MODELS[0].id]);
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(0.9);
  const [tokenUsage, setTokenUsage] = useState<any>(initialUsage);
  const [usageNotices, setUsageNotices] = useState<{ id: string; message: string }[]>([]);
  const noticeTimeouts = useRef<number[]>([]);
  const [savedResults, setSavedResults] = useState<SavedResultSummary[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savingResults, setSavingResults] = useState(false);
  const [loadingSavedId, setLoadingSavedId] = useState<number | null>(null);
  const [deletingSavedId, setDeletingSavedId] = useState<number | null>(null);
  const [savedUsageBytes, setSavedUsageBytes] = useState(0);
  const [savedLimitBytes, setSavedLimitBytes] = useState(0);
  const [savedPanelMode, setSavedPanelMode] = useState<"generated" | "compare" | "decision" | "stakeholder" | null>(null);
  const [savedPanelPos, setSavedPanelPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const savedPanelRef = useRef<HTMLDivElement | null>(null);
  const savedPanelDragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    width: number;
    height: number;
  } | null>(null);
  const [isDraggingSavedPanel, setIsDraggingSavedPanel] = useState(false);
  const savedGeneratedButtonRef = useRef<HTMLButtonElement | null>(null);
  const savedCompareButtonRef = useRef<HTMLButtonElement | null>(null);
  const savedDecisionButtonRef = useRef<HTMLButtonElement | null>(null);
  const savedStakeholderButtonRef = useRef<HTMLButtonElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [pageBootLoading, setPageBootLoading] = useState(true);
  const [compareSelection, setCompareSelection] = useState<{ runA: number | null; runB: number | null }>({
    runA: null,
    runB: null,
  });
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [compareResult, setCompareResult] = useState<CompareResult | null>(null);
  const [savedComparisons, setSavedComparisons] = useState<SavedComparisonSummary[]>([]);
  const [comparisonsLoading, setComparisonsLoading] = useState(false);
  const [savedReports, setSavedReports] = useState<SavedReportSummary[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [savedStakeholderReports, setSavedStakeholderReports] = useState<StakeholderReportSummary[]>([]);
  const [stakeholderReportsLoading, setStakeholderReportsLoading] = useState(false);
  const [stakeholderReport, setStakeholderReport] = useState<StakeholderReport | null>(null);
  const [executionPlanPickerOpen, setExecutionPlanPickerOpen] = useState(false);
  const [executionPlanSelectedKey, setExecutionPlanSelectedKey] = useState<string | null>(null);
  const [executionPlanPickerLoading, setExecutionPlanPickerLoading] = useState(false);
  const [executionPlanGeneratedKeys, setExecutionPlanGeneratedKeys] = useState<string[]>([]);
  const [executionPlanPickerError, setExecutionPlanPickerError] = useState<string | null>(null);
  const [executionPlanPickerPos, setExecutionPlanPickerPos] = useState<{ top: number; left: number; width: number } | null>(null);
  const executionPlanPickerRef = useRef<HTMLDivElement | null>(null);
  const executionPlanPickerDragRef = useRef<{
    startX: number;
    startY: number;
    originX: number;
    originY: number;
    width: number;
    height: number;
  } | null>(null);
  const [isDraggingExecutionPlanPicker, setIsDraggingExecutionPlanPicker] = useState(false);
  const [stakeholderLoadingId, setStakeholderLoadingId] = useState<number | null>(null);
  const [stakeholderGenerating, setStakeholderGenerating] = useState(false);
  const [deleteStakeholderOpen, setDeleteStakeholderOpen] = useState(false);
  const [deletingStakeholderId, setDeletingStakeholderId] = useState<number | null>(null);
  const [reportDownloadId, setReportDownloadId] = useState<number | null>(null);
  const [rankResult, setRankResult] = useState<RankResult | null>(null);
  const [rankResultOpen, setRankResultOpen] = useState(false);
  const [reportSelection, setReportSelection] = useState<number[]>([]);
  const [reportOutput, setReportOutput] = useState<"pdf" | "email" | "both">("pdf");
  const [reportEmail, setReportEmail] = useState("");
  const [reportLoading, setReportLoading] = useState(false);
  const [useAllRuns, setUseAllRuns] = useState(false);
  const [compareSelectOpen, setCompareSelectOpen] = useState(false);
  const [decisionSelectOpen, setDecisionSelectOpen] = useState(false);
  const [usageRefreshing, setUsageRefreshing] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SavedResultSummary | null>(null);
  const [deleteAllGeneratedOpen, setDeleteAllGeneratedOpen] = useState(false);
  const [deletingAllGenerated, setDeletingAllGenerated] = useState(false);
  const [deletingGeneratedIds, setDeletingGeneratedIds] = useState<number[]>([]);
  const [loadedSavedMeta, setLoadedSavedMeta] = useState<SavedResultSummary | null>(null);
  const [deleteAllComparisonsOpen, setDeleteAllComparisonsOpen] = useState(false);
  const [deletingAllComparisons, setDeletingAllComparisons] = useState(false);
  const [deletingComparisonIds, setDeletingComparisonIds] = useState<number[]>([]);
  const [deleteComparisonOpen, setDeleteComparisonOpen] = useState(false);
  const [deletingComparisonId, setDeletingComparisonId] = useState<number | null>(null);
  const [decisionReport, setDecisionReport] = useState<DecisionSummaryReport | null>(null);
  const [deleteAllReportsOpen, setDeleteAllReportsOpen] = useState(false);
  const [deletingAllReports, setDeletingAllReports] = useState(false);
  const [deletingReportIds, setDeletingReportIds] = useState<number[]>([]);
  const [deleteDecisionOpen, setDeleteDecisionOpen] = useState(false);
  const [deletingDecisionId, setDeletingDecisionId] = useState<number | null>(null);
  const savedPanelOpen = savedPanelMode !== null;
  const savedPanelLocked =
    (savedPanelMode === "generated" && deletingAllGenerated) ||
    (savedPanelMode === "compare" && (compareLoading || deletingAllComparisons)) ||
    (savedPanelMode === "decision" && (reportLoading || deletingAllReports));
  const savedPanelStyle: React.CSSProperties = savedPanelPos
    ? { top: savedPanelPos.top, left: savedPanelPos.left, width: savedPanelPos.width }
    : {
        top: "50%",
        left: "50%",
        width: "min(768px, calc(100vw - 32px))",
        transform: "translate(-50%, -50%)",
      };
  const executionPlanPickerStyle: React.CSSProperties = executionPlanPickerPos
    ? { top: executionPlanPickerPos.top, left: executionPlanPickerPos.left, width: executionPlanPickerPos.width }
    : {
        top: "46%",
        left: "50%",
        width: "min(768px, calc(100vw - 32px))",
        transform: "translate(-50%, -50%)",
      };

  const apiLimit: number = isPremium ? 5 : 1;
  const emailLimit: number = isPremium ? 10 : 0;
  const tokenLimitFree = Number(process.env.NEXT_PUBLIC_TOKEN_LIMIT_FREE ?? "50000");
  const tokenLimitPremium = Number(process.env.NEXT_PUBLIC_TOKEN_LIMIT_PREMIUM ?? "500000");
  const tokenLimit = isPremium ? tokenLimitPremium : tokenLimitFree;
  const isApiLimited = (tokenUsage.api_calls_count || 0) >= apiLimit;
  const isEmailLimited = (tokenUsage.emails_sent_count || 0) >= emailLimit;
  const isTokenLimited = (tokenUsage.total_tokens || 0) >= tokenLimit;
  const usageTone = (value: number, limit: number) => {
    if (limit <= 0) return "text-gray-400 dark:text-gray-500";
    const ratio = value / limit;
    if (ratio >= 1) return "text-rose-600 dark:text-rose-400";
    if (ratio >= 0.8) return "text-amber-600 dark:text-amber-400";
    return "text-gray-900 dark:text-white";
  };
  const tokenTone = usageTone(tokenUsage.total_tokens || 0, tokenLimit);
  const apiTone = usageTone(tokenUsage.api_calls_count || 0, apiLimit);
  const emailTone = usageTone(tokenUsage.emails_sent_count || 0, emailLimit);
  const isStorageLimited = savedLimitBytes > 0 && savedUsageBytes >= savedLimitBytes;
  const formatBytes = (value: number) => {
    if (value >= 1024 * 1024 * 1024) return `${(value / (1024 * 1024 * 1024)).toFixed(1)}GB`;
    if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)}MB`;
    if (value >= 1024) return `${Math.round(value / 1024)}KB`;
    return `${value}B`;
  };
  const formatCurrency = (value?: number, currencyCode?: string) => {
    const amount = Number(value || 0);
    const code = (currencyCode || "USD").toUpperCase();
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: code,
      maximumFractionDigits: 0,
    }).format(amount);
  };
  const formatCurrencyOrNA = (value: number | null | undefined, currencyCode?: string) =>
    typeof value === "number" ? formatCurrency(value, currencyCode) : "N/A";
  const executionDecision = stakeholderReport?.dossier?.decision?.go_no_go || "conditional_go";
  const executionSupport = stakeholderReport?.dossier?.decision_support;
  const executionRecovery = executionSupport?.profitability_recovery;
  const executionGates = executionSupport?.gates;
  const executionReportTitle = stakeholderReport?.dossier?.decision?.winner?.title || "Untitled execution plan";
  const executionIndustryAssumption = Array.isArray(stakeholderReport?.assumptions)
    ? stakeholderReport?.assumptions?.find((item) => String(item?.key || "").toLowerCase() === "industry")
    : undefined;
  const executionIndustry = String(executionIndustryAssumption?.value || "").trim();
  const executionDecisionTone =
    executionDecision === "go"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : executionDecision === "no_go"
      ? "border-rose-500/40 bg-rose-500/10 text-rose-200"
      : "border-amber-500/40 bg-amber-500/10 text-amber-200";
  const executionDecisionLabel =
    executionDecision === "go" ? "Go" : executionDecision === "no_go" ? "No-Go" : "Conditional Go";
  const formatUsageCompact = (value: number) =>
    new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 0 }).format(value);
  const storageTone = usageTone(savedUsageBytes, savedLimitBytes);
  const storagePercent = savedLimitBytes > 0
    ? Math.min(100, Math.round((savedUsageBytes / savedLimitBytes) * 100))
    : 0;

  const isUsageLimitMessage = (message: string) => {
    const text = String(message || "").toLowerCase();
    return (
      text.includes("limit") ||
      text.includes("quota") ||
      text.includes("too many requests") ||
      text.includes("rate")
    );
  };

  const ensureOk = async (response: Response, fallbackMessage: string) => {
    if (response.ok) return;
    const data = await response.json().catch(() => ({}));
    const message =
      (typeof data?.detail === "string" && data.detail) ||
      (typeof data?.error === "string" && data.error) ||
      fallbackMessage;
    const err: any = new Error(message);
    err.status = response.status;
    throw err;
  };

  const handleApiActionError = (error: any, fallbackMessage: string) => {
    const message = String(error?.message || fallbackMessage);
    const status = Number(error?.status || 0);
    if (status === 429 || isUsageLimitMessage(message)) {
      pushNotice(message);
      return message;
    }
    pushNotice(message);
    return message;
  };

  const pushNotice = useCallback((message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setUsageNotices((prev) => [...prev, { id, message }].slice(-3));
    const timeoutId = window.setTimeout(() => {
      setUsageNotices((prev) => prev.filter((notice) => notice.id !== id));
    }, 6500);
    noticeTimeouts.current.push(timeoutId);
  }, []);

  useEffect(() => {
    return () => {
      noticeTimeouts.current.forEach((timeoutId) => window.clearTimeout(timeoutId));
    };
  }, []);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPageBootLoading(false);
    }, 700);
    return () => window.clearTimeout(timer);
  }, []);

  const formatSavedDate = (value: string) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString();
  };
  const labelForPersona = (toneId: string) => {
    if (!toneId) return "Neutral";
    return PERSONAS.find((p) => p.id === toneId)?.label ?? toneId;
  };
  const formatConstraints = (items: string[] = []) => {
    if (!items.length) return "None";
    const first = items.slice(0, 2);
    const extra = items.length - first.length;
    return extra > 0 ? `${first.join(", ")} +${extra}` : first.join(", ");
  };
  const formatModelList = (models: string[] = []) => {
    if (!models.length) return "None";
    const labels = Array.from(new Set(models.map(labelForModelId)));
    const first = labels.slice(0, 2);
    const extra = labels.length - first.length;
    return extra > 0 ? `${first.join(", ")} +${extra}` : first.join(", ");
  };
  const compareRunA = compareSelection.runA;
  const compareRunB = compareSelection.runB;
  const compareReady = Boolean(compareRunA && compareRunB);
  const selectedCompareRunA = compareRunA
    ? savedResults.find((item) => item.id === compareRunA)
    : null;
  const selectedCompareRunB = compareRunB
    ? savedResults.find((item) => item.id === compareRunB)
    : null;
  const savedPanelLoading =
    savedPanelMode === "generated"
      ? savedLoading
      : savedPanelMode === "compare"
      ? (savedLoading || comparisonsLoading)
      : savedPanelMode === "decision"
      ? (savedLoading || reportsLoading)
      : savedPanelMode === "stakeholder"
      ? stakeholderReportsLoading
      : false;
  const getSavedById = (id: number) => savedResults.find((item) => item.id === id);
  const formatRunLabel = (id: number) => {
    const item = getSavedById(id);
    if (!item) return `Run ${id}`;
    const industry = item.industry || "Saved result";
    return `${industry} • ${formatSavedDate(item.created_at)}`;
  };
  const formatRankReportTimestamp = (value: Date) => {
    const pad = (num: number) => String(num).padStart(2, "0");
    return [
      value.getUTCFullYear(),
      pad(value.getUTCMonth() + 1),
      pad(value.getUTCDate()),
      "_",
      pad(value.getUTCHours()),
      pad(value.getUTCMinutes()),
      pad(value.getUTCSeconds()),
    ].join("");
  };
  const buildRankReportFilename = (value = new Date()) => (
    `IdeaGen_Rank_Report_${formatRankReportTimestamp(value)}.pdf`
  );
  const extractFilename = (value: string | null) => {
    if (!value) return null;
    const match = /filename="?([^"]+)"?/.exec(value);
    return match?.[1] ?? null;
  };
  const ensureMinLoadingTime = async (startedAt: number, minMs = 350) => {
    const elapsed = Date.now() - startedAt;
    const remaining = Math.max(0, minMs - elapsed);
    if (remaining > 0) {
      await new Promise((resolve) => setTimeout(resolve, remaining));
    }
  };
  const reportHasSelection = useAllRuns || reportSelection.length > 0;
  const reportEmailRequired = reportOutput === "email" || reportOutput === "both";
  const reportCanSubmit = reportHasSelection && (!reportEmailRequired || reportEmail.trim().length > 0);
  const stakeholderFooterText = stakeholderReportsLoading
    ? "Loading execution plans"
    : stakeholderLoadingId !== null
    ? "Loading selected execution plan"
    : deletingStakeholderId !== null
    ? "Deleting execution plan"
    : savedStakeholderReports.length === 0
    ? "No execution plans saved yet."
    : "Select a saved execution plan, then click View.";
  const formatWinnerLabel = (comparison: SavedComparisonSummary) => {
    if (!comparison.winner_run_id) return "Tie";
    return formatRunLabel(comparison.winner_run_id);
  };

  const fetchSavedResults = useCallback(async () => {
    const startedAt = Date.now();
    try {
      setSavedLoading(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) return;
      const res = await fetch("/api/saved-results?limit=6", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`saved_results_${res.status}`);
      const data = await res.json();
      setSavedResults(Array.isArray(data?.results) ? data.results : []);
      setSavedUsageBytes(Number(data?.usage_bytes || 0));
      setSavedLimitBytes(Number(data?.limit_bytes || 0));
      const nextIds = new Set((Array.isArray(data?.results) ? data.results : []).map((r: any) => r.id));
      setCompareSelection((prev) => ({
        runA: prev.runA && nextIds.has(prev.runA) ? prev.runA : null,
        runB: prev.runB && nextIds.has(prev.runB) ? prev.runB : null,
      }));
      setReportSelection((prev) => prev.filter((id) => nextIds.has(id)));
    } catch {
      setSavedResults([]);
      setSavedUsageBytes(0);
      setSavedLimitBytes(0);
      setCompareSelection({ runA: null, runB: null });
      setReportSelection([]);
    } finally {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, 350 - elapsed);
      if (remaining > 0) {
        await new Promise((resolve) => setTimeout(resolve, remaining));
      }
      setSavedLoading(false);
    }
  }, [getToken]);

  const fetchSavedComparisons = useCallback(async () => {
    const startedAt = Date.now();
    try {
      setComparisonsLoading(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) return;
      const res = await fetch("/api/compare-results?limit=6", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`compare_results_${res.status}`);
      const data = await res.json();
      setSavedComparisons(Array.isArray(data?.comparisons) ? data.comparisons : []);
    } catch {
      setSavedComparisons([]);
    } finally {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, 350 - elapsed);
      if (remaining > 0) {
        await new Promise((resolve) => setTimeout(resolve, remaining));
      }
      setComparisonsLoading(false);
    }
  }, [getToken]);

  const fetchSavedReports = useCallback(async () => {
    const startedAt = Date.now();
    try {
      setReportsLoading(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) return;
      const res = await fetch("/api/rank-reports?limit=6", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`rank_reports_${res.status}`);
      const data = await res.json();
      setSavedReports(Array.isArray(data?.reports) ? data.reports : []);
    } catch {
      setSavedReports([]);
    } finally {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, 350 - elapsed);
      if (remaining > 0) {
        await new Promise((resolve) => setTimeout(resolve, remaining));
      }
      setReportsLoading(false);
    }
  }, [getToken]);

  const fetchSavedStakeholderReports = useCallback(async () => {
    const startedAt = Date.now();
    try {
      setStakeholderReportsLoading(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) return;
      const res = await fetch("/api/stakeholder-reports?limit=6", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`stakeholder_reports_${res.status}`);
      const data = await res.json();
      setSavedStakeholderReports(Array.isArray(data?.reports) ? data.reports : []);
    } catch {
      setSavedStakeholderReports([]);
    } finally {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, 350 - elapsed);
      if (remaining > 0) {
        await new Promise((resolve) => setTimeout(resolve, remaining));
      }
      setStakeholderReportsLoading(false);
    }
  }, [getToken]);

  useEffect(() => {
    if (isSignedIn) {
      fetchSavedResults();
      fetchSavedComparisons();
      fetchSavedReports();
      fetchSavedStakeholderReports();
      return;
    }
    setSavedResults([]);
    setSavedUsageBytes(0);
    setSavedLimitBytes(0);
    setCompareSelection({ runA: null, runB: null });
    setReportSelection([]);
    setCompareResult(null);
    setSavedComparisons([]);
    setSavedReports([]);
    setSavedStakeholderReports([]);
    setStakeholderReport(null);
    setUseAllRuns(false);
  }, [fetchSavedResults, fetchSavedComparisons, fetchSavedReports, fetchSavedStakeholderReports, isSignedIn]);

  useEffect(() => {
    if (decisionReport?.id) return;
    setExecutionPlanPickerOpen(false);
    setExecutionPlanSelectedKey(null);
    setExecutionPlanGeneratedKeys([]);
  }, [decisionReport?.id]);

  useEffect(() => {
    if (initialUsage && typeof initialUsage.total_tokens === 'number') {
      setTokenUsage(initialUsage);
    }
  }, [initialUsage]);

  const refreshUsage = useCallback(async (showLoading = false) => {
    const startedAt = Date.now();
    try {
      if (showLoading) setUsageRefreshing(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) return;
      const res = await fetch("/api/subscription", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.usage) {
        setTokenUsage((prev: any) => ({ ...prev, ...data.usage }));
      }
    } catch {
      // silent refresh
    } finally {
      if (showLoading) {
        const elapsed = Date.now() - startedAt;
        const remaining = Math.max(0, 500 - elapsed);
        if (remaining > 0) {
          await new Promise((resolve) => setTimeout(resolve, remaining));
        }
        setUsageRefreshing(false);
      }
    }
  }, [getToken]);

  useEffect(() => {
    const interval = setInterval(async () => {
      await refreshUsage(false);
    }, 3000);
    return () => clearInterval(interval);
  }, [refreshUsage]);

  const [email, setEmail] = useState("");
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailStatus, setEmailStatus] = useState("");

  const [recoLoading, setRecoLoading] = useState(false);
  const [recoHtml, setRecoHtml] = useState<string>("");

  const [pdfLoading, setPdfLoading] = useState(false);
  const [executionPresentationLoading, setExecutionPresentationLoading] = useState(false);

  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const FREE_ALLOWED_CONSTRAINTS = 3; // first 3 options (including "None")
  const FREE_MAX_CONSTRAINTS = 1;
  const FREE_MAX_MODELS = 1;

  const scrollToPricing = () => {
    if (typeof window === "undefined") return;
    const el = document.getElementById("pricing-table");
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    window.location.hash = "pricing-table";
  };

  const handleAccountClick = () => {
    // same “account” surface users expect from the avatar menu
    if (!isSignedIn) {
      openSignIn();            // if logged out, prompt sign-in
      return;
    }
    openUserProfile();         // if logged in, open the Clerk profile modal
  };

  const addUsage = (newUsage: any) => {
    if (!newUsage) return;
    setTokenUsage((prev: any) => ({
      ...prev,
      total_tokens: (prev.total_tokens || 0) + (newUsage.total_tokens || 0),
      prompt_tokens: (prev.prompt_tokens || 0) + (newUsage.prompt_tokens || 0),
      completion_tokens: (prev.completion_tokens || 0) + (newUsage.completion_tokens || 0),
      api_calls_count: newUsage.api_calls_count ?? prev.api_calls_count,
      emails_sent_count: newUsage.emails_sent_count ?? prev.emails_sent_count,
    }));
  };

  const clearGeneratedResults = () => {
    setResults({});
    setActiveTab("");
    setRankResult(null);
    setRankResultOpen(false);
    setLoadedSavedId(null);
    setLoadedSavedSnapshot(null);
    setLoadedSavedMeta(null);
  };

  const clearCompareResults = () => {
    setCompareResult(null);
  };

  const clearDecisionReport = () => {
    setDecisionReport(null);
  };

  const clearStakeholderReport = () => {
    setStakeholderReport(null);
  };

  const buildSavePayload = () => ({
    industry,
    constraints,
    tone,
    models: Object.keys(results),
    results,
    rank_result: rankResult,
  });

  const buildSaveSnapshot = (payload: ReturnType<typeof buildSavePayload>) => {
    const normalizedResults: Record<string, string> = {};
    Object.keys(payload.results || {})
      .sort()
      .forEach((key) => {
        normalizedResults[key] = String(payload.results[key] ?? "");
      });

    const normalized = {
      industry: payload.industry || "",
      tone: payload.tone || "",
      constraints: Array.isArray(payload.constraints) ? payload.constraints : [],
      models: Array.isArray(payload.models) ? payload.models.slice().sort() : [],
      results: normalizedResults,
      rank_result: payload.rank_result ?? null,
    };

    return JSON.stringify(normalized);
  };

  const saveCurrentResults = async (
    override?: ReturnType<typeof buildSavePayload>,
    options: { silent?: boolean } = {}
  ) => {
    const payload = override ?? buildSavePayload();
    if (Object.keys(payload.results || {}).length === 0) return;
    try {
      setSavingResults(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const snapshot = buildSaveSnapshot(payload);
      if (loadedSavedId && loadedSavedSnapshot && snapshot === loadedSavedSnapshot) {
        if (!options.silent) {
          pushNotice("No changes to save.");
        }
        return;
      }
      const res = await fetch("/api/saved-results", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let message = "Failed to save results. Please try again.";
        try {
          const data = await res.json();
          if (data?.detail) message = data.detail;
        } catch {
          // keep fallback message
        }
        throw new Error(message);
      }
      const saved = await res.json().catch(() => ({}));
      const nextId = saved?.id ?? null;
      setLoadedSavedId(nextId);
      setLoadedSavedSnapshot(snapshot);
      if (nextId) {
        setLoadedSavedMeta({
          id: nextId,
          created_at: saved?.created_at || new Date().toISOString(),
          industry: payload.industry,
          tone: payload.tone,
          constraints: payload.constraints,
          models: Array.isArray(payload.models) && payload.models.length > 0 ? payload.models : Object.keys(payload.results || {}),
        });
      }
      fetchSavedResults();
      if (!options.silent) {
        pushNotice("Results saved. You can reload them anytime.");
      }
    } catch (e: any) {
      if (!options.silent) {
        pushNotice(e?.message || "Failed to save results. Please try again.");
      } else {
        pushNotice(e?.message || "Auto-save failed. Please try again.");
      }
    } finally {
      setSavingResults(false);
    }
  };

  const loadSavedResult = async (savedId: number) => {
    const startedAt = Date.now();
    try {
      setSavedPanelMode(null);
      setResultsHydrating(true);
      setLoadingSavedId(savedId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/saved-results/${savedId}`, {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`load_failed_${res.status}`);
      const data = await res.json();
      const savedResultsData = data?.results || {};
      const savedRankResult = data?.rank_result ?? null;
      const resultKeys = Object.keys(savedResultsData);
      const normalizeModelIds = (ids: string[]) => {
        const openaiId = MODELS.find((m) => m.label === "OpenAI")?.id;
        const geminiId = MODELS.find((m) => m.label === "Gemini")?.id;
        const deepseekId = MODELS.find((m) => m.label === "DeepSeek")?.id;
        const grokId = MODELS.find((m) => m.label === "Grok")?.id;
        const normalized = ids.map((id) => {
          if (MODELS.some((m) => m.id === id)) return id;
          const lower = String(id || "").toLowerCase();
          if (lower.startsWith("gpt-") || lower.startsWith("o-")) return openaiId || id;
          if (lower.startsWith("gemini-")) return geminiId || id;
          if (lower.startsWith("deepseek-")) return deepseekId || id;
          if (lower.startsWith("grok-")) return grokId || id;
          return id;
        });
        return Array.from(new Set(normalized.filter(Boolean)));
      };

      setResults(savedResultsData);
      setActiveTab(resultKeys[0] || "");
      setResultsView("generated");
      setLoadedSavedId(savedId);
      setLoadedSavedSnapshot(
        buildSaveSnapshot({
          industry: data?.industry || "",
          constraints: Array.isArray(data?.constraints) ? data.constraints : [],
          tone: data?.tone || "",
          models: resultKeys,
          results: savedResultsData,
          rank_result: savedRankResult,
        })
      );
      setLoadedSavedMeta({
        id: savedId,
        created_at: data?.created_at || new Date().toISOString(),
        industry: data?.industry || "",
        tone: data?.tone || "",
        constraints: Array.isArray(data?.constraints) ? data.constraints : [],
        models: Array.isArray(data?.models) && data.models.length > 0 ? data.models : resultKeys,
      });
      setRankResult(savedRankResult);
      setRankResultOpen(false);
      if (data?.industry) setIndustry(data.industry);
      if (Array.isArray(data?.constraints) && data.constraints.length > 0) {
        setConstraints(data.constraints);
      } else {
        setConstraints([CONSTRAINTS[0]]);
      }
      if (data?.tone) setTone(data.tone);
      const nextModels = Array.isArray(data?.models) && data.models.length > 0 ? data.models : resultKeys;
      const normalizedModels = normalizeModelIds(nextModels);
      if (normalizedModels.length > 0) setSelectedModels(normalizedModels);
      pushNotice("Saved results loaded.");
    } catch {
      pushNotice("Failed to load saved results.");
    } finally {
      await ensureMinLoadingTime(startedAt, 600);
      setResultsHydrating(false);
      setLoadingSavedId(null);
    }
  };

  const deleteSavedResult = async (savedId: number) => {
    try {
      setDeletingSavedId(savedId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/saved-results/${savedId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_failed_${res.status}`);
      pushNotice("Saved result deleted.");
      setCompareSelection((prev) => ({
        runA: prev.runA === savedId ? null : prev.runA,
        runB: prev.runB === savedId ? null : prev.runB,
      }));
      setReportSelection((prev) => prev.filter((id) => id !== savedId));
      if (loadedSavedId === savedId) {
        setLoadedSavedId(null);
        setLoadedSavedSnapshot(null);
        setLoadedSavedMeta(null);
      }
      fetchSavedResults();
    } catch {
      pushNotice("Failed to delete saved result.");
    } finally {
      setDeletingSavedId(null);
    }
  };

  const deleteAllGeneratedResults = async () => {
    const ids = savedResults.map((item) => item.id);
    if (!ids.length) {
      setDeleteAllGeneratedOpen(false);
      return;
    }
    const startedAt = Date.now();
    try {
      setDeleteAllGeneratedOpen(false);
      setDeleteTarget(null);
      setDeletingAllGenerated(true);
      setDeletingGeneratedIds(ids);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/saved-results", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_all_saved_failed_${res.status}`);
      const data = await res.json().catch(() => ({}));
      const deletedCount = Number(data?.count || ids.length);
      await ensureMinLoadingTime(startedAt, 500);
      setSavedResults([]);
      setCompareSelection({ runA: null, runB: null });
      setReportSelection([]);
      setLoadedSavedId(null);
      setLoadedSavedSnapshot(null);
      setLoadedSavedMeta(null);
      setResults({});
      setActiveTab("");
      setRankResult(null);
      setRankResultOpen(false);
      setSavedUsageBytes(0);
      pushNotice(`Deleted ${deletedCount} saved result(s).`);
      fetchSavedResults();
    } catch {
      pushNotice("Failed to delete generated results.");
    } finally {
      setDeletingGeneratedIds([]);
      setDeletingAllGenerated(false);
    }
  };

  const deleteAllComparisons = async () => {
    const ids = savedComparisons.map((item) => item.id);
    if (!ids.length) {
      setDeleteAllComparisonsOpen(false);
      return;
    }
    const startedAt = Date.now();
    try {
      setDeleteAllComparisonsOpen(false);
      setDeleteComparisonOpen(false);
      setDeletingAllComparisons(true);
      setDeletingComparisonIds(ids);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/compare-results", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_all_compare_failed_${res.status}`);
      const data = await res.json().catch(() => ({}));
      const deletedCount = Number(data?.count || ids.length);
      await ensureMinLoadingTime(startedAt, 500);
      setSavedComparisons([]);
      setCompareResult(null);
      setCompareError(null);
      pushNotice(`Deleted ${deletedCount} comparison(s).`);
      fetchSavedComparisons();
    } catch {
      pushNotice("Failed to delete comparisons.");
    } finally {
      setDeletingComparisonIds([]);
      setDeletingAllComparisons(false);
    }
  };

  const deleteComparison = async (comparisonId: number) => {
    try {
      setDeletingComparisonId(comparisonId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/compare-results/${comparisonId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_compare_failed_${res.status}`);
      pushNotice("Comparison deleted.");
      setCompareResult((prev) => (prev?.comparison_id === comparisonId ? null : prev));
      fetchSavedComparisons();
    } catch {
      pushNotice("Failed to delete comparison.");
    } finally {
      setDeletingComparisonId(null);
    }
  };

  const deleteAllDecisionReports = async () => {
    const ids = savedReports.map((item) => item.id);
    if (!ids.length) {
      setDeleteAllReportsOpen(false);
      return;
    }
    const startedAt = Date.now();
    try {
      setDeleteAllReportsOpen(false);
      setDeleteDecisionOpen(false);
      setDeletingAllReports(true);
      setDeletingReportIds(ids);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/rank-reports", {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_all_reports_failed_${res.status}`);
      const data = await res.json().catch(() => ({}));
      const deletedCount = Number(data?.count || ids.length);
      await ensureMinLoadingTime(startedAt, 500);
      setSavedReports([]);
      setDecisionReport(null);
      pushNotice(`Deleted ${deletedCount} decision report(s).`);
      fetchSavedReports();
    } catch {
      pushNotice("Failed to delete decision reports.");
    } finally {
      setDeletingReportIds([]);
      setDeletingAllReports(false);
    }
  };

  const deleteDecisionReport = async (reportId: number) => {
    try {
      setDeletingDecisionId(reportId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/rank-reports/${reportId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) throw new Error(`delete_report_failed_${res.status}`);
      pushNotice("Decision report deleted.");
      setDecisionReport((prev) => (prev?.id === reportId ? null : prev));
      fetchSavedReports();
    } catch {
      pushNotice("Failed to delete decision report.");
    } finally {
      setDeletingDecisionId(null);
    }
  };

  const runCompare = async (runA?: number, runB?: number, fromSavedView = false) => {
    const startedAt = Date.now();
    const resolvedA = runA ?? compareSelection.runA;
    const resolvedB = runB ?? compareSelection.runB;
    if (!resolvedA || !resolvedB) return;
    try {
      if (fromSavedView) {
        setSavedPanelMode(null);
        setResultsHydrating(true);
      }
      setCompareLoading(true);
      setCompareError(null);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/compare-results", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify({ run_a_id: resolvedA, run_b_id: resolvedB }),
      });
      await ensureOk(res, "Compare failed.");
      const data = await res.json();
      setCompareError(null);
      await ensureMinLoadingTime(startedAt, fromSavedView ? 600 : 350);
      setCompareResult(data);
      setResultsView("insights");
      pushNotice(data?.cached ? "Loaded saved comparison." : "Comparison generated and saved.");
      if (!fromSavedView) setSavedPanelMode(null);
      fetchSavedComparisons();
    } catch (e: any) {
      handleApiActionError(e, "Failed to compare saved results.");
      const message = e?.message || "Failed to compare saved results.";
      setCompareError(message);
    } finally {
      if (fromSavedView) setResultsHydrating(false);
      setCompareLoading(false);
    }
  };

  const updateCompareSelection = (slot: "a" | "b", value: string) => {
    const runId = Number(value);
    const nextId = Number.isFinite(runId) && runId > 0 ? runId : null;
    setCompareSelection((prev) => {
      let nextA = prev.runA;
      let nextB = prev.runB;
      if (slot === "a") {
        nextA = nextId;
        if (nextA && nextA === nextB) nextB = null;
      } else {
        nextB = nextId;
        if (nextB && nextB === nextA) nextA = null;
      }
      return { runA: nextA, runB: nextB };
    });
  };

  const toggleReportSelection = (savedId: number) => {
    setReportSelection((prev) => {
      if (prev.includes(savedId)) {
        return prev.filter((id) => id !== savedId);
      }
      if (prev.length >= 5) {
        pushNotice("Select up to 5 runs for a report.");
        return prev;
      }
      return [...prev, savedId];
    });
  };

  const runAgenticReport = async () => {
    if (!reportHasSelection) {
      pushNotice("Select runs or choose all saved runs for the report.");
      return;
    }
    if ((reportOutput === "email" || reportOutput === "both") && !reportEmail) {
      pushNotice("Enter an email address for delivery.");
      return;
    }
    try {
      setReportLoading(true);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/rank-report", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          run_ids: useAllRuns ? [] : reportSelection,
          output: reportOutput,
          email: reportEmail || null,
          include_all_runs: useAllRuns,
        }),
      });
      await ensureOk(res, "Failed to generate report.");
      const contentType = res.headers.get("content-type") || "";
      const cached = res.headers.get("x-report-cached") === "true";
      if (contentType.includes("application/pdf")) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        const disposition = res.headers.get("content-disposition");
        a.download = extractFilename(disposition) || buildRankReportFilename();
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        const emailSent = res.headers.get("x-report-email-sent") === "true";
        const emailFailed = res.headers.get("x-report-email-failed") === "true";
        if (emailSent) {
          pushNotice(cached ? "Cached report downloaded and emailed." : "Report downloaded and emailed.");
        } else {
          pushNotice(cached ? "Cached report downloaded." : "Report downloaded.");
        }
        if (emailFailed) {
          pushNotice("Email delivery failed. Please try again.");
        }
      } else {
        const data = await res.json();
        if (data?.status === "sent") {
          pushNotice(data?.cached ? "Cached report emailed." : "Report emailed.");
        } else {
          pushNotice(data?.cached ? "Cached report generated." : "Report generated.");
        }
        if (data?.email_failed) {
          pushNotice("Email delivery failed. Please try again.");
        }
      }
      await fetchSavedReports();
      try {
        const latestRes = await fetch("/api/rank-reports?limit=1", {
          headers: { Authorization: `Bearer ${jwt}` },
        });
        if (latestRes.ok) {
          const latestData = await latestRes.json();
          const latest = Array.isArray(latestData?.reports) ? latestData.reports[0] : null;
          if (latest?.id) {
            const reportRes = await fetch(`/api/rank-reports/${latest.id}`, {
              headers: { Authorization: `Bearer ${jwt}` },
            });
            if (reportRes.ok) {
              const reportData = await reportRes.json();
              setDecisionReport(reportData);
            }
          }
        }
      } catch {
        // ignore load failures; saved list is still refreshed
      }
      setResultsView("decision");
      setSavedPanelMode(null);
    } catch (e: any) {
      handleApiActionError(e, "Failed to generate report.");
    } finally {
      setReportLoading(false);
    }
  };

  const downloadSavedReport = async (reportId: number) => {
    try {
      setReportDownloadId(reportId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/rank-reports/${reportId}/pdf`, {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Failed to download report.");
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const disposition = res.headers.get("content-disposition");
      a.download = extractFilename(disposition) || buildRankReportFilename();
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      const runsMissing = res.headers.get("x-report-runs-missing") === "true";
      pushNotice(runsMissing ? "Report downloaded (some runs missing)." : "Report downloaded.");
    } catch (e: any) {
      pushNotice(e?.message || "Failed to download report.");
    } finally {
      setReportDownloadId(null);
    }
  };

  const loadStakeholderReport = async (reportId: number, fromSavedView = false) => {
    const startedAt = Date.now();
    let loaded = false;
    try {
      if (fromSavedView) {
        setSavedPanelMode(null);
        setResultsHydrating(true);
      }
      setStakeholderLoadingId(reportId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/stakeholder-reports/${reportId}`, {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Failed to load execution plan.");
      }
      const data = await res.json();
      await ensureMinLoadingTime(startedAt, fromSavedView ? 600 : 350);
      setStakeholderReport(data);
      setResultsView("stakeholder");
      loaded = true;
    } catch (e: any) {
      pushNotice(e?.message || "Failed to load execution plan.");
    } finally {
      if (fromSavedView) {
        setResultsHydrating(false);
      }
      if (loaded) {
        pushNotice("Execution plan loaded.");
      }
      setStakeholderLoadingId(null);
    }
  };

  const openExecutionPlanPicker = async () => {
    if (!decisionReport?.id) {
      pushNotice("Generate or load a Decision Summary Report first.");
      return;
    }
    if (!executionPlanOptions.length) {
      pushNotice("No ranked reports available for Execution Plan generation.");
      return;
    }
    setExecutionPlanPickerOpen(true);
    setExecutionPlanPickerLoading(true);
    setExecutionPlanGeneratedKeys([]);
    setExecutionPlanPickerError(null);
    try {
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const listRes = await fetch("/api/stakeholder-reports?limit=200", {
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!listRes.ok) throw new Error("failed_to_list_execution_plans");
      const listData = await listRes.json();
      const allReports: StakeholderReportSummary[] = Array.isArray(listData?.reports) ? listData.reports : [];
      const relatedReports = allReports.filter(
        (report: StakeholderReportSummary) =>
          report.source_type === "decision_report" && Number(report.source_id) === Number(decisionReport.id)
      );
      if (!relatedReports.length) return;
      const optionKeys = await Promise.all(
        relatedReports.map(async (report: StakeholderReportSummary) => {
          try {
            const res = await fetch(`/api/stakeholder-reports/${report.id}`, {
              headers: { Authorization: `Bearer ${jwt}` },
            });
            if (!res.ok) return null;
            const data = await res.json();
            const runId = Number(data?.dossier?.provenance?.selected_run_id);
            const modelId = String(data?.dossier?.provenance?.selected_model_id || "").trim();
            if (!Number.isFinite(runId) || runId <= 0 || !modelId) return null;
            return makeExecutionPlanOptionKey(runId, modelId);
          } catch {
            return null;
          }
        })
      );
      const uniqueKeys = Array.from(
        new Set(optionKeys.filter((key): key is string => typeof key === "string" && key.length > 0))
      );
      setExecutionPlanGeneratedKeys(uniqueKeys);
    } catch {
      // Keep picker usable even if we cannot resolve previously generated reports.
      setExecutionPlanGeneratedKeys([]);
    } finally {
      setExecutionPlanPickerLoading(false);
    }
  };

  const runStakeholderReport = async (selectedOption?: { runId: number; modelId: string } | null) => {
    if (!decisionReport?.id) {
      pushNotice("Generate or load a Decision Summary Report first.");
      return;
    }
    const fallbackOption = executionPlanOptions.find((item) => item.optionKey === executionPlanSelectedKey);
    const resolvedRunId = Number(
      selectedOption?.runId ?? fallbackOption?.runId ?? decisionReport.report?.ranked_runs?.[0]?.run_id ?? 0
    );
    const resolvedModelId = String(selectedOption?.modelId ?? fallbackOption?.modelId ?? "").trim();
    if (!Number.isFinite(resolvedRunId) || resolvedRunId <= 0) {
      pushNotice("Select one ranked report before generating the Execution Plan.");
      return;
    }
    if (!resolvedModelId) {
      pushNotice("Select one model output before generating the Execution Plan.");
      return;
    }
    let generated = false;
    try {
      setStakeholderGenerating(true);
      setExecutionPlanPickerError(null);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch("/api/stakeholder-report", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          source: {
            mode: "decision_report",
            decision_report_id: decisionReport.id,
            selected_run_id: resolvedRunId,
            selected_model_id: resolvedModelId,
          },
          scenario_profile: "base",
          horizon_months: 12,
          currency: "USD",
          region: "US",
          output: "json",
        }),
      });
      await ensureOk(res, "Failed to generate execution plan.");
      const data = await res.json();
      await fetchSavedStakeholderReports();
      if (data?.id) {
        await loadStakeholderReport(data.id);
      } else {
        setStakeholderReport(data);
        setResultsView("stakeholder");
      }
      generated = true;
      pushNotice("Execution plan generated.");
    } catch (e: any) {
      const message = handleApiActionError(e, "Failed to generate execution plan.");
      setExecutionPlanPickerError(message);
    } finally {
      setStakeholderGenerating(false);
      if (generated) {
        setExecutionPlanPickerOpen(false);
      }
    }
  };

  const deleteStakeholderReport = async (reportId: number) => {
    try {
      setDeletingStakeholderId(reportId);
      const jwt = await getToken(tokenOptions());
      if (!jwt) throw new Error("no_token");
      const res = await fetch(`/api/stakeholder-reports/${reportId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${jwt}` },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail || "Failed to delete execution plan.");
      }
      setStakeholderReport((prev) => (prev?.id === reportId ? null : prev));
      setDeleteStakeholderOpen(false);
      await fetchSavedStakeholderReports();
      pushNotice("Execution plan deleted.");
    } catch (e: any) {
      pushNotice(e?.message || "Failed to delete execution plan.");
    } finally {
      setDeletingStakeholderId(null);
    }
  };


  const openUpgrade = () => setUpgradeOpen(true);

  const upgradeTo = () => {
    // If you have a billing route, change this:
    window.location.href = "/pricing";
  };

  // lock scrolling while full-page loader is open
  useEffect(() => {
    if (!isLoading) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [isLoading]);

  const handleModelToggle = (modelId: string, wantChecked: boolean) => {
    setSelectedModels((prev) => {
      const checked = prev.includes(modelId);
      const nextChecked = wantChecked ?? !checked;

      if (!nextChecked) return prev.filter((id) => id !== modelId);

      // turning ON
      if (!isPremium && prev.length >= FREE_MAX_MODELS) {
        // keep UI premium; gate interaction
        if (planLoaded) openUpgrade();
        return prev;
      }

      return [...prev, modelId];
    });
  };

  const labelForModelId = (modelId: string) => {
    const byId = MODELS.find((m) => m.id === modelId);
    if (byId) return byId.label;
    const lower = String(modelId || "").toLowerCase();
    if (lower.startsWith("gpt-") || lower.startsWith("o-")) return "OpenAI";
    if (lower.startsWith("gemini-")) return "Google Gemini";
    if (lower.startsWith("deepseek-")) return "Deepseek";
    if (lower.startsWith("grok-")) return "Grok";
    return "Model";
  };

  const extractTitleFromHtml = (value: string) => {
    if (!value) return "Untitled result";
    const match = value.match(/<h[1-3][^>]*>(.*?)<\/h[1-3]>/i);
    const strip = (input: string) =>
      input.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
    let title = match ? strip(match[1]) : strip(value);
    if (title) {
      const lower = title.toLowerCase();
      for (const marker of ["title:", "idea:", "concept:"]) {
        const idx = lower.indexOf(marker);
        if (idx !== -1) {
          const snippet = title.slice(idx + marker.length).trim();
          if (snippet) {
            title = snippet;
            break;
          }
        }
      }
    }
    if (!title) return "Untitled result";
    return title.length > 80 ? `${title.slice(0, 77).trim()}...` : title;
  };

  const getRunOutputsMeta = (run?: RunSnapshot) => {
    if (!run) return [];
    const results = run.results || {};
    const modelIds = (run.models && run.models.length ? run.models : Object.keys(results)).filter(Boolean);
    const titleMap = run.rank_result?.title_map || {};
    return modelIds.map((modelId) => {
      const titleFromMap = titleMap[modelId];
      const titleFromHtml = results[modelId] ? extractTitleFromHtml(results[modelId]) : "";
      const title = titleFromMap || titleFromHtml || "Untitled result";
      return {
        modelId,
        modelLabel: labelForModelId(modelId),
        title,
      };
    });
  };

  const getTopModelIdForRun = (run?: RunSnapshot) => {
    if (!run) return "";
    const ranked = Array.isArray(run.rank_result?.ranked_models)
      ? [...(run.rank_result?.ranked_models || [])]
      : [];
    ranked.sort((a, b) => (a.rank || 0) - (b.rank || 0));
    return ranked[0]?.model_id || "";
  };

  const selectedModelLabels = useMemo(
    () => selectedModels.map(labelForModelId).filter(Boolean),
    [selectedModels]
  );

  const makeExecutionPlanOptionKey = useCallback(
    (runId: number, modelId: string) => `${runId}::${String(modelId || "").trim()}`,
    []
  );

  const executionPlanOptions = useMemo(() => {
    const rankedRuns = Array.isArray(decisionReport?.report?.ranked_runs)
      ? decisionReport?.report?.ranked_runs
      : [];
    const runSnapshots = Array.isArray(decisionReport?.runs_snapshot)
      ? decisionReport?.runs_snapshot
      : [];
    const rankedItems = rankedRuns
      .map((item, originalIndex) => {
        const runId = Number(item?.run_id);
        if (!Number.isFinite(runId) || runId <= 0) return null;
        const score = typeof item?.score === "number" ? item.score : null;
        const run = runSnapshots.find((r) => Number(r?.id) === runId);
        const outputs = run && run.results && typeof run.results === "object"
          ? getRunOutputsMeta(run)
          : [];
        const rankedModels = Array.isArray(run?.rank_result?.ranked_models)
          ? run?.rank_result?.ranked_models
          : [];
        const modelScoreMap = new Map<string, number>();
        rankedModels.forEach((rankedItem) => {
          const modelId = String(rankedItem?.model_id || "").trim();
          const score = Number(rankedItem?.score);
          if (modelId && Number.isFinite(score)) {
            modelScoreMap.set(modelId, score);
          }
        });
        const topModelId = getTopModelIdForRun(run);
        const personaLabel = run ? labelForPersona(run.tone || "") : "Not specified";
        const constraintsLabel = run ? formatConstraints(run.constraints || []) : "Not specified";
        const modelLabel = run ? formatModelList(run.models || []) : "Not specified";
        const industryLabel = run?.industry || "Saved run";
        const runLabel = run
          ? `${run.industry || "Saved run"} • ${formatSavedDate(run.created_at || "")}`
          : formatRunLabel(runId);
        return {
          runId,
          score,
          rationale: String(item?.rationale || "").trim(),
          outputs,
          modelScoreMap,
          topModelId,
          runLabel,
          industryLabel,
          personaLabel,
          constraintsLabel,
          modelLabel,
          originalIndex,
        };
      })
      .filter((item): item is NonNullable<typeof item> => Boolean(item));

    rankedItems.sort((a, b) => {
      const aHas = typeof a.score === "number";
      const bHas = typeof b.score === "number";
      if (aHas && bHas && a.score !== b.score) return (b.score as number) - (a.score as number);
      if (aHas !== bHas) return bHas ? 1 : -1;
      return a.originalIndex - b.originalIndex;
    });

    const expanded: Array<{
      optionKey: string;
      runId: number;
      modelId: string;
      modelLabel: string;
      title: string;
      modelScore?: number;
      runRank: number;
      runScore: number | null;
      isWinnerRun: boolean;
      isTopOutput: boolean;
      rationale: string;
      runLabel: string;
      industryLabel: string;
      personaLabel: string;
      constraintsLabel: string;
      modelSetLabel: string;
    }> = [];

    rankedItems.forEach((item, runIndex) => {
      const orderedOutputs = [...item.outputs].sort((a, b) => {
        const aTop = a.modelId === item.topModelId ? 1 : 0;
        const bTop = b.modelId === item.topModelId ? 1 : 0;
        return bTop - aTop;
      });
      const outputs = orderedOutputs.length
        ? orderedOutputs
        : [{ modelId: "", modelLabel: "Model", title: item.runLabel }];
          outputs.forEach((output) => {
            expanded.push({
              optionKey: makeExecutionPlanOptionKey(item.runId, output.modelId),
              runId: item.runId,
              modelId: output.modelId,
              modelLabel: output.modelLabel,
              title: output.title,
              modelScore: item.modelScoreMap.get(output.modelId),
              runRank: runIndex + 1,
              runScore: item.score,
              isWinnerRun: runIndex === 0,
              isTopOutput: output.modelId === item.topModelId,
          rationale: item.rationale,
          runLabel: item.runLabel,
          industryLabel: item.industryLabel,
          personaLabel: item.personaLabel,
          constraintsLabel: item.constraintsLabel,
          modelSetLabel: item.modelLabel,
        });
      });
    });

    return expanded;
  }, [decisionReport, makeExecutionPlanOptionKey]);

  const executionPlanGeneratedKeySet = useMemo(
    () => new Set(executionPlanGeneratedKeys),
    [executionPlanGeneratedKeys]
  );

  const hasSelectableExecutionPlanOption = executionPlanOptions.some(
    (item) => !executionPlanGeneratedKeySet.has(item.optionKey)
  );

  useEffect(() => {
    if (!executionPlanPickerOpen) return;
    const firstSelectable = executionPlanOptions.find((item) => !executionPlanGeneratedKeySet.has(item.optionKey));
    setExecutionPlanSelectedKey((prev) => {
      if (prev && executionPlanOptions.some((item) => item.optionKey === prev && !executionPlanGeneratedKeySet.has(item.optionKey))) {
        return prev;
      }
      return firstSelectable?.optionKey ?? null;
    });
  }, [executionPlanPickerOpen, executionPlanOptions, executionPlanGeneratedKeySet]);

  const generateIdeas = async () => {
    if (selectedModels.length === 0) return alert("Please select at least one AI model.");

    // backend safety: free users send only allowed data
    const safeConstraints = !isPremium
      ? constraints.filter((c) => CONSTRAINTS.indexOf(c) >= 0).slice(0, FREE_MAX_CONSTRAINTS).map((c) => c)
      : constraints;

    const safeTone = !isPremium ? PERSONAS[0].id : tone;

    const safeModels = !isPremium ? selectedModels.slice(0, FREE_MAX_MODELS) : selectedModels;

    // Map IDs to Labels for the backend (which resolves them dynamically)
    const payloadModels = safeModels
      .map((id) => MODELS.find((m) => m.id === id)?.label)
      .filter(Boolean);

    // Always return to Generated Results after a new run is requested.
    setResultsView("generated");
    setIsLoading(true);
    setResults({});
    setActiveTab(safeModels[0]);
    setEmailStatus("");
    setRankResult(null);
    setRankResultOpen(false);
    setLoadedSavedId(null);
    setLoadedSavedSnapshot(null);
    setDeleteTarget(null);
    setLoadedSavedMeta(null);
    setDeleteComparisonOpen(false);
    setDecisionReport(null);
    setDeleteStakeholderOpen(false);

    const jwt = await getToken(tokenOptions());

    const payload: any = { 
      industry, 
      constraints: safeConstraints, 
      tone: safeTone, 
      models: payloadModels,
      temperature: isPremium ? temperature : 0.7,
      top_p: isPremium ? topP : 0.9
    };

    try {
      const response = await fetch("/api", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      await ensureOk(response, "Failed to generate ideas.");
      const data = await response.json();
      
      const resultsData = data.results || data;
      setResults(resultsData);
      if (data.rank_result) {
        setRankResult(data.rank_result);
      } else {
        setRankResult(null);
      }
      addUsage(data.usage);
      
      const keys = Object.keys(resultsData);
      if (keys.length > 0) setActiveTab(keys[0]);

      void saveCurrentResults(
        {
          industry,
          constraints: safeConstraints,
          tone: safeTone,
          models: Object.keys(resultsData),
          results: resultsData,
          rank_result: data.rank_result ?? null,
        },
        { silent: true }
      );
    } catch (e: any) {
      handleApiActionError(e, "Failed to generate ideas.");
    } finally {
      setIsLoading(false);
    }
  };

  const recommendCombination = async () => {
    if (!isPremium) {
      if (planLoaded) scrollToPricing();
      return;
    }

    setRecoLoading(true);
    setRecoHtml("");

    const jwt = await getToken(tokenOptions());

    try {
      const res = await fetch("/api/recommend-combination", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify({ industry, constraints: CONSTRAINTS, personas: PERSONAS }),
      });

      await ensureOk(res, "Failed to recommend combination.");
      const data = await res.json();

      addUsage(data.usage);

      const nextConstraints: string[] =
        Array.isArray(data?.recommended_constraints) && data.recommended_constraints.length
          ? data.recommended_constraints
          : [CONSTRAINTS[0]];

      setConstraints(nextConstraints);
      if (data?.recommended_persona) setTone(data.recommended_persona);
      if (data?.reason_html) setRecoHtml(data.reason_html);
    } catch (e: any) {
      handleApiActionError(e, "Failed to recommend combination.");
    } finally {
      setRecoLoading(false);
    }
  };

  const getReportPayload = () => ({ industry, constraints, tone, models: Object.keys(results), results, rank_result: rankResult });

  const downloadResponseBlob = async (response: Response, fallbackFilename: string) => {
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const filename = extractFilename(response.headers.get("Content-Disposition")) || fallbackFilename;
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  const downloadPDF = async () => {
    if (!isPremium) {
      if (planLoaded) openUpgrade();
      return;
    }

    setPdfLoading(true);
    try {
      let response: Response | null = null;
      if (resultsView === "stakeholder") {
        if (!stakeholderReport?.id) {
          alert("Generate or load an Execution Plan before exporting.");
          return;
        }
        response = await fetch(`/api/stakeholder-reports/${stakeholderReport.id}/pdf`, {
          method: "GET",
          headers: { Authorization: `Bearer ${await getToken(tokenOptions())}` },
        });
      } else if (resultsView === "insights" && !compareResult?.comparison_id) {
        alert("Run a comparison before exporting the compare report.");
        return;
      } else if (resultsView === "insights" && compareResult?.comparison_id) {
        response = await fetch(`/api/compare-results/${compareResult.comparison_id}/pdf`, {
          method: "GET",
          headers: { Authorization: `Bearer ${await getToken(tokenOptions())}` },
        });
      } else if (resultsView === "decision" && decisionReport?.id) {
        response = await fetch(`/api/rank-reports/${decisionReport.id}/pdf`, {
          method: "GET",
          headers: { Authorization: `Bearer ${await getToken(tokenOptions())}` },
        });
      } else {
        response = await fetch("/api/download-pdf", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(getReportPayload()),
        });
      }

      if (!response.ok) {
        alert("Failed to download PDF.");
        return;
      }
      const fallbackFilename = (() => {
        const safeIndustry = String(industry || "industry")
          .trim()
          .replace(/\s+/g, "_")
          .replace(/[^a-zA-Z0-9_-]/g, "");
        const d = new Date();
        const stamp =
          `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}_` +
          `${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}${String(d.getSeconds()).padStart(2, "0")}`;
        return `IdeaGen_${safeIndustry}_${stamp}.pdf`;
      })();
      await downloadResponseBlob(response, fallbackFilename);
    } finally {
      setPdfLoading(false);
    }
  };

  const downloadExecutionPresentation = async () => {
    if (!isPremium) {
      if (planLoaded) openUpgrade();
      return;
    }
    if (!stakeholderReport?.id) {
      alert("Generate or load an Execution Plan before downloading the presentation report.");
      return;
    }
    setExecutionPresentationLoading(true);
    try {
      const response = await fetch(`/api/stakeholder-reports/${stakeholderReport.id}/presentation`, {
        method: "GET",
        headers: { Authorization: `Bearer ${await getToken(tokenOptions())}` },
      });
      if (!response.ok) {
        alert("Failed to download presentation report.");
        return;
      }
      await downloadResponseBlob(response, "IdeaGen_Execution_Presentation.pdf");
    } finally {
      setExecutionPresentationLoading(false);
    }
  };

  const sendEmail = async () => {
    if (!isPremium) {
      if (planLoaded) openUpgrade();
      return;
    }

    if (!email) return;

    setSendingEmail(true);
    setEmailStatus("");

    try {
      const jwt = await getToken(tokenOptions());
      if (resultsView === "stakeholder") {
        setEmailStatus("Execution Plan email delivery is not yet available.");
        return;
      }
      if (resultsView === "insights" && !compareResult?.comparison_id) {
        setEmailStatus("Run a comparison before emailing the compare report.");
        return;
      }
      if (resultsView === "decision" && !decisionReport?.id) {
        setEmailStatus("Select a Decision Summary Report before emailing.");
        return;
      }
      let response: Response | null = null;
      if (resultsView === "insights" && compareResult?.comparison_id) {
        response = await fetch(`/api/compare-results/${compareResult.comparison_id}/email`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
          body: JSON.stringify({ to_email: email }),
        });
      } else if (resultsView === "decision" && decisionReport?.id) {
        response = await fetch(`/api/rank-reports/${decisionReport.id}/email`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
          body: JSON.stringify({ to_email: email }),
        });
      } else {
        response = await fetch("/api/email", {
          method: "POST",
          headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
          body: JSON.stringify({ ...getReportPayload(), to_email: email }),
        });
      }
      setEmailStatus(response.ok ? "Email sent successfully!" : "Failed to send email.");
    } catch {
      setEmailStatus("Failed to send email.");
    } finally {
      setSendingEmail(false);
    }
  };

  const resultsModelCount = Object.keys(results).length;
  const hasResults = !isLoading && resultsModelCount > 0;
  const showInsights = Boolean(compareResult);
  const canClearGenerated = hasResults || Boolean(loadedSavedMeta);
  const canClearCompare = Boolean(compareResult);
  const canClearDecision = Boolean(decisionReport);
  const canClearStakeholder = Boolean(stakeholderReport);
  const canDeleteGenerated = Boolean(loadedSavedMeta) && resultsView === "generated";
  const canDeleteCompare = Boolean(compareResult?.comparison_id) && resultsView === "insights";
  const canDeleteDecision = Boolean(decisionReport?.id) && resultsView === "decision";
  const canDeleteStakeholder = Boolean(stakeholderReport?.id) && resultsView === "stakeholder";

  // UI gating values (keeps premium UI; free is locked)
  const maxConstraints = isPremium ? 3 : FREE_MAX_CONSTRAINTS;
  const freeAllowedConstraints = FREE_ALLOWED_CONSTRAINTS;
  const maxModels = isPremium ? MODELS.length : FREE_MAX_MODELS;

  // inside your component (near other state)
  const [industryOpen, setIndustryOpen] = useState(false);
  const [industryQuery, setIndustryQuery] = useState("");
  const [industryActive, setIndustryActive] = useState(0);
  const [industryHoverBubble, setIndustryHoverBubble] = useState<HoverBubbleState | null>(null);
  const industryRef = useRef<HTMLDivElement | null>(null);

  const filteredIndustries = useMemo(() => {
    const q = industryQuery.trim().toLowerCase();
    if (!q) return INDUSTRIES;
    return INDUSTRIES.filter((x) => x.toLowerCase().includes(q));
  }, [industryQuery]);

  useEffect(() => {
    function onDocDown(e: MouseEvent) {
      if (!industryRef.current) return;
      if (!industryRef.current.contains(e.target as Node)) {
        setIndustryOpen(false);
        setIndustryQuery("");
      }
    }
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, []);

  useEffect(() => {
    // reset highlight when opening or filtering
    setIndustryActive(0);
  }, [industryOpen, industryQuery]);

  useEffect(() => {
    if (!industryOpen) setIndustryHoverBubble(null);
  }, [industryOpen]);


  // AI Persona dropdown (Target-Industry style, single select)
  const [personaOpen, setPersonaOpen] = useState(false);
  const [personaQuery, setPersonaQuery] = useState("");
  const [personaActive, setPersonaActive] = useState(0);
  const [personaHoverBubble, setPersonaHoverBubble] = useState<HoverBubbleState | null>(null);
  const personaRef = useRef<HTMLDivElement | null>(null);

  const filteredPersonas = useMemo(() => {
    const q = personaQuery.trim().toLowerCase();
    if (!q) return PERSONAS;
    return PERSONAS.filter((p) => p.label.toLowerCase().includes(q) || p.id.toLowerCase().includes(q));
  }, [personaQuery]);

  useEffect(() => {
    function onDocDown(e: MouseEvent) {
      if (!personaRef.current) return;
      if (!personaRef.current.contains(e.target as Node)) {
        setPersonaOpen(false);
        setPersonaQuery("");
      }
    }
    document.addEventListener("mousedown", onDocDown);
    return () => document.removeEventListener("mousedown", onDocDown);
  }, []);

  useEffect(() => {
    if (personaOpen) setPersonaActive(0);
  }, [personaOpen, personaQuery]);

  useEffect(() => {
    if (!personaOpen) setPersonaHoverBubble(null);
  }, [personaOpen]);

  const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

  const updateSavedPanelPos = useCallback((forceCenter = false) => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.min(768, viewportWidth - 32);
    const fallbackHeight = Math.min(520, viewportHeight - 32);
    const panelHeight = savedPanelRef.current?.getBoundingClientRect().height ?? fallbackHeight;

    setSavedPanelPos((prev) => {
      if (forceCenter || !prev) {
        const left = Math.max(16, Math.round((viewportWidth - width) / 2));
        const top = Math.max(16, Math.round((viewportHeight - panelHeight) / 2));
        return { top, left, width };
      }
      const maxLeft = Math.max(16, viewportWidth - prev.width - 16);
      const maxTop = Math.max(16, viewportHeight - panelHeight - 16);
      const left = clamp(prev.left, 16, maxLeft);
      const top = clamp(prev.top, 16, maxTop);
      if (left !== prev.left || top !== prev.top) {
        return { ...prev, top, left };
      }
      return prev;
    });
  }, []);

  const openSavedPanel = (mode: "generated" | "compare" | "decision" | "stakeholder") => {
    const isSameMode = savedPanelMode === mode;
    if (isSameMode) {
      setSavedPanelMode(null);
    } else {
      setSavedPanelPos(null);
      setSavedPanelMode(mode);
    }
    if (!isSameMode) {
      if (mode === "generated") {
        fetchSavedResults();
      } else if (mode === "compare") {
        fetchSavedResults();
        fetchSavedComparisons();
      } else if (mode === "decision") {
        fetchSavedResults();
        fetchSavedReports();
      } else if (mode === "stakeholder") {
        fetchSavedStakeholderReports();
      }
    }
  };

  const startSavedPanelDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    if (savedPanelLocked) return;
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest("button, [data-no-drag='true']")) return;
    const panel = savedPanelRef.current;
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    e.preventDefault();
    savedPanelDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      originX: rect.left,
      originY: rect.top,
      width: rect.width,
      height: rect.height,
    };
    setIsDraggingSavedPanel(true);

    const onMouseMove = (moveEvent: MouseEvent) => {
      const drag = savedPanelDragRef.current;
      if (!drag) return;
      const dx = moveEvent.clientX - drag.startX;
      const dy = moveEvent.clientY - drag.startY;
      const maxLeft = Math.max(8, window.innerWidth - drag.width - 8);
      const maxTop = Math.max(8, window.innerHeight - drag.height - 8);
      const left = clamp(drag.originX + dx, 8, maxLeft);
      const top = clamp(drag.originY + dy, 8, maxTop);
      setSavedPanelPos({ top, left, width: drag.width });
    };

    const onMouseUp = () => {
      setIsDraggingSavedPanel(false);
      savedPanelDragRef.current = null;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  const updateExecutionPlanPickerPos = useCallback((forceCenter = false) => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const width = Math.min(768, viewportWidth - 32);
    const fallbackHeight = Math.min(520, viewportHeight - 32);
    const panelHeight = executionPlanPickerRef.current?.getBoundingClientRect().height ?? fallbackHeight;
    const centerTop = Math.max(16, Math.round((viewportHeight - panelHeight) / 2) - 48);

    setExecutionPlanPickerPos((prev) => {
      if (forceCenter || !prev) {
        const left = Math.max(16, Math.round((viewportWidth - width) / 2));
        const top = centerTop;
        return { top, left, width };
      }
      const maxLeft = Math.max(16, viewportWidth - prev.width - 16);
      const maxTop = Math.max(16, viewportHeight - panelHeight - 16);
      const left = clamp(prev.left, 16, maxLeft);
      const top = clamp(prev.top, 16, maxTop);
      if (left !== prev.left || top !== prev.top) {
        return { ...prev, top, left };
      }
      return prev;
    });
  }, []);

  const startExecutionPlanPickerDrag = (e: React.MouseEvent<HTMLDivElement>) => {
    if (stakeholderGenerating) return;
    if (e.button !== 0) return;
    const target = e.target as HTMLElement;
    if (target.closest("button, [data-no-drag='true']")) return;
    const panel = executionPlanPickerRef.current;
    if (!panel) return;
    const rect = panel.getBoundingClientRect();
    e.preventDefault();
    executionPlanPickerDragRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      originX: rect.left,
      originY: rect.top,
      width: rect.width,
      height: rect.height,
    };
    setIsDraggingExecutionPlanPicker(true);

    const onMouseMove = (moveEvent: MouseEvent) => {
      const drag = executionPlanPickerDragRef.current;
      if (!drag) return;
      const dx = moveEvent.clientX - drag.startX;
      const dy = moveEvent.clientY - drag.startY;
      const maxLeft = Math.max(8, window.innerWidth - drag.width - 8);
      const maxTop = Math.max(8, window.innerHeight - drag.height - 8);
      const left = clamp(drag.originX + dx, 8, maxLeft);
      const top = clamp(drag.originY + dy, 8, maxTop);
      setExecutionPlanPickerPos({ top, left, width: drag.width });
    };

    const onMouseUp = () => {
      setIsDraggingExecutionPlanPicker(false);
      executionPlanPickerDragRef.current = null;
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  };

  useEffect(() => {
    if (!savedPanelOpen) return;

    updateSavedPanelPos(true);

    function onDocDown(e: MouseEvent) {
      if (savedPanelLocked) return;
      if (
        deleteTarget ||
        deleteComparisonOpen ||
        deleteDecisionOpen ||
        deleteStakeholderOpen ||
        deleteAllGeneratedOpen ||
        deleteAllComparisonsOpen ||
        deleteAllReportsOpen
      ) {
        return;
      }
      const panel = savedPanelRef.current;
      const target = e.target as Node;
      const triggers = [
        savedGeneratedButtonRef.current,
        savedCompareButtonRef.current,
        savedDecisionButtonRef.current,
        savedStakeholderButtonRef.current,
      ].filter(Boolean) as HTMLElement[];
      if (panel && panel.contains(target)) return;
      if (triggers.some((trigger) => trigger.contains(target))) return;
      setSavedPanelMode(null);
    }

    function onKeyDown(e: KeyboardEvent) {
      if (savedPanelLocked) return;
      if (e.key === "Escape") setSavedPanelMode(null);
    }

    const handleResize = () => updateSavedPanelPos();
    window.addEventListener("resize", handleResize);
    document.addEventListener("mousedown", onDocDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("mousedown", onDocDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [
    savedPanelOpen,
    savedPanelLocked,
    updateSavedPanelPos,
    deleteTarget,
    deleteComparisonOpen,
    deleteDecisionOpen,
    deleteStakeholderOpen,
    deleteAllGeneratedOpen,
    deleteAllComparisonsOpen,
    deleteAllReportsOpen,
  ]);

  useEffect(() => {
    if (savedPanelOpen) return;
    setSavedPanelPos(null);
    setIsDraggingSavedPanel(false);
    savedPanelDragRef.current = null;
    setDeleteAllGeneratedOpen(false);
    setDeleteAllComparisonsOpen(false);
    setDeleteAllReportsOpen(false);
  }, [savedPanelOpen]);

  useEffect(() => {
    if (!executionPlanPickerOpen) return;
    updateExecutionPlanPickerPos(true);
    const onResize = () => updateExecutionPlanPickerPos();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [executionPlanPickerOpen, updateExecutionPlanPickerPos]);

  useEffect(() => {
    if (executionPlanPickerOpen) return;
    setExecutionPlanPickerPos(null);
    setIsDraggingExecutionPlanPicker(false);
    executionPlanPickerDragRef.current = null;
  }, [executionPlanPickerOpen]);

  return (
    <div className="grid min-w-0 grid-cols-1 lg:grid-cols-[342px_1fr] gap-3 lg:gap-4">
      <UpgradeModal open={upgradeOpen} onClose={() => setUpgradeOpen(false)} onUpgrade={upgradeTo} />
      {deleteTarget ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete saved result?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove the saved result and related selections.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80 space-y-1">
              <div><span className="text-white/50">Saved:</span> {formatSavedDate(deleteTarget.created_at)}</div>
              <div><span className="text-white/50">Industry:</span> {deleteTarget.industry || "Saved result"}</div>
              <div><span className="text-white/50">Persona:</span> {labelForPersona(deleteTarget.tone || "")}</div>
              <div><span className="text-white/50">Constraints:</span> {formatConstraints(deleteTarget.constraints || [])}</div>
              <div><span className="text-white/50">Models:</span> {formatModelList(deleteTarget.models || [])}</div>
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteTarget(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600"
                onClick={async () => {
                  const targetId = deleteTarget.id;
                  setDeleteTarget(null);
                  await deleteSavedResult(targetId);
                }}
                disabled={deletingSavedId === deleteTarget.id}
              >
                {deletingSavedId === deleteTarget.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteAllGeneratedOpen ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete all generated results?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove all saved generated results. This action cannot be undone.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80">
              {savedResults.length} result(s) will be deleted.
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteAllGeneratedOpen(false)}
                disabled={deletingAllGenerated}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-60 disabled:cursor-not-allowed"
                onClick={() => void deleteAllGeneratedResults()}
                disabled={deletingAllGenerated || savedResults.length === 0}
              >
                {deletingAllGenerated ? "Deleting..." : "Delete All"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteAllComparisonsOpen ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete all comparisons?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove all saved compare results. This action cannot be undone.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80">
              {savedComparisons.length} comparison(s) will be deleted.
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteAllComparisonsOpen(false)}
                disabled={deletingAllComparisons}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-60 disabled:cursor-not-allowed"
                onClick={() => void deleteAllComparisons()}
                disabled={deletingAllComparisons || savedComparisons.length === 0}
              >
                {deletingAllComparisons ? "Deleting..." : "Delete All"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteComparisonOpen && compareResult ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete comparison?</div>
            <p className="mt-2 text-sm text-white/70">
              This will remove the saved comparison and its diff insight.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80 space-y-1">
              <div><span className="text-white/50">Saved:</span> {compareResult.created_at ? formatSavedDate(compareResult.created_at) : "Recent"}</div>
              <div><span className="text-white/50">Run A:</span> {compareResult.comparison.top_outputs?.run_a?.title || formatRunLabel(compareResult.run_a_id)}</div>
              <div><span className="text-white/50">Run B:</span> {compareResult.comparison.top_outputs?.run_b?.title || formatRunLabel(compareResult.run_b_id)}</div>
              <div><span className="text-white/50">Winner:</span> {compareResult.winner_run_id ? formatRunLabel(compareResult.winner_run_id) : "Tie"}</div>
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteComparisonOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600"
                onClick={async () => {
                  const comparisonId = compareResult.comparison_id;
                  setDeleteComparisonOpen(false);
                  if (comparisonId) await deleteComparison(comparisonId);
                }}
                disabled={deletingComparisonId === compareResult.comparison_id}
              >
                {deletingComparisonId === compareResult.comparison_id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteDecisionOpen && decisionReport ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete decision report?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove the saved decision summary report.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80 space-y-1">
              <div><span className="text-white/50">Saved:</span> {formatSavedDate(decisionReport.created_at)}</div>
              <div>
                <span className="text-white/50">Runs:</span>{" "}
                {Array.isArray(decisionReport.run_ids) && decisionReport.run_ids.length > 0
                  ? decisionReport.run_ids.map(formatRunLabel).join(" • ")
                  : "No runs selected"}
              </div>
              {decisionReport.report?.summary ? (
                <div><span className="text-white/50">Summary:</span> {decisionReport.report.summary}</div>
              ) : null}
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteDecisionOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600"
                onClick={async () => {
                  const reportId = decisionReport.id;
                  setDeleteDecisionOpen(false);
                  await deleteDecisionReport(reportId);
                }}
                disabled={deletingDecisionId === decisionReport.id}
              >
                {deletingDecisionId === decisionReport.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteStakeholderOpen && stakeholderReport ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete execution plan?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove the saved execution plan.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80 space-y-1">
              <div><span className="text-white/50">Saved:</span> {formatSavedDate(stakeholderReport.created_at)}</div>
              <div>
                <span className="text-white/50">Project:</span>{" "}
                {stakeholderReport.title || stakeholderReport.dossier?.decision?.winner?.title || "Untitled execution plan"}
              </div>
              <div className="inline-flex items-center gap-1.5">
                <span className="text-white/50">Recommendation:</span>
                <span
                  className={cx(
                    "rounded-full border px-1.5 py-0.5 font-semibold",
                    recommendationTone(stakeholderReport.recommendation || stakeholderReport.dossier?.decision?.go_no_go)
                  )}
                >
                  {recommendationLabel(stakeholderReport.recommendation || stakeholderReport.dossier?.decision?.go_no_go)}
                </span>
              </div>
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteStakeholderOpen(false)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600"
                onClick={async () => {
                  const reportId = stakeholderReport.id;
                  await deleteStakeholderReport(reportId);
                }}
                disabled={deletingStakeholderId === stakeholderReport.id}
              >
                {deletingStakeholderId === stakeholderReport.id ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {deleteAllReportsOpen ? (
        <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
          <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
            <div className="text-lg font-semibold text-rose-200">Delete all decision reports?</div>
            <p className="mt-2 text-sm text-white/70">
              This will permanently remove all saved decision summary reports. This action cannot be undone.
            </p>
            <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-white/80">
              {savedReports.length} report(s) will be deleted.
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
                onClick={() => setDeleteAllReportsOpen(false)}
                disabled={deletingAllReports}
              >
                Cancel
              </button>
              <button
                type="button"
                className="flex-1 rounded-xl bg-rose-500 px-4 py-2 text-sm font-semibold text-white hover:bg-rose-600 disabled:opacity-60 disabled:cursor-not-allowed"
                onClick={() => void deleteAllDecisionReports()}
                disabled={deletingAllReports || savedReports.length === 0}
              >
                {deletingAllReports ? "Deleting..." : "Delete All"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {executionPlanPickerOpen ? (
        <div className="fixed inset-0 z-[210]" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" />
          <div
            ref={executionPlanPickerRef}
            style={executionPlanPickerStyle}
            className="fixed box-border rounded-2xl border border-white/10 bg-slate-950/95 p-5 text-white shadow-2xl backdrop-blur-xl"
          >
            <div
              className={cx(
                "flex items-center justify-between gap-3 select-none touch-none",
                isDraggingExecutionPlanPicker ? "cursor-grabbing" : "cursor-grab"
              )}
              onMouseDown={startExecutionPlanPickerDrag}
            >
              <div>
                <div className="text-lg font-semibold text-white">Select 1 report for Execution Plan</div>
                <p className="mt-1 text-xs text-white/65">
                  Ordered by run score. You can choose one model output variant per run.
                </p>
              </div>
              <button
                type="button"
                className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-60"
                onClick={() => {
                  setExecutionPlanPickerOpen(false);
                  setExecutionPlanPickerError(null);
                }}
                disabled={stakeholderGenerating}
                data-no-drag="true"
              >
                Close
              </button>
            </div>
            {stakeholderGenerating ? (
              <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-[11px] font-medium text-amber-300">
                Processing in progress — modal is temporarily locked.
              </div>
            ) : null}
            <div className="mt-4 max-h-[420px] overflow-y-auto ig-scrollbar pr-1 space-y-2">
              {executionPlanPickerLoading ? (
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white/80 inline-flex items-center gap-2">
                  <Spinner className="h-4 w-4" />
                  Loading previously generated execution plans...
                </div>
              ) : executionPlanOptions.length === 0 ? (
                <div className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-white/70">
                  No ranked reports available from this Decision Summary.
                </div>
              ) : (
                executionPlanOptions.map((item) => {
                  const alreadyGenerated = executionPlanGeneratedKeySet.has(item.optionKey);
                  const selected = executionPlanSelectedKey === item.optionKey;
                  const disabled = alreadyGenerated || stakeholderGenerating;
                  return (
                    <button
                      key={item.optionKey}
                      type="button"
                      onClick={() => {
                        if (disabled) return;
                        setExecutionPlanPickerError(null);
                        setExecutionPlanSelectedKey(item.optionKey);
                      }}
                      disabled={disabled}
                      className={cx(
                        "w-full rounded-xl border p-3 text-left transition",
                        selected
                          ? "border-blue-400/50 bg-blue-500/10"
                          : "border-white/10 bg-white/5",
                        disabled && "opacity-60 cursor-not-allowed",
                        !disabled && "hover:bg-white/10"
                      )}
                    >
                      <div className="flex flex-wrap items-center gap-2 text-[11px]">
                        <span className="rounded-full border border-white/15 bg-white/5 px-2 py-0.5 font-semibold">Run Rank {item.runRank}</span>
                        {typeof item.runScore === "number" ? (
                          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-semibold text-emerald-200">
                            Run score {item.runScore}
                          </span>
                        ) : null}
                        {typeof item.modelScore === "number" ? (
                          <span className="rounded-full border border-cyan-400/30 bg-cyan-500/10 px-2 py-0.5 font-semibold text-cyan-200">
                            Model score {item.modelScore}
                          </span>
                        ) : null}
                        {item.isWinnerRun ? (
                          <span className="rounded-full border border-indigo-400/40 bg-indigo-500/20 px-2 py-0.5 font-semibold text-indigo-200">
                            Winner run
                          </span>
                        ) : null}
                        {item.isTopOutput ? (
                          <span className="rounded-full border border-cyan-400/40 bg-cyan-500/20 px-2 py-0.5 font-semibold text-cyan-200">
                            Top output
                          </span>
                        ) : null}
                        {alreadyGenerated ? (
                          <span className="rounded-full border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 font-semibold text-amber-200">
                            Execution Plan already generated
                          </span>
                        ) : null}
                        {!alreadyGenerated && selected ? (
                          <span className="rounded-full border border-blue-400/40 bg-blue-500/20 px-2 py-0.5 font-semibold text-blue-200">
                            Selected
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-2 text-[15px] font-semibold text-white">{item.title}</div>
                      <div className="mt-0.5 text-[11px] text-cyan-200/90">
                        {item.modelLabel}
                      </div>
                      <div className="mt-1 text-[12px] text-white/75">
                        {item.runLabel}
                      </div>
                      <div className="mt-0.5 text-[11px] text-white/60">
                        Persona: {item.personaLabel}
                      </div>
                      <div className="text-[11px] text-white/60">
                        Constraints: {item.constraintsLabel}
                      </div>
                      <div className="text-[11px] text-white/60">
                        Models in run: {item.modelSetLabel}
                      </div>
                      {item.rationale ? (
                        <div className="mt-1.5 text-[11px] text-white/70 line-clamp-2">
                          {item.rationale}
                        </div>
                      ) : null}
                    </button>
                  );
                })
              )}
            </div>
            <div className="mt-4 flex items-center justify-between gap-2 border-t border-white/10 pt-3">
              <div
                className={cx(
                  "min-w-0 text-xs leading-5 whitespace-nowrap truncate py-px",
                  executionPlanPickerError ? "text-rose-300" : "text-white/70"
                )}
              >
                {executionPlanPickerError ? (
                  executionPlanPickerError
                ) : stakeholderGenerating ? (
                  <span className="inline-flex items-center">
                    Generating execution plan
                    <LoadingDots className="ml-1.5" />
                  </span>
                ) : isTokenLimited ? (
                  "Monthly token limit reached. Execution Plan generation is disabled until reset."
                ) : (
                  `${executionPlanOptions.length} output report(s) · ${executionPlanOptions.filter((item) => executionPlanGeneratedKeySet.has(item.optionKey)).length} locked`
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="rounded-xl border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-60"
                  onClick={() => {
                    setExecutionPlanPickerOpen(false);
                    setExecutionPlanPickerError(null);
                  }}
                  disabled={stakeholderGenerating}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className={cx(
                    "rounded-xl border px-3 py-1.5 text-xs font-semibold",
                    !executionPlanSelectedKey || !hasSelectableExecutionPlanOption || stakeholderGenerating || isTokenLimited
                      ? "border-white/10 bg-white/5 text-white/45 cursor-not-allowed"
                      : "border-indigo-500/40 bg-indigo-500/20 text-indigo-100 hover:bg-indigo-500/30"
                  )}
                  disabled={!executionPlanSelectedKey || !hasSelectableExecutionPlanOption || stakeholderGenerating || isTokenLimited}
                  onClick={() => {
                    const selected = executionPlanOptions.find((item) => item.optionKey === executionPlanSelectedKey);
                    if (!selected) return;
                    void runStakeholderReport({ runId: selected.runId, modelId: selected.modelId });
                  }}
                >
                  {stakeholderGenerating ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Spinner className="h-3.5 w-3.5" />
                      Generating...
                    </span>
                  ) : isTokenLimited ? (
                    "Token Limit Reached"
                  ) : (
                    "Generate Execution Plan"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {usageNotices.length ? (
        <div
          className="fixed bottom-4 right-4 z-50 flex w-full max-w-xs flex-col gap-2 pointer-events-none"
          role="status"
          aria-live="polite"
        >
          {usageNotices.map((notice) => (
            <div
              key={notice.id}
              className="rounded-xl border border-white/10 bg-slate-950/95 px-4 py-3 text-xs text-white/85 shadow-xl backdrop-blur"
            >
              {notice.message}
            </div>
          ))}
        </div>
      ) : null}

      {pageBootLoading ? (
        <FullPageLoader
          title="Loading IdeaGen"
          subtitle="Preparing your workspace..."
          chips={["Saved Results", "Compare Results", "Decision Summary"]}
          note="Please wait while we initialize your dashboard."
          tip="Tip: this only appears on page refresh/load."
        />
      ) : null}

      {isLoading ? (
        <FullPageLoader
          title="Generating ideas"
          subtitle={`Running ${selectedModels.length} model(s)…`}
          chips={selectedModelLabels}
        />
      ) : null}

      {/* Sidebar */}
      <aside className="min-w-0 lg:sticky lg:top-24 h-fit overflow-visible">
        <GlassCard className="p-5 overflow-visible">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center">
                <h2 className="text-base font-semibold text-gray-900 dark:text-white">Configuration</h2>
                <HelpTooltip
                  content={
                    <>
                      <div>Step 1: Pick a Target Industry.</div>
                      <div>Step 2: Choose Constraints (“must-have conditions” for the idea — the rules the output has to follow).</div>
                      <div>Step 3: Pick an AI Persona (the voice/point of view of the idea).</div>
                      <div>Step 4: Select the AI Models you want to compare.</div>
                      <div>Step 5: Click Generate Ideas. You can change any step and run again.</div>
                    </>
                  }
                />
              </div>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
                Tune inputs, then compare outputs across models.
              </p>
            </div>

            <span
              className={cx(
                "rounded-full border px-2 py-1 text-[11px] font-semibold",
                isPremium
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                  : "border-white/10 bg-white/5 text-gray-700 dark:text-gray-300"
              )}
            >
              {isPremium ? "Premium" : "Free"}
            </span>
          </div>

          {/* Keep premium-looking UI: show limits as a small note (no layout downgrade) */}
          {!isPremium ? (
            <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-gray-900 dark:text-white">Free plan limits</div>
                <span className="text-[11px] rounded-full border border-white/10 bg-white/10 px-2 py-0.5 font-semibold text-gray-700 dark:text-gray-200">
                  Locked
                </span>
              </div>

              <ul className="mt-3 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                <li>• Up to {maxModels} model</li>
                <li>• {FREE_MAX_CONSTRAINTS} constraint</li>
                <li>• Neutral persona only</li>
                <li>• Recommend/Export locked</li>
              </ul>

              <button
                type="button"
                onClick={scrollToPricing}
                className="mt-3 inline-flex w-full items-center justify-center rounded-xl bg-blue-600 px-3 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Upgrade to Premium
              </button>
            </div>
          ) : null}

          <div className="mt-5 space-y-5 overflow-visible">
            <div ref={industryRef}>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                Target Industry
              </label>

              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIndustryOpen((v) => !v)}
                  className={cx(
                    "w-full rounded-xl border px-3 py-2.5 text-sm outline-none text-left flex items-center justify-between gap-2",
                    "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
                    "focus:ring-2 focus:ring-blue-500/40"
                  )}
                  aria-haspopup="listbox"
                  aria-expanded={industryOpen}
                >
                  <span className="truncate text-gray-900 dark:text-gray-100">
                    {industry || "Select industry"}
                  </span>

                  <svg
                    className={cx(
                      "h-4 w-4 shrink-0 text-gray-500 dark:text-gray-300 transition-transform",
                      industryOpen ? "rotate-180" : "rotate-0"
                    )}
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    aria-hidden="true"
                  >
                    <path
                      fillRule="evenodd"
                      d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>

                {industryOpen && (
                  <div className="absolute z-50 mt-2 w-full rounded-2xl border shadow-2xl overflow-hidden bg-slate-950/95 border-white/10">
                    {/* search */}
                    <div className="p-2 border-b border-white/10 bg-slate-950/95">
                      <input
                        value={industryQuery}
                        onChange={(e) => setIndustryQuery(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Escape") {
                            setIndustryOpen(false);
                            setIndustryQuery("");
                            return;
                          }
                          if (e.key === "ArrowDown") {
                            e.preventDefault();
                            setIndustryActive((i) => Math.min(i + 1, filteredIndustries.length - 1));
                            return;
                          }
                          if (e.key === "ArrowUp") {
                            e.preventDefault();
                            setIndustryActive((i) => Math.max(i - 1, 0));
                            return;
                          }
                          if (e.key === "Enter") {
                            e.preventDefault();
                            const pick = filteredIndustries[industryActive];
                            if (pick) {
                              setIndustry(pick);
                              setIndustryOpen(false);
                              setIndustryQuery("");
                            }
                          }
                        }}
                        placeholder="Search industry…"
                        className={cx(
                          "w-full rounded-lg border px-3 py-2 text-sm outline-none",
                          "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
                          "text-gray-900 dark:text-gray-100",
                          "focus:ring-2 focus:ring-blue-500/40"
                        )}
                        autoFocus
                      />
                    </div>

                    {/* options */}
                    <div
                      className="p-2 max-h-64 overflow-y-auto ig-scrollbar bg-slate-950/95"
                      role="listbox"
                      onMouseLeave={() => setIndustryHoverBubble(null)}
                    >
                      {filteredIndustries.length === 0 ? (
                        <div className="px-2 py-3 text-sm text-gray-500 dark:text-gray-300">
                          No matches.
                        </div>
                      ) : (
                        filteredIndustries.map((ind, idx) => {
                          const active = idx === industryActive;
                          const selected = ind === industry;

                          return (
                            <button
                              key={ind}
                              type="button"
                              aria-label={`${ind}. ${getIndustryHint(ind)}`}
                              onMouseEnter={(e) => {
                                setIndustryActive(idx);
                                setIndustryHoverBubble(buildHoverBubble(e.currentTarget, getIndustryHint(ind)));
                              }}
                              onMouseMove={(e) => setIndustryHoverBubble(buildHoverBubble(e.currentTarget, getIndustryHint(ind)))}
                              onFocus={(e) => setIndustryHoverBubble(buildHoverBubble(e.currentTarget, getIndustryHint(ind)))}
                              onBlur={() => setIndustryHoverBubble(null)}
                              onClick={() => {
                                setIndustry(ind);
                                setIndustryOpen(false);
                                setIndustryQuery("");
                              }}
                              className={cx(
                                "w-full text-left px-2 py-2 rounded-lg text-sm flex items-center justify-between gap-2",
                                active
                                  ? "bg-blue-500/15 text-gray-900 dark:text-gray-100"
                                  : "hover:bg-gray-50 dark:hover:bg-white/10 text-gray-900 dark:text-gray-100"
                              )}
                              aria-selected={selected}
                              role="option"
                            >
                              <span className="truncate">{ind}</span>
                              {selected ? (
                                <span className="text-xs font-semibold text-blue-400">Selected</span>
                              ) : null}
                            </button>
                          );
                        })
                      )}
                    </div>

                    {/* footer */}
                    <div className="flex items-center justify-between gap-2 p-2 border-t border-white/10 bg-slate-950/95">
                      <div className="text-xs text-gray-500 dark:text-gray-300">
                        {filteredIndustries.length} option(s)
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setIndustryOpen(false);
                          setIndustryQuery("");
                        }}
                        className="text-xs font-semibold px-2 py-1 rounded-lg border border-black/10 dark:border-white/10 hover:bg-gray-50 dark:hover:bg-white/10 text-gray-700 dark:text-gray-200"
                      >
                        Close
                      </button>
                    </div>
                    {industryHoverBubble
                      ? createPortal(
                          <div
                            className="fixed z-[120] max-w-[320px] rounded-xl border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[11px] leading-snug text-white/90 shadow-2xl backdrop-blur pointer-events-none"
                            style={{
                              top: industryHoverBubble.top,
                              left: industryHoverBubble.left,
                              transform:
                                industryHoverBubble.side === "right"
                                  ? "translateY(-50%)"
                                  : "translate(-100%, -50%)",
                            }}
                            role="tooltip"
                          >
                            {industryHoverBubble.text}
                          </div>,
                          document.body
                        )
                      : null}
                  </div>
                )}
              </div>
            </div>


            <div className="relative overflow-visible ig-scrollbar">
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">Constraints</label>

              <ConstraintMultiSelectDropdown
                options={CONSTRAINTS}
                value={constraints}
                onChange={setConstraints}
                maxSelected={maxConstraints}
                isPremium={isPremium}
                freeAllowedCount={freeAllowedConstraints}
                onLimitReached={() => {
                  if (planLoaded) openUpgrade();
                }}
                onPremiumOptionSelected={() => {
                  if (planLoaded) openUpgrade();
                }}
              />
            </div>

            <div>
              <div ref={personaRef}>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                  AI Persona
                </label>

                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setPersonaOpen((v) => !v)}
                    className={cx(
                      "w-full rounded-xl border px-3 py-2.5 text-sm outline-none text-left flex items-center justify-between gap-2",
                      "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
                      "focus:ring-2 focus:ring-blue-500/40"
                    )}
                    aria-haspopup="listbox"
                    aria-expanded={personaOpen}
                  >
                    <span className="truncate text-gray-900 dark:text-gray-100">
                      {PERSONAS.find((p) => p.id === tone)?.label ?? "Select persona"}
                    </span>

                    <svg
                      className={cx(
                        "h-4 w-4 shrink-0 text-gray-500 dark:text-gray-300 transition-transform",
                        personaOpen ? "rotate-180" : "rotate-0"
                      )}
                      viewBox="0 0 20 20"
                      fill="currentColor"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M5.23 7.21a.75.75 0 011.06.02L10 10.94l3.71-3.71a.75.75 0 111.06 1.06l-4.24 4.25a.75.75 0 01-1.06 0L5.21 8.29a.75.75 0 01.02-1.08z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </button>

                  {personaOpen && (
                    <div
                      className="absolute z-50 mt-2 w-full rounded-2xl border shadow-2xl overflow-hidden bg-slate-950/95 border-white/10"
                      role="listbox"
                    >
                      {/* search */}
                      <div className="p-2 border-b border-white/10 bg-slate-950/95">
                        <input
                          value={personaQuery}
                          onChange={(e) => setPersonaQuery(e.target.value)}
                          placeholder="Search persona…"
                          className={cx(
                            "w-full rounded-lg border px-3 py-2 text-sm outline-none",
                            "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
                            "text-gray-900 dark:text-gray-100 placeholder:text-gray-500 dark:placeholder:text-gray-400",
                            "focus:ring-2 focus:ring-blue-500/40"
                          )}
                          autoFocus
                        />
                      </div>

                      {/* options */}
                      <div
                        className="p-2 max-h-64 overflow-y-auto ig-scrollbar bg-slate-950/95"
                        onMouseLeave={() => setPersonaHoverBubble(null)}
                      >
                        {filteredPersonas.length === 0 ? (
                          <div className="px-2 py-3 text-sm text-gray-400">No matches.</div>
                        ) : (
                          filteredPersonas.map((p, idx) => {
                            const active = idx === personaActive;
                            const selected = p.id === tone;
                            const personaHint = getPersonaHint(p.id);

                            const originalIdx = PERSONAS.findIndex((x) => x.id === p.id);
                            const locked = !isPremium && originalIdx > 0;

                            return (
                              <button
                                key={p.id}
                                type="button"
                                aria-label={`${p.label}. ${personaHint}`}
                                onMouseEnter={(e) => {
                                  setPersonaActive(idx);
                                  setPersonaHoverBubble(buildHoverBubble(e.currentTarget, personaHint));
                                }}
                                onMouseMove={(e) => setPersonaHoverBubble(buildHoverBubble(e.currentTarget, personaHint))}
                                onFocus={(e) => setPersonaHoverBubble(buildHoverBubble(e.currentTarget, personaHint))}
                                onBlur={() => setPersonaHoverBubble(null)}
                                onClick={() => {
                                  if (locked) {
                                    if (planLoaded) openUpgrade();
                                    return;
                                  }
                                  setTone(p.id);
                                  setPersonaOpen(false);
                                  setPersonaQuery("");
                                }}
                                className={cx(
                                  "w-full text-left px-3 py-2.5 rounded-xl text-sm transition-colors",
                                  active ? "bg-blue-500/15 text-white" : "hover:bg-white/10 text-white/90",
                                  locked && "opacity-60"
                                )}
                                aria-selected={selected}
                                role="option"
                              >
                                <div className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3">
                                  {/* LEFT: wraps naturally */}
                                  <div className="min-w-0 whitespace-normal break-words leading-snug">
                                    {p.label}
                                  </div>

                                  {/* RIGHT: always on the right, no layout shift */}
                                  <div className="text-[11px] font-semibold">
                                    {locked ? (
                                      <span className="text-gray-400">Premium</span>
                                    ) : selected ? (
                                      <span className="text-blue-300">Selected</span>
                                    ) : (
                                      <span className="opacity-0 select-none">Selected</span>
                                    )}
                                  </div>
                                </div>
                              </button>

                            );
                          })
                        )}
                      </div>

                      {/* footer */}
                      <div className="flex items-center justify-between gap-2 p-2 border-t border-white/10 bg-slate-950/95">
                        <div className="text-xs text-white/55">{filteredPersonas.length} option(s)</div>
                        <button
                          type="button"
                          onClick={() => {
                            setPersonaOpen(false);
                            setPersonaQuery("");
                          }}
                          className="text-xs font-semibold px-3 py-1.5 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white/80"
                        >
                          Close
                        </button>
                      </div>
                      {personaHoverBubble
                        ? createPortal(
                            <div
                              className="fixed z-[120] max-w-[320px] rounded-xl border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[11px] leading-snug text-white/90 shadow-2xl backdrop-blur pointer-events-none"
                              style={{
                                top: personaHoverBubble.top,
                                left: personaHoverBubble.left,
                                transform:
                                  personaHoverBubble.side === "right"
                                    ? "translateY(-50%)"
                                    : "translate(-100%, -50%)",
                              }}
                              role="tooltip"
                            >
                              {personaHoverBubble.text}
                            </div>,
                            document.body
                          )
                        : null}
                    </div>
                  )}
                </div>
              </div>


            </div>

            <div>
              <button
                type="button"
                onClick={recommendCombination}
                disabled={recoLoading || isApiLimited || isTokenLimited}
                className={cx(
                  "w-full rounded-xl border px-3 py-2.5 text-sm font-semibold",
                  "border-black/10 dark:border-white/10",
                  "bg-white/50 dark:bg-white/5",
                  (recoLoading || isApiLimited || isTokenLimited) && "opacity-70 cursor-not-allowed",
                  (!recoLoading && !isApiLimited && !isTokenLimited) && "hover:bg-white/70 dark:hover:bg-white/10"
                )}
              >
                <span className="inline-flex items-center justify-center gap-2">
                  {recoLoading ? <Spinner className="h-4 w-4" /> : null}
                  <span>
                    {recoLoading ? "Recommending..." : isTokenLimited ? "Token Limit Reached" : isApiLimited ? "Rate Limit Reached" : "Recommend Combination"}
                  </span>
                  {!isPremium ? (
                    <span className="ml-2 text-[10px] font-semibold text-gray-600 dark:text-gray-400">Premium</span>
                  ) : null}
                </span>
              </button>

              {recoHtml && (
                <div className="mt-3 rounded-xl border border-black/10 dark:border-white/10 bg-white/50 dark:bg-white/5 p-4">
                  <div
                    className="max-h-[280px] overflow-y-auto pr-2 text-sm leading-relaxed ig-scrollbar"
                    style={{ scrollbarGutter: "stable" as any }}
                    dangerouslySetInnerHTML={{ __html: recoHtml }}
                  />
                  <style jsx>{`
                    :global([data-section="recommendation_reason"] ul) {
                      margin: 0.5rem 0 0.25rem 1rem;
                    }
                    :global([data-section="recommendation_reason"] li) {
                      margin: 0.35rem 0;
                    }
                    :global([data-section="recommendation_reason"] h3) {
                      margin: 0 0 0.5rem 0;
                      font-weight: 700;
                    }
                  `}</style>
                </div>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">AI Models</label>

              <div className="space-y-2">
                {MODELS.map((model) => {
                  const checked = selectedModels.includes(model.id);
                  const locked = !isPremium && !checked && selectedModels.length >= FREE_MAX_MODELS;

                  return (
                    <label
                      key={model.id}
                      className={cx(
                        "flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5",
                        "border-black/10 dark:border-white/10",
                        "bg-white/50 dark:bg-white/5",
                        locked ? "opacity-60 cursor-not-allowed" : "cursor-pointer hover:bg-white/70 dark:hover:bg-white/10"
                      )}
                    >
                      <div className="flex items-center gap-3">
                        <input
                          type="checkbox"
                          value={model.id}
                          checked={checked}
                          onChange={(e) => {
                            if (locked && e.target.checked) {
                              if (planLoaded) openUpgrade();
                              return;
                            }
                            handleModelToggle(model.id, e.target.checked);
                          }}
                          disabled={locked}
                          className="w-4 h-4 rounded"
                        />
                        <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{model.label}</span>
                      </div>
                      {!isPremium && model.id !== selectedModels[0] ? (
                        <span className="text-[11px] font-semibold text-gray-600 dark:text-gray-400">Premium</span>
                      ) : null}
                    </label>
                  );
                })}
              </div>
            </div>

            {isPremium && (
              <div>
                <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <div className="flex items-center">
                    Advanced Settings
                    <HelpTooltip content={
                      <>
                        <div>Step 1: Move Creativity left for safer ideas or right for bolder ideas.</div>
                        <div>Step 2: Move Idea Diversity left for fewer variations or right for more variety.</div>
                        <div>Step 3: Small tweaks are enough. Premium only.</div>
                      </>
                    } />
                  </div>
                </label>
                
                <div className="space-y-5 rounded-xl border border-black/10 dark:border-white/10 bg-white/50 dark:bg-white/5 p-3">
                  
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center">
                        <span className="text-xs text-gray-700 dark:text-gray-300">Creativity</span>
                        <HelpTooltip content="Determines how imaginative the AI should be. Higher values encourage unique and unconventional ideas, while lower values stick to safe, proven concepts." />
                      </div>
                      <span className="text-xs font-mono text-gray-600 dark:text-gray-400">{temperature}</span>
                    </div>
                    <input 
                      type="range" 
                      min="0" max="1" step="0.1" 
                      value={temperature} 
                      onChange={(e) => setTemperature(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700 accent-blue-600"
                    />
                    <div className="flex justify-between px-0.5 mt-1">
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">Predictable</span>
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">Wild</span>
                    </div>
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center">
                        <span className="text-xs text-gray-700 dark:text-gray-300">Idea Diversity</span>
                        <HelpTooltip content="Controls the variety of word choices and concepts. High values explore a broader range of possibilities, while low values focus on the most likely outcomes." />
                      </div>
                      <span className="text-xs font-mono text-gray-600 dark:text-gray-400">{topP}</span>
                    </div>
                    <input 
                      type="range" 
                      min="0" max="1" step="0.05" 
                      value={topP} 
                      onChange={(e) => setTopP(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer dark:bg-gray-700 accent-blue-600"
                    />
                    <div className="flex justify-between px-0.5 mt-1">
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">Focused</span>
                      <span className="text-[10px] text-gray-500 dark:text-gray-400">Broad</span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={generateIdeas}
              disabled={isLoading || isApiLimited || isTokenLimited}
              className={cx(
                "w-full rounded-xl px-3 py-3 text-sm font-semibold text-white",
                (isLoading || isApiLimited || isTokenLimited) ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
              )}
            >
              <span className="inline-flex items-center justify-center gap-2">
                {isLoading ? <Spinner className="h-4 w-4" /> : null}
                <span>
                  {isLoading ? "Generating..." : isTokenLimited ? "Token Limit Reached" : isApiLimited ? "Rate Limit Reached" : "Generate Ideas"}
                </span>
              </span>
            </button>

            {(hasResults || compareResult) && (
              <div className="pt-5 mt-5 border-t border-black/10 dark:border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center">
                    <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Export</h3>
                    <HelpTooltip content={
                      <>
                        <div>Step 1: Generate ideas or compare results first.</div>
                        <div>Step 2: Choose Download PDF or Email.</div>
                        <div>Step 3: If emailing, enter an address and click Send Email.</div>
                        <div>Step 4: The file matches the view you are on.</div>
                      </>
                    } />
                  </div>
                  {!isPremium ? (
                    <span className="text-[11px] font-semibold text-gray-600 dark:text-gray-400">Premium</span>
                  ) : null}
                </div>

                <div className="space-y-3">
                  <button
                    type="button"
                    onClick={downloadPDF}
                    disabled={pdfLoading}
                    className={cx(
                      "w-full rounded-xl border px-3 py-2.5 text-sm font-semibold",
                      "border-black/10 dark:border-white/10",
                      "bg-white/50 dark:bg-white/5",
                      pdfLoading ? "opacity-70 cursor-wait" : "hover:bg-white/70 dark:hover:bg-white/10",
                      !isPremium && "opacity-60"
                    )}
                  >
                    <span className="inline-flex items-center justify-center gap-2">
                      {pdfLoading ? <Spinner className="h-4 w-4" /> : null}
                      <span>{pdfLoading ? "Preparing PDF..." : "Download PDF"}</span>
                    </span>
                  </button>

                  <input
                    type="email"
                    placeholder="Email address"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    disabled={!isPremium}
                    className={cx(
                      "w-full rounded-xl border px-3 py-2.5 text-sm outline-none",
                      "bg-white/60 dark:bg-white/5 border-black/10 dark:border-white/10",
                      "focus:ring-2 focus:ring-blue-500/40",
                      !isPremium && "opacity-60 cursor-not-allowed"
                    )}
                  />

                  <button
                    type="button"
                    onClick={sendEmail}
                    disabled={sendingEmail || !email || !isPremium || isEmailLimited}
                    className={cx(
                      "w-full rounded-xl px-3 py-2.5 text-sm font-semibold text-white",
                      (sendingEmail || isEmailLimited) ? "bg-blue-500 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700",
                      (!email || !isPremium) && "opacity-60"
                    )}
                  >
                    <span className="inline-flex items-center justify-center gap-2">
                      {sendingEmail ? <Spinner className="h-4 w-4" /> : null}
                      <span>
                        {sendingEmail ? "Sending..." : isEmailLimited ? "Daily Limit Reached" : "Send Email"}
                      </span>
                    </span>
                  </button>

                  {emailStatus && <p className="text-xs text-center text-gray-600 dark:text-gray-300">{emailStatus}</p>}

                  {!isPremium ? (
                    <button
                      type="button"
                      onClick={handleAccountClick}
                      className="w-full rounded-xl border px-3 py-2 text-sm outline-none
                                  bg-slate-900/90 border-white/10 text-white placeholder:text-white/40
                                  focus:ring-2 focus:ring-blue-500/40"
                    >
                      Unlock export with Premium
                    </button>
                  ) : null}
                </div>
              </div>
            )}
          </div>
        </GlassCard>
      </aside>

      {/* Main content */}
      <section className="min-w-0">
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] gap-2 mb-4">
          <GlassCard className="p-2 sm:p-3 order-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <h2 className="text-xs font-semibold text-gray-900 dark:text-white">Current Usage</h2>
                <div className="mt-1.5 grid w-full grid-cols-4 items-start gap-x-2 text-[10px] sm:text-[11px]">
                  <div className="min-w-0 flex w-full flex-col items-center justify-center leading-tight">
                    <UsageLabel
                      label="Tokens"
                      tooltip={`Tokens: ${(tokenUsage.total_tokens || 0).toLocaleString()} / ${tokenLimit.toLocaleString()} • Refresh: monthly`}
                    />
                    <span className={cx("font-semibold tabular-nums", tokenTone)}>
                      {formatUsageCompact(tokenUsage.total_tokens || 0)}
                    </span>
                  </div>

                  <div className="min-w-0 flex w-full flex-col items-center justify-center leading-tight">
                    <UsageLabel
                      label="API"
                      tooltip={`API calls: ${(tokenUsage.api_calls_count || 0).toLocaleString()} / ${apiLimit} • Refresh: per minute`}
                    />
                    <span className={cx("font-semibold tabular-nums", apiTone)}>
                      {formatUsageCompact(tokenUsage.api_calls_count || 0)}
                    </span>
                  </div>

                  <div className="min-w-0 flex w-full flex-col items-center justify-center leading-tight">
                    <UsageLabel
                      label="Email"
                      tooltip={`Emails sent: ${(tokenUsage.emails_sent_count || 0).toLocaleString()} / ${emailLimit} • Refresh: daily`}
                    />
                    <span className={cx("font-semibold tabular-nums", emailTone)}>
                      {formatUsageCompact(tokenUsage.emails_sent_count || 0)}
                    </span>
                  </div>

                  <div className="min-w-0 flex w-full flex-col items-center justify-center leading-tight">
                    <UsageLabel
                      label="Storage"
                      tooltip={`Storage: ${formatBytes(savedUsageBytes)} / ${savedLimitBytes ? formatBytes(savedLimitBytes) : "Unknown"} • Refresh: persistent`}
                    />
                    <span className={cx("font-semibold tabular-nums", storageTone)}>
                      {storagePercent}%
                    </span>
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => refreshUsage(true)}
                disabled={usageRefreshing}
                className={cx(
                  "rounded-full border border-black/10 dark:border-white/10 p-1",
                  "text-gray-500 dark:text-gray-300",
                  usageRefreshing ? "opacity-60 cursor-wait" : "hover:bg-white/80 dark:hover:bg-white/10"
                )}
                title="Refresh usage"
                aria-label="Refresh usage"
              >
                <svg
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className={cx("h-3.5 w-3.5", usageRefreshing && "animate-spin")}
                  aria-hidden="true"
                >
                  <path
                    d="M15.5 10a5.5 5.5 0 01-9.96 3.25M4.5 10a5.5 5.5 0 019.96-3.25"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <path d="M14.5 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M5.5 16.5v-3h3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </div>
          </GlassCard>

          <GlassCard className="p-2 sm:p-3 relative order-1 overflow-hidden">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-xs font-semibold text-gray-900 dark:text-white">Saved Results</h2>
                <div className="text-[10px] text-gray-500 dark:text-gray-400">
                  {savedResults.length} saved
                </div>
              </div>
              <div className="grid grid-cols-4 gap-1.5 min-w-0">
                <button
                  ref={savedGeneratedButtonRef}
                  type="button"
                  onClick={() => openSavedPanel("generated")}
                  className={cx(
                    "min-w-0 rounded-lg border px-1 py-1 text-[9px] sm:text-[10px] font-semibold whitespace-nowrap text-center truncate",
                    "border-black/10 dark:border-white/10",
                    savedPanelMode === "generated"
                      ? "bg-blue-600 text-white"
                      : "bg-white/60 dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                  )}
                >
                  Generated Results
                </button>
                <button
                  ref={savedCompareButtonRef}
                  type="button"
                  onClick={() => openSavedPanel("compare")}
                  className={cx(
                    "min-w-0 rounded-lg border px-1 py-1 text-[9px] sm:text-[10px] font-semibold whitespace-nowrap text-center truncate",
                    "border-black/10 dark:border-white/10",
                    savedPanelMode === "compare"
                      ? "bg-blue-600 text-white"
                      : "bg-white/60 dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                  )}
                >
                  Compare Results
                </button>
                <button
                  ref={savedDecisionButtonRef}
                  type="button"
                  onClick={() => openSavedPanel("decision")}
                  className={cx(
                    "min-w-0 rounded-lg border px-1 py-1 text-[9px] sm:text-[10px] font-semibold whitespace-nowrap text-center truncate",
                    "border-black/10 dark:border-white/10",
                    savedPanelMode === "decision"
                      ? "bg-blue-600 text-white"
                      : "bg-white/60 dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                  )}
                >
                  Decision Summary
                </button>
                <button
                  ref={savedStakeholderButtonRef}
                  type="button"
                  onClick={() => openSavedPanel("stakeholder")}
                  className={cx(
                    "min-w-0 rounded-lg border px-1 py-1 text-[9px] sm:text-[10px] font-semibold whitespace-nowrap text-center truncate transition-colors",
                    savedPanelMode === "stakeholder"
                      ? "bg-amber-500/18 dark:bg-amber-400/20 text-amber-900 dark:text-amber-100 border-amber-400/90 dark:border-amber-300/90"
                      : "bg-white/60 dark:bg-white/5 text-gray-700 dark:text-gray-200 border-amber-500/70 dark:border-amber-400/70 hover:bg-amber-500/12 dark:hover:bg-amber-400/12 hover:text-amber-900 dark:hover:text-amber-100 active:bg-amber-500/18 dark:active:bg-amber-400/18"
                  )}
                >
                  Execution Plan
                </button>
              </div>
            </div>

            {mounted && savedPanelOpen
              ? createPortal(
                  <div className="fixed inset-0 z-50">
                    <div
                      className="absolute inset-0 bg-black/40"
                      aria-hidden="true"
                      onClick={() => {
                        if (savedPanelLocked) return;
                        setSavedPanelMode(null);
                      }}
                    />
                    <div
                      ref={savedPanelRef}
                      style={savedPanelStyle}
                      className="fixed z-10 box-border rounded-2xl border border-white/10 bg-white/95 shadow-2xl backdrop-blur dark:bg-slate-950/95 overflow-visible flex flex-col h-[520px] max-h-[85vh]"
                    >
                      <div
                        className={cx(
                          "flex items-center justify-between px-4 py-3 border-b border-white/10 bg-white/60 dark:bg-white/5 select-none touch-none",
                          isDraggingSavedPanel ? "cursor-grabbing" : "cursor-grab"
                        )}
                        onMouseDown={startSavedPanelDrag}
                      >
                        <div className="flex items-center gap-2">
                          <div className="text-sm font-semibold text-gray-900 dark:text-white">
                            {savedPanelMode === "generated"
                              ? "Generated Results"
                              : savedPanelMode === "compare"
                              ? "Compare Results"
                              : savedPanelMode === "decision"
                              ? "Decision Summary Report"
                              : "Execution Plan"}
                          </div>
                          {savedPanelMode === "generated" ? (
                            <HelpTooltip content="Load a saved run to revisit its outputs or delete it to free up space." />
                          ) : savedPanelMode === "compare" ? (
                            <HelpTooltip
                              content={
                                <>
                                  <div>Step 1: Open Compare Results.</div>
                                  <div>Step 2: Click Show under Select two runs.</div>
                                  <div>Step 3: Choose Run A and Run B from the list.</div>
                                  <div>Step 4: Make sure both runs used the same Industry, Persona, and Constraints.</div>
                                  <div>Step 5: Click Compare to generate the Diff Insight.</div>
                                  <div>Step 6: Review the winner and key changes, then export if needed.</div>
                                </>
                              }
                            />
                          ) : savedPanelMode === "decision" ? (
                            <HelpTooltip
                              content={
                                <>
                                  <div>Step 1: Open Decision Summary Report.</div>
                                  <div>Step 2: Click Show under Select runs for the report.</div>
                                  <div>Step 3: Choose 1-5 runs you want to summarize.</div>
                                  <div>Step 4: Make sure you select the same Industry</div>
                                  <div>Step 5: Click Decision Summary Report to generate the summary.</div>
                                  <div>Step 6: Review the ranked runs, insights, and next steps.</div>
                                  <div>Step 7: Export or email the report if needed.</div>
                                </>
                              }
                            />
                          ) : (
                            <HelpTooltip
                              content={
                                <>
                                  <div>Step 1: Open Execution Plan.</div>
                                  <div>Step 2: Click Generate Execution Plan from the Decision Summary tab.</div>
                                  <div>Step 3: View saved execution plans here and reload when needed.</div>
                                  <div>Step 4: Use the plan to brief stakeholders on execution, cost, and risk.</div>
                                </>
                              }
                            />
                          )}
                        </div>
                        <div className="flex items-center gap-2" data-no-drag="true">
                          <button
                            type="button"
                            onClick={() => {
                              if (savedPanelMode === "generated") {
                                fetchSavedResults();
                              } else if (savedPanelMode === "compare") {
                                setCompareError(null);
                                fetchSavedResults();
                                fetchSavedComparisons();
                              } else if (savedPanelMode === "decision") {
                                fetchSavedResults();
                                fetchSavedReports();
                              } else if (savedPanelMode === "stakeholder") {
                                fetchSavedStakeholderReports();
                              }
                            }}
                            disabled={savedPanelLoading || savedPanelLocked}
                            className={cx(
                              "rounded-lg border px-2.5 py-1 text-[11px] font-semibold",
                              "border-black/10 dark:border-white/10",
                              "bg-white/60 dark:bg-white/5 inline-flex items-center gap-1.5",
                              savedPanelLoading || savedPanelLocked
                                ? "opacity-60 cursor-not-allowed"
                                : "hover:bg-white/80 dark:hover:bg-white/10"
                            )}
                          >
                            {savedPanelLoading ? (
                              <svg
                                viewBox="0 0 20 20"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.5"
                                className="h-3.5 w-3.5 animate-spin"
                                aria-hidden="true"
                              >
                                <path
                                  d="M15.5 10a5.5 5.5 0 01-9.96 3.25M4.5 10a5.5 5.5 0 019.96-3.25"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                />
                                <path d="M14.5 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
                                <path d="M5.5 16.5v-3h3" strokeLinecap="round" strokeLinejoin="round" />
                              </svg>
                            ) : null}
                            {savedPanelLoading ? "Loading..." : "Refresh"}
                          </button>
                          {savedPanelMode === "generated" ? (
                            <button
                              type="button"
                              onClick={() => {
                                if (savedResults.length === 0) return;
                                setDeleteAllGeneratedOpen(true);
                              }}
                              disabled={savedPanelLoading || savedPanelLocked || savedResults.length === 0}
                              aria-disabled={savedPanelLoading || savedPanelLocked || savedResults.length === 0}
                              title={savedResults.length === 0 ? "No saved results to delete." : undefined}
                              className={cx(
                                "rounded-lg border px-2.5 py-1 text-[11px] font-semibold",
                                "border-rose-300/40 dark:border-rose-400/30",
                                "bg-rose-500/10 text-rose-700 dark:text-rose-300 inline-flex items-center gap-1.5",
                                savedPanelLoading || savedPanelLocked || savedResults.length === 0
                                  ? "opacity-60 cursor-not-allowed"
                                  : "hover:bg-rose-500/20"
                              )}
                            >
                              {deletingAllGenerated ? (
                                <>
                                  <Spinner className="h-3.5 w-3.5" />
                                  <span className="inline-flex items-center">
                                    Deleting
                                    <LoadingDots className="ml-1" />
                                  </span>
                                </>
                              ) : (
                                "Delete All"
                              )}
                            </button>
                          ) : null}
                          <button
                            type="button"
                            onClick={() => setSavedPanelMode(null)}
                            disabled={savedPanelLocked}
                            className={cx(
                              "rounded-lg border px-2.5 py-1 text-[11px] font-semibold border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5",
                              savedPanelLocked
                                ? "text-gray-400 dark:text-gray-500 cursor-not-allowed"
                                : "text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                            )}
                            aria-label="Close saved panel"
                          >
                            Close
                          </button>
                        </div>
                      </div>
                      {savedPanelLocked ? (
                        <div className="border-b border-white/10 bg-amber-500/10 px-4 py-1.5 text-[11px] font-medium text-amber-700 dark:text-amber-300">
                          Processing in progress — modal is temporarily locked.
                        </div>
                      ) : null}

                      <div className="flex-1 min-h-0 flex flex-col">
                        <div
                          aria-busy={savedPanelLoading || savedPanelLocked}
                          className={cx(
                            "flex-1 min-h-0 overflow-y-auto p-4 space-y-3 ig-scrollbar",
                            (savedPanelMode === "compare" || savedPanelMode === "decision") && "flex flex-col",
                            savedPanelMode === "compare" && "pb-1",
                            savedPanelMode === "decision" && "pb-0"
                          )}
                        >
                          {savedPanelMode === "generated" ? (
                          savedLoading ? (
                            <div className="inline-flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                              <Spinner className="h-3.5 w-3.5" />
                              <span>Loading saved results…</span>
                            </div>
                          ) : savedResults.length === 0 ? (
                            <div className="text-xs text-gray-500 dark:text-gray-400">No saved results yet.</div>
                          ) : (
                            <>
                              {deletingAllGenerated ? (
                                <div className="inline-flex items-center gap-2 text-xs text-rose-600 dark:text-rose-300">
                                  <Spinner className="h-3.5 w-3.5" />
                                  <span className="inline-flex items-center">
                                    Deleting saved results
                                    <LoadingDots className="ml-1.5" />
                                  </span>
                                </div>
                              ) : null}
                              {savedResults.map((item) => (
                                <div
                                  key={item.id}
                                  className={cx(
                                    "rounded-xl border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-3.5 py-3 space-y-2 shadow-sm transition-all duration-300",
                                    deletingGeneratedIds.includes(item.id) && "opacity-40 translate-x-1 scale-[0.99] animate-pulse"
                                  )}
                                >
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="text-xs font-semibold text-gray-900 dark:text-white truncate">
                                      {formatSavedDate(item.created_at)}
                                    </div>
                                    <div className="flex flex-wrap items-center justify-end gap-1.5">
                                      <button
                                        type="button"
                                        onClick={() => loadSavedResult(item.id)}
                                        disabled={loadingSavedId === item.id || deletingSavedId === item.id || deletingAllGenerated}
                                        className={cx(
                                          "rounded-lg px-2.5 py-1 text-[11px] font-semibold",
                                          "bg-blue-600 text-white",
                                          loadingSavedId === item.id || deletingSavedId === item.id || deletingAllGenerated
                                            ? "opacity-60 cursor-wait"
                                            : "hover:bg-blue-700"
                                        )}
                                      >
                                        {loadingSavedId === item.id ? "Loading" : "Load"}
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => setDeleteTarget(item)}
                                        disabled={loadingSavedId === item.id || deletingSavedId === item.id || deletingAllGenerated}
                                        className={cx(
                                          "rounded-lg px-2.5 py-1 text-[11px] font-semibold",
                                          "bg-rose-500 text-white",
                                          loadingSavedId === item.id || deletingSavedId === item.id || deletingAllGenerated
                                            ? "opacity-60 cursor-wait"
                                            : "hover:bg-rose-600"
                                        )}
                                      >
                                        {deletingSavedId === item.id ? "Deleting" : "Delete"}
                                      </button>
                                    </div>
                                  </div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400">
                                    {item.industry || "Saved result"} · {formatModelList(item.models || [])}
                                  </div>
                                  <div className="text-xs text-gray-500 dark:text-gray-400">
                                    {labelForPersona(item.tone || "")} · {formatConstraints(item.constraints || [])}
                                  </div>
                                </div>
                              ))}
                            </>
                          )
                        ) : savedPanelMode === "compare" ? (
                          <div className="flex flex-col gap-3 flex-1 min-h-0">
                            <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 space-y-2">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-300">Select two runs</div>
                                <button
                                  type="button"
                                  onClick={() => setCompareSelectOpen((prev) => !prev)}
                                  className="text-[10px] font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400"
                                >
                                  {compareSelectOpen ? "Hide" : "Show"}
                                </button>
                              </div>
                              {compareSelectOpen ? (
                                <>
                                  <div className="space-y-2">
                                    <label className="block text-[11px] text-gray-600 dark:text-gray-300">
                                      <span className="font-semibold text-gray-700 dark:text-gray-200">Run A</span>
                                      <select
                                        value={compareRunA ?? ""}
                                        onChange={(e) => updateCompareSelection("a", e.target.value)}
                                        className="mt-1 w-full rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2 py-1 text-[11px] text-gray-800 dark:text-gray-100"
                                      >
                                        <option value="">Select a run</option>
                                        {savedResults.map((item) => (
                                          <option key={item.id} value={item.id}>
                                            {formatSavedDate(item.created_at)} · {item.industry || "Saved result"}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                    <label className="block text-[11px] text-gray-600 dark:text-gray-300">
                                      <span className="font-semibold text-gray-700 dark:text-gray-200">Run B</span>
                                      <select
                                        value={compareRunB ?? ""}
                                        onChange={(e) => updateCompareSelection("b", e.target.value)}
                                        className="mt-1 w-full rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2 py-1 text-[11px] text-gray-800 dark:text-gray-100"
                                      >
                                        <option value="">Select a run</option>
                                        {savedResults.map((item) => (
                                          <option key={item.id} value={item.id}>
                                            {formatSavedDate(item.created_at)} · {item.industry || "Saved result"}
                                          </option>
                                        ))}
                                      </select>
                                    </label>
                                  </div>
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                    {compareRunA ? `A: ${formatRunLabel(compareRunA)}` : "A: Not selected"}
                                    {compareRunB ? ` • B: ${formatRunLabel(compareRunB)}` : ""}
                                  </div>
                                  {selectedCompareRunA ? (
                                    <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                      A config: {labelForPersona(selectedCompareRunA.tone || "")} · {formatConstraints(selectedCompareRunA.constraints || [])}
                                    </div>
                                  ) : null}
                                  {selectedCompareRunB ? (
                                    <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                      B config: {labelForPersona(selectedCompareRunB.tone || "")} · {formatConstraints(selectedCompareRunB.constraints || [])}
                                    </div>
                                  ) : null}
                                </>
                              ) : (
                                <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                  {compareRunA ? `A: ${formatRunLabel(compareRunA)}` : "A: Not selected"}
                                  {compareRunB ? ` • B: ${formatRunLabel(compareRunB)}` : ""}
                                </div>
                              )}
                            </div>

                            <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 space-y-2 flex-1 min-h-0 flex flex-col">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-300">Saved comparisons</div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (savedComparisons.length === 0) return;
                                    setDeleteAllComparisonsOpen(true);
                                  }}
                                  disabled={comparisonsLoading || deletingAllComparisons || savedComparisons.length === 0 || savedPanelLocked}
                                  aria-disabled={comparisonsLoading || deletingAllComparisons || savedComparisons.length === 0 || savedPanelLocked}
                                  title={savedComparisons.length === 0 ? "No comparisons to delete." : undefined}
                                  className={cx(
                                    "rounded-lg border px-2 py-0.5 text-[10px] font-semibold",
                                    "border-rose-300/40 dark:border-rose-400/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
                                    comparisonsLoading || deletingAllComparisons || savedComparisons.length === 0 || savedPanelLocked
                                      ? "opacity-60 cursor-not-allowed"
                                      : "hover:bg-rose-500/20"
                                  )}
                                >
                                  {deletingAllComparisons ? "Deleting..." : "Delete All"}
                                </button>
                              </div>
                              <div className="flex-1 min-h-0 space-y-2 overflow-y-auto ig-scrollbar pr-1">
                                {comparisonsLoading ? (
                                  <div className="inline-flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                                    <Spinner className="h-3.5 w-3.5" />
                                    <span>Loading comparisons…</span>
                                  </div>
                                ) : savedComparisons.length === 0 ? (
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">No comparisons yet.</div>
                                ) : (
                                  <>
                                    {deletingAllComparisons ? (
                                      <div className="inline-flex items-center gap-2 text-[11px] text-rose-600 dark:text-rose-300">
                                        <Spinner className="h-3.5 w-3.5" />
                                        <span className="inline-flex items-center">
                                          Deleting comparisons
                                          <LoadingDots className="ml-1.5" />
                                        </span>
                                      </div>
                                    ) : null}
                                    {savedComparisons.map((item) => (
                                      <div
                                        key={item.id}
                                        className={cx(
                                          "flex items-center justify-between gap-2 rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2.5 py-2 transition-all duration-300",
                                          deletingComparisonIds.includes(item.id) && "opacity-40 translate-x-1 scale-[0.99] animate-pulse"
                                        )}
                                      >
                                        <div className="min-w-0">
                                          <div className="text-[11px] font-semibold text-gray-900 dark:text-white truncate">
                                            {formatSavedDate(item.created_at)}
                                          </div>
                                          <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                            Winner: {formatWinnerLabel(item)}
                                          </div>
                                          {item.top_outputs ? (
                                            <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                              A: {item.top_outputs.run_a?.title || "Untitled"}
                                              {item.top_outputs.run_a?.model_label ? ` (${item.top_outputs.run_a.model_label})` : ""}
                                              {typeof item.top_outputs.run_a?.score === "number" ? ` · Score ${item.top_outputs.run_a.score}` : ""} · B:{" "}
                                              {item.top_outputs.run_b?.title || "Untitled"}
                                              {item.top_outputs.run_b?.model_label ? ` (${item.top_outputs.run_b.model_label})` : ""}
                                              {typeof item.top_outputs.run_b?.score === "number" ? ` · Score ${item.top_outputs.run_b.score}` : ""}
                                            </div>
                                          ) : null}
                                        </div>
                                        <div className="flex items-center gap-1.5 shrink-0">
                                          <button
                                            type="button"
                                            onClick={() => {
                                              setCompareSelection({ runA: item.run_a_id, runB: item.run_b_id });
                                              setCompareResult(null);
                                              runCompare(item.run_a_id, item.run_b_id, true);
                                            }}
                                            disabled={isTokenLimited || compareLoading || savedPanelLocked || deletingAllComparisons}
                                            className={cx(
                                              "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                              isTokenLimited || compareLoading || savedPanelLocked || deletingAllComparisons
                                                ? "bg-slate-400 cursor-not-allowed"
                                                : "bg-emerald-600 hover:bg-emerald-700"
                                            )}
                                          >
                                            View
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() => void deleteComparison(item.id)}
                                            disabled={deletingComparisonId === item.id || compareLoading || savedPanelLocked || deletingAllComparisons}
                                            className={cx(
                                              "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                              deletingComparisonId === item.id || compareLoading || savedPanelLocked || deletingAllComparisons
                                                ? "bg-slate-400 cursor-not-allowed"
                                                : "bg-rose-500 hover:bg-rose-600"
                                            )}
                                          >
                                            {deletingComparisonId === item.id ? "Deleting..." : "Delete"}
                                          </button>
                                        </div>
                                      </div>
                                    ))}
                                  </>
                                )}
                              </div>
                            </div>
                          </div>
                        ) : savedPanelMode === "decision" ? (
                          <div className="flex flex-col gap-3 flex-1 min-h-0">
                            <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 space-y-2">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-300">Select runs for the report</div>
                                <button
                                  type="button"
                                  onClick={() => setDecisionSelectOpen((prev) => !prev)}
                                  className="text-[10px] font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400"
                                >
                                  {decisionSelectOpen ? "Hide" : "Show"}
                                </button>
                              </div>
                              <label className="flex items-start gap-2 text-[11px] text-gray-600 dark:text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={useAllRuns}
                                  onChange={(e) => setUseAllRuns(e.target.checked)}
                                  className="mt-0.5"
                                />
                                <span>Include all saved results.</span>
                              </label>
                              {decisionSelectOpen ? (
                                savedLoading ? (
                                  <div className="inline-flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                                    <Spinner className="h-3.5 w-3.5" />
                                    <span>Loading saved runs…</span>
                                  </div>
                                ) : savedResults.length === 0 ? (
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">No saved runs yet.</div>
                                ) : (
                                  <div className={cx("space-y-2", useAllRuns && "opacity-60 pointer-events-none")}>
                                    {savedResults.map((item) => (
                                      <label
                                        key={item.id}
                                        className="flex items-start gap-2 rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2.5 py-2"
                                      >
                                        <input
                                          type="checkbox"
                                          checked={reportSelection.includes(item.id)}
                                          onChange={() => toggleReportSelection(item.id)}
                                        />
                                        <div className="min-w-0">
                                          <div className="text-[11px] font-semibold text-gray-900 dark:text-white truncate">
                                            {formatSavedDate(item.created_at)}
                                          </div>
                                          <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                            {item.industry || "Saved result"} · {formatModelList(item.models || [])}
                                          </div>
                                          <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                            {labelForPersona(item.tone || "")} · {formatConstraints(item.constraints || [])}
                                          </div>
                                        </div>
                                      </label>
                                    ))}
                                  </div>
                                )
                              ) : (
                                <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                  {useAllRuns
                                    ? "All saved runs selected"
                                    : reportSelection.length > 0
                                    ? `${reportSelection.length} run(s) selected`
                                    : "No runs selected"}
                                </div>
                              )}
                            </div>

                            <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 space-y-2 flex-1 min-h-0 flex flex-col">
                              <div className="flex items-center justify-between gap-2">
                                <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-300">Saved decision summary reports</div>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (savedReports.length === 0) return;
                                    setDeleteAllReportsOpen(true);
                                  }}
                                  disabled={reportsLoading || deletingAllReports || savedReports.length === 0 || savedPanelLocked}
                                  aria-disabled={reportsLoading || deletingAllReports || savedReports.length === 0 || savedPanelLocked}
                                  title={savedReports.length === 0 ? "No reports to delete." : undefined}
                                  className={cx(
                                    "rounded-lg border px-2 py-0.5 text-[10px] font-semibold",
                                    "border-rose-300/40 dark:border-rose-400/30 bg-rose-500/10 text-rose-700 dark:text-rose-300",
                                    reportsLoading || deletingAllReports || savedReports.length === 0 || savedPanelLocked
                                      ? "opacity-60 cursor-not-allowed"
                                      : "hover:bg-rose-500/20"
                                  )}
                                >
                                  {deletingAllReports ? "Deleting..." : "Delete All"}
                                </button>
                              </div>
                              <div className="flex-1 min-h-0 space-y-2 overflow-y-auto ig-scrollbar pr-1">
                                {reportsLoading ? (
                                  <div className="inline-flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                                    <Spinner className="h-3.5 w-3.5" />
                                    <span>Loading reports…</span>
                                  </div>
                                ) : savedReports.length === 0 ? (
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">No reports yet.</div>
                                ) : (
                                  <>
                                    {deletingAllReports ? (
                                      <div className="inline-flex items-center gap-2 text-[11px] text-rose-600 dark:text-rose-300">
                                        <Spinner className="h-3.5 w-3.5" />
                                        <span className="inline-flex items-center">
                                          Deleting decision reports
                                          <LoadingDots className="ml-1.5" />
                                        </span>
                                      </div>
                                    ) : null}
                                    {savedReports.map((item) => {
                                      const runSummary = Array.isArray(item.run_ids)
                                        ? item.run_ids.map(formatRunLabel).join(" • ")
                                        : "";
                                      return (
                                        <div
                                          key={item.id}
                                          className={cx(
                                            "flex items-center justify-between gap-2 rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2.5 py-2 transition-all duration-300",
                                            deletingReportIds.includes(item.id) && "opacity-40 translate-x-1 scale-[0.99] animate-pulse"
                                          )}
                                        >
                                          <div className="min-w-0">
                                            <div className="text-[11px] font-semibold text-gray-900 dark:text-white truncate">
                                              {formatSavedDate(item.created_at)}
                                            </div>
                                            <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                              {runSummary || "Saved report"}
                                            </div>
                                            {item.top_run_id ? (
                                              <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                                Top: {formatRunLabel(item.top_run_id)}
                                              </div>
                                            ) : null}
                                          </div>
                                          <div className="flex items-center gap-1.5 shrink-0">
                                            <button
                                              type="button"
                                              onClick={async () => {
                                                const startedAt = Date.now();
                                                let loaded = false;
                                                try {
                                                  setSavedPanelMode(null);
                                                  setResultsHydrating(true);
                                                  setReportDownloadId(item.id);
                                                  const jwt = await getToken(tokenOptions());
                                                  if (!jwt) throw new Error("no_token");
                                                  const res = await fetch(`/api/rank-reports/${item.id}`, {
                                                    headers: { Authorization: `Bearer ${jwt}` },
                                                  });
                                                  if (!res.ok) throw new Error("load_report_failed");
                                                  const data = await res.json();
                                                  await ensureMinLoadingTime(startedAt, 600);
                                                  setDecisionReport(data);
                                                  setResultsView("decision");
                                                  loaded = true;
                                                } catch {
                                                  pushNotice("Failed to load report.");
                                                } finally {
                                                  setResultsHydrating(false);
                                                  if (loaded) {
                                                    pushNotice("Decision summary report loaded.");
                                                  }
                                                  setReportDownloadId(null);
                                                }
                                              }}
                                              disabled={reportDownloadId === item.id || reportLoading || savedPanelLocked || deletingAllReports}
                                              className={cx(
                                                "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                                reportDownloadId === item.id || reportLoading || savedPanelLocked || deletingAllReports
                                                  ? "bg-slate-400 cursor-not-allowed"
                                                  : "bg-blue-600 hover:bg-blue-700"
                                              )}
                                            >
                                              {reportDownloadId === item.id ? "Loading..." : "View"}
                                            </button>
                                            <button
                                              type="button"
                                              onClick={() => void deleteDecisionReport(item.id)}
                                              disabled={deletingDecisionId === item.id || reportLoading || savedPanelLocked || deletingAllReports}
                                              className={cx(
                                                "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                                deletingDecisionId === item.id || reportLoading || savedPanelLocked || deletingAllReports
                                                  ? "bg-slate-400 cursor-not-allowed"
                                                  : "bg-rose-500 hover:bg-rose-600"
                                              )}
                                            >
                                              {deletingDecisionId === item.id ? "Deleting..." : "Delete"}
                                            </button>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </>
                                )}
                              </div>
                            </div>

                            {isTokenLimited ? (
                              <div className="mt-2 text-[11px] text-rose-500 dark:text-rose-400">
                                Token limit reached. Diff Mode and rank reports are disabled until the monthly reset.
                              </div>
                            ) : null}
                          </div>
                        ) : savedPanelMode === "stakeholder" ? (
                          <div className="flex flex-col gap-3 flex-1 min-h-0">
                            <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3 space-y-2 flex-1 min-h-0 flex flex-col">
                              <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-300">
                                Saved execution plans
                              </div>
                              <div className="flex-1 min-h-0 space-y-2 overflow-y-auto ig-scrollbar pr-1">
                                {stakeholderReportsLoading ? (
                                  <div className="inline-flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
                                    <Spinner className="h-3.5 w-3.5" />
                                    <span>Loading execution plans…</span>
                                  </div>
                                ) : savedStakeholderReports.length === 0 ? (
                                  <div className="text-[11px] text-gray-500 dark:text-gray-400">
                                    No execution plans yet.
                                  </div>
                                ) : (
                                  savedStakeholderReports.map((item) => (
                                    <div
                                      key={item.id}
                                      className="flex items-center justify-between gap-2 rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 px-2.5 py-2"
                                    >
                                      <div className="min-w-0">
                                        <div className="text-[11px] font-semibold text-gray-900 dark:text-white truncate">
                                          {formatSavedDate(item.created_at)}
                                        </div>
                                        <div className="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                                          Project: {item.title || "Untitled execution plan"}
                                        </div>
                                        <div className="mt-1 inline-flex items-center gap-1.5 text-[11px]">
                                          <span className="text-gray-500 dark:text-gray-400">Recommendation:</span>
                                          <span className={cx("rounded-full border px-1.5 py-0.5 font-semibold", recommendationTone(item.recommendation))}>
                                            {recommendationLabel(item.recommendation)}
                                          </span>
                                          <span className="text-gray-500 dark:text-gray-400">· {item.horizon_months} months</span>
                                        </div>
                                      </div>
                                      <div className="flex items-center gap-1.5 shrink-0">
                                        <button
                                          type="button"
                                          onClick={() => void loadStakeholderReport(item.id, true)}
                                          disabled={stakeholderLoadingId === item.id || deletingStakeholderId === item.id || savedPanelLocked}
                                          className={cx(
                                            "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                            stakeholderLoadingId === item.id || deletingStakeholderId === item.id || savedPanelLocked
                                              ? "bg-slate-400 cursor-not-allowed"
                                              : "bg-blue-600 hover:bg-blue-700"
                                          )}
                                        >
                                          {stakeholderLoadingId === item.id ? "Loading..." : "View"}
                                        </button>
                                        <button
                                          type="button"
                                          onClick={() => {
                                            setStakeholderReport((prev) => (prev?.id === item.id ? prev : ({
                                              id: item.id,
                                              created_at: item.created_at,
                                              source_type: item.source_type,
                                              source_id: item.source_id,
                                              title: item.title,
                                              recommendation: item.recommendation,
                                              scenario_profile: item.scenario_profile,
                                              horizon_months: item.horizon_months,
                                              currency: item.currency,
                                              region: item.region,
                                              model: item.model,
                                            } as StakeholderReport)));
                                            setDeleteStakeholderOpen(true);
                                          }}
                                          disabled={deletingStakeholderId === item.id || stakeholderLoadingId === item.id || savedPanelLocked}
                                          className={cx(
                                            "rounded-lg px-2.5 py-1 text-[11px] font-semibold text-white",
                                            deletingStakeholderId === item.id || stakeholderLoadingId === item.id || savedPanelLocked
                                              ? "bg-slate-400 cursor-not-allowed"
                                              : "bg-rose-500 hover:bg-rose-600"
                                          )}
                                        >
                                          {deletingStakeholderId === item.id ? "Deleting..." : "Delete"}
                                        </button>
                                      </div>
                                    </div>
                                  ))
                                )}
                              </div>
                            </div>
                          </div>
                        ) : null}
                        </div>
                        {savedPanelMode === "compare" ? (
                          <div className="h-9 border-t border-white/10 bg-white/90 px-4 dark:bg-slate-950/90">
                            <div className="flex h-full items-center justify-between gap-3 overflow-hidden">
                              <div
                                className={cx(
                                  "min-w-0 text-[11px] leading-none whitespace-nowrap truncate",
                                  compareError ? "text-rose-500 dark:text-rose-300" : "text-gray-600 dark:text-gray-300"
                                )}
                              >
                                {compareError ? (
                                  compareError
                                ) : compareLoading ? (
                                  <span className="inline-flex items-center">
                                    Comparing selected runs
                                    <LoadingDots className="ml-1.5" />
                                  </span>
                                ) : compareReady ? (
                                  "Ready to compare."
                                ) : (
                                  "Select two runs with the same configuration."
                                )}
                              </div>
                              <button
                                type="button"
                                onClick={() => runCompare()}
                                disabled={!compareReady || compareLoading || isTokenLimited}
                                className={cx(
                                  "inline-flex items-center gap-2 rounded-lg px-3 py-1 text-[11px] font-semibold text-white",
                                  !compareReady || compareLoading || isTokenLimited
                                    ? "bg-slate-400 cursor-not-allowed"
                                    : "bg-blue-600 hover:bg-blue-700"
                                )}
                              >
                                {compareLoading ? (
                                  <>
                                    <svg
                                      viewBox="0 0 20 20"
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="1.5"
                                      className="h-3.5 w-3.5 animate-spin"
                                      aria-hidden="true"
                                    >
                                      <path
                                        d="M15.5 10a5.5 5.5 0 01-9.96 3.25M4.5 10a5.5 5.5 0 019.96-3.25"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                      />
                                      <path d="M14.5 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
                                      <path d="M5.5 16.5v-3h3" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                    Comparing...
                                  </>
                                ) : (
                                  "Compare"
                                )}
                              </button>
                            </div>
                          </div>
                        ) : null}
                        {savedPanelMode === "decision" ? (
                          <div className="h-9 border-t border-white/10 bg-white/90 px-4 dark:bg-slate-950/90 overflow-hidden">
                            <div className="flex h-full items-center gap-2 overflow-x-auto overflow-y-hidden flex-nowrap ig-scrollbar">
                              <div className="text-[11px] font-semibold text-gray-700 dark:text-gray-200">Delivery</div>
                              <div className="flex items-center gap-2">
                                {(["pdf", "email", "both"] as const).map((opt) => (
                                  <button
                                    key={opt}
                                    type="button"
                                    onClick={() => setReportOutput(opt)}
                                    disabled={reportLoading || savedPanelLocked}
                                    className={cx(
                                      "rounded-lg border px-2.5 py-1 text-[10px] font-semibold whitespace-nowrap",
                                      "border-black/10 dark:border-white/10",
                                      reportLoading || savedPanelLocked ? "opacity-60 cursor-not-allowed" : "",
                                      reportOutput === opt
                                        ? "bg-blue-600 text-white"
                                        : "bg-white/60 dark:bg-white/5 text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                                    )}
                                  >
                                    {opt === "pdf" ? "PDF" : opt === "email" ? "Email" : "PDF + Email"}
                                  </button>
                                ))}
                              </div>
                              {reportEmailRequired ? (
                                <input
                                  type="email"
                                  value={reportEmail}
                                  onChange={(e) => setReportEmail(e.target.value)}
                                  placeholder="you@company.com"
                                  disabled={reportLoading || savedPanelLocked}
                                  className="h-8 w-36 sm:w-44 rounded-lg border px-2.5 text-[11px] outline-none bg-white/70 dark:bg-white/5 border-black/10 dark:border-white/10 text-gray-900 dark:text-gray-100"
                                />
                              ) : null}
                              <button
                                type="button"
                                onClick={runAgenticReport}
                                className={cx(
                                  "inline-flex items-center gap-2 rounded-lg px-3 py-1 text-[11px] font-semibold text-white whitespace-nowrap",
                                  reportLoading || !reportCanSubmit || isTokenLimited
                                    ? "bg-slate-400 cursor-not-allowed"
                                    : "bg-purple-600 hover:bg-purple-700"
                                )}
                                disabled={reportLoading || !reportCanSubmit || isTokenLimited}
                              >
                                {reportLoading ? (
                                  <>
                                    <svg
                                      viewBox="0 0 20 20"
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="1.5"
                                      className="h-3.5 w-3.5 animate-spin"
                                      aria-hidden="true"
                                    >
                                      <path
                                        d="M15.5 10a5.5 5.5 0 01-9.96 3.25M4.5 10a5.5 5.5 0 019.96-3.25"
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                      />
                                      <path d="M14.5 3.5v3h-3" strokeLinecap="round" strokeLinejoin="round" />
                                      <path d="M5.5 16.5v-3h3" strokeLinecap="round" strokeLinejoin="round" />
                                    </svg>
                                    Generating...
                                  </>
                                ) : (
                                  "Decision Summary Report"
                                )}
                              </button>
                              <div className="ml-auto hidden md:block text-[11px] leading-none text-gray-600 dark:text-gray-300 whitespace-nowrap">
                                {reportLoading ? (
                                  <span className="inline-flex items-center">
                                    Generating decision summary
                                    <LoadingDots className="ml-1.5" />
                                  </span>
                                ) : useAllRuns ? (
                                  "All saved runs selected"
                                ) : reportSelection.length > 0 ? (
                                  `${reportSelection.length} run(s) selected`
                                ) : (
                                  "No runs selected"
                                )}
                              </div>
                            </div>
                          </div>
                        ) : null}
                        {savedPanelMode === "stakeholder" ? (
                          <div className="h-9 border-t border-white/10 bg-white/90 px-4 dark:bg-slate-950/90">
                            <div className="flex h-full items-center justify-between gap-3 overflow-hidden">
                              <div
                                className={cx(
                                  "min-w-0 text-[11px] leading-none whitespace-nowrap truncate",
                                  deletingStakeholderId !== null
                                    ? "text-rose-500 dark:text-rose-300"
                                    : "text-gray-600 dark:text-gray-300"
                                )}
                              >
                                {stakeholderReportsLoading || stakeholderLoadingId !== null || deletingStakeholderId !== null ? (
                                  <span className="inline-flex items-center">
                                    {stakeholderFooterText}
                                    <LoadingDots className="ml-1.5" />
                                  </span>
                                ) : (
                                  stakeholderFooterText
                                )}
                              </div>
                              <div className="text-[11px] leading-none text-gray-600 dark:text-gray-300 whitespace-nowrap">
                                {savedStakeholderReports.length} saved
                              </div>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  </div>,
                  document.body
                )
              : null}
          </GlassCard>
        </div>

        <GlassCard className="min-h-[680px] p-6 lg:p-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex w-full lg:w-auto flex-wrap items-center gap-0.5 rounded-full border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-1">
              <button
                type="button"
                onClick={() => setResultsView("generated")}
                className={cx(
                  "rounded-full px-3 py-1.5 text-xs font-semibold transition",
                  resultsView === "generated"
                    ? "bg-blue-600 text-white"
                    : "text-gray-700 dark:text-gray-200 hover:bg-white/70 dark:hover:bg-white/10"
                )}
              >
                Generated Results
              </button>
              <span
                aria-hidden="true"
                className="pointer-events-none select-none px-0.5 text-gray-500/75 dark:text-gray-400/75"
              >
                <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" fill="none">
                  <path d="M3 1.5L7 5L3 8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <button
                type="button"
                onClick={() => setResultsView("insights")}
                className={cx(
                  "rounded-full px-3 py-1.5 text-xs font-semibold transition",
                  resultsView === "insights"
                    ? "bg-blue-600 text-white"
                    : "text-gray-700 dark:text-gray-200 hover:bg-white/70 dark:hover:bg-white/10"
                )}
              >
                Compare Rank Results
              </button>
              <span
                aria-hidden="true"
                className="pointer-events-none select-none px-0.5 text-gray-500/75 dark:text-gray-400/75"
              >
                <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" fill="none">
                  <path d="M3 1.5L7 5L3 8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <button
                type="button"
                onClick={() => setResultsView("decision")}
                className={cx(
                  "rounded-full px-3 py-1.5 text-xs font-semibold transition",
                  resultsView === "decision"
                    ? "bg-blue-600 text-white"
                    : "text-gray-700 dark:text-gray-200 hover:bg-white/70 dark:hover:bg-white/10"
                )}
              >
                Decision Summary Report
              </button>
              <span
                aria-hidden="true"
                className="pointer-events-none select-none px-0.5 text-gray-500/75 dark:text-gray-400/75"
              >
                <svg viewBox="0 0 10 10" className="h-2.5 w-2.5" fill="none">
                  <path d="M3 1.5L7 5L3 8.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <button
                type="button"
                onClick={() => setResultsView("stakeholder")}
                className={cx(
                  "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors",
                  resultsView === "stakeholder"
                    ? "bg-amber-500/18 dark:bg-amber-400/20 text-amber-900 dark:text-amber-100 border-amber-400/90 dark:border-amber-300/90"
                    : "text-gray-700 dark:text-gray-200 border-amber-500/70 dark:border-amber-400/70 hover:bg-amber-500/12 dark:hover:bg-amber-400/12 hover:text-amber-900 dark:hover:text-amber-100 active:bg-amber-500/18 dark:active:bg-amber-400/18"
                )}
              >
                Execution Plan
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  if (resultsView === "generated") {
                    if (canClearGenerated) clearGeneratedResults();
                  } else if (resultsView === "insights") {
                    if (canClearCompare) clearCompareResults();
                  } else if (resultsView === "decision") {
                    if (canClearDecision) clearDecisionReport();
                  } else if (resultsView === "stakeholder") {
                    if (canClearStakeholder) clearStakeholderReport();
                  }
                }}
                disabled={
                  resultsView === "generated"
                    ? !canClearGenerated
                    : resultsView === "insights"
                    ? !canClearCompare
                    : resultsView === "decision"
                    ? !canClearDecision
                    : !canClearStakeholder
                }
                className={cx(
                  "rounded-full px-3 py-1.5 text-xs font-semibold",
                  "border border-black/10 dark:border-white/10",
                  "bg-white/70 dark:bg-white/5 text-gray-700 dark:text-gray-200",
                  resultsView === "generated"
                    ? (canClearGenerated ? "hover:bg-white/90 dark:hover:bg-white/10" : "opacity-60 cursor-not-allowed")
                    : resultsView === "insights"
                    ? (canClearCompare ? "hover:bg-white/90 dark:hover:bg-white/10" : "opacity-60 cursor-not-allowed")
                    : resultsView === "decision"
                    ? (canClearDecision ? "hover:bg-white/90 dark:hover:bg-white/10" : "opacity-60 cursor-not-allowed")
                    : (canClearStakeholder ? "hover:bg-white/90 dark:hover:bg-white/10" : "opacity-60 cursor-not-allowed")
                )}
              >
                Clear
              </button>
              <button
                type="button"
                onClick={() => {
                  if (canDeleteCompare && compareResult?.comparison_id) {
                    setDeleteComparisonOpen(true);
                  } else if (canDeleteGenerated && loadedSavedMeta) {
                    setDeleteTarget(loadedSavedMeta);
                  } else if (canDeleteDecision) {
                    setDeleteDecisionOpen(true);
                  } else if (canDeleteStakeholder) {
                    setDeleteStakeholderOpen(true);
                  }
                }}
                disabled={
                  resultsView === "insights"
                    ? !canDeleteCompare
                    : resultsView === "decision"
                    ? !canDeleteDecision
                    : resultsView === "stakeholder"
                    ? !canDeleteStakeholder
                    : !canDeleteGenerated
                }
                className={cx(
                  "rounded-full px-3 py-1.5 text-xs font-semibold",
                  "border border-rose-500/40 text-rose-200 bg-rose-500/10",
                  resultsView === "insights"
                    ? (canDeleteCompare ? "hover:bg-rose-500/20" : "opacity-60 cursor-not-allowed")
                    : resultsView === "decision"
                    ? (canDeleteDecision ? "hover:bg-rose-500/20" : "opacity-60 cursor-not-allowed")
                    : resultsView === "stakeholder"
                    ? (canDeleteStakeholder ? "hover:bg-rose-500/20" : "opacity-60 cursor-not-allowed")
                    : (canDeleteGenerated ? "hover:bg-rose-500/20" : "opacity-60 cursor-not-allowed")
                )}
              >
                {resultsView === "insights" && deletingComparisonId && compareResult?.comparison_id === deletingComparisonId
                  ? "Deleting..."
                  : resultsView === "decision" && deletingDecisionId && decisionReport?.id === deletingDecisionId
                  ? "Deleting..."
                  : resultsView === "stakeholder" && deletingStakeholderId && stakeholderReport?.id === deletingStakeholderId
                  ? "Deleting..."
                  : resultsView === "generated" && deletingSavedId && loadedSavedMeta?.id === deletingSavedId
                  ? "Deleting..."
                  : "Delete"}
              </button>
            </div>
          </div>
          {hasResults && isStorageLimited ? (
            <div className="mt-2 text-[11px] text-rose-500 dark:text-rose-400">
              Storage limit reached. Free up space by deleting saved results.
            </div>
          ) : null}
          <div className="mt-4">
            {resultsHydrating ? (
              <ResultsSkeletonCard />
            ) : resultsView === "generated" ? (
              <div className="mt-4 space-y-5">
                {!isLoading && Object.keys(results).length === 0 && (
                  <div className="rounded-xl border border-dashed border-black/15 dark:border-white/15 p-10 text-center">
                    <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-3 text-center space-y-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">Your generated ideas will appear here</p>
                      <p className="text-sm text-gray-700 dark:text-gray-200">
                        Go to <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results</span> and click the <span className="font-semibold text-indigo-700 dark:text-indigo-300">Generated Results</span> button to load the generated results.
                      </p>
                    </div>
                    <div className="mt-6 text-left">
                      <div className="mx-auto max-w-lg">
                        <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-4">
                          <div className="text-sm font-semibold text-gray-900 dark:text-white text-center">Quick start</div>
                          <div className="mt-3 space-y-1.5 text-left text-sm text-gray-700 dark:text-gray-200">
                            {[
                              <>Pick a <span className="font-semibold text-indigo-700 dark:text-indigo-300">Target Industry</span></>,
                              <>Choose <span className="font-semibold text-indigo-700 dark:text-indigo-300">constraints</span> (must-have rules)</>,
                              <>Select an <span className="font-semibold text-indigo-700 dark:text-indigo-300">AI persona</span> (voice/POV)</>,
                              <>Pick 1–4 <span className="font-semibold text-indigo-700 dark:text-indigo-300">AI models</span> to compare</>,
                            ].map((step, idx) => (
                              <div key={idx} className="flex items-center gap-2">
                                <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-indigo-500 text-[11px] font-semibold text-white/95 shadow-sm">
                                  {idx + 1}
                                </span>
                                <span className="leading-tight">{step}</span>
                              </div>
                            ))}
                          </div>
                        <div className="mt-3 text-xs font-semibold text-blue-800 dark:text-blue-200 text-left">
                          Premium boost: Tap <span className="font-extrabold uppercase tracking-wide text-blue-700 dark:text-blue-200">Recommend Combination</span> to auto-pick the best-fit persona + constraints for this industry (it will replace your current selections) before you run.
                        </div>
                          <div className="mt-3 space-y-1 text-left text-xs text-gray-700 dark:text-gray-300">
                            <div className="font-semibold text-gray-800 dark:text-gray-100">Optional (Premium)</div>
                            <div>• Set <span className="font-semibold text-indigo-700 dark:text-indigo-300">Creativity</span> (safe ↔ bold)</div>
                            <div>• Set <span className="font-semibold text-indigo-700 dark:text-indigo-300">Idea Diversity</span> (focused ↔ varied)</div>
                          </div>
                          <div className="mt-3 text-left text-sm font-semibold">
                            <span className="inline-flex items-center gap-2 rounded-md bg-blue-600 px-2.5 py-1 text-white shadow">
                              Click “Generate Ideas”
                            </span>
                            <span className="ml-2 text-gray-800 dark:text-gray-200">— adjust and rerun anytime</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {!isLoading && Object.keys(results).length > 0 && (
                  <div className="space-y-5">
                    {rankResult ? (
                      <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <div className="text-[15px] font-semibold text-gray-900 dark:text-white">Model ranking</div>
                            <div className="mt-1 text-[13px] text-gray-600 dark:text-gray-300">
                              Automatic ranking for this run based on clarity, feasibility, differentiation, actionability, risks, and stakeholder readiness.
                            </div>
                            <div className="mt-1 text-[12px] text-gray-500 dark:text-gray-400">
                              Configuration: {industry || "Industry"} · {labelForPersona(tone)} · {formatConstraints(constraints)}
                            </div>
                          </div>
                          {!rankResult.skipped ? (
                            <button
                              type="button"
                              onClick={() => setRankResultOpen((prev) => !prev)}
                              className="rounded-lg border border-black/10 dark:border-white/10 px-3 py-1.5 text-[12px] font-semibold text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                            >
                              {rankResultOpen ? "Hide rank results" : "Show rank results"}
                            </button>
                          ) : null}
                        </div>
                        {rankResult.skipped ? (
                          <div className="mt-3 text-[13px] text-gray-500 dark:text-gray-400">
                            {rankResult.reason || "Ranking not available for a single model."}
                          </div>
                        ) : (
                          <>
                            {rankResult.summary ? (
                              <div className="mt-3 text-[13px] text-gray-600 dark:text-gray-300">
                                {rankResult.summary}
                              </div>
                            ) : null}
                            {rankResultOpen ? (
                              <div className="mt-3 space-y-3">
                                {Array.isArray(rankResult.highlights) && rankResult.highlights.length >= 5 ? (
                                  <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 px-3 py-2">
                                    <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Highlights</div>
                                    <ul className="mt-2 space-y-1 text-[12px] text-gray-600 dark:text-gray-300">
                                      {rankResult.highlights.slice(0, 7).map((item, idx) => (
                                        <li key={idx}>• {item}</li>
                                      ))}
                                    </ul>
                                  </div>
                                ) : null}
                                {[...(rankResult.ranked_models || [])]
                                  .sort((a, b) => (a.rank || 0) - (b.rank || 0))
                                  .map((item) => {
                                    const modelLabel = labelForModelId(item.model_id);
                                    const title = rankResult.title_map?.[item.model_id] || item.title || modelLabel;
                                    return (
                                      <div
                                        key={`${item.model_id}-${item.rank}`}
                                        className="rounded-lg border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 px-3 py-2"
                                      >
                                        <div className="text-[13px] font-semibold text-gray-900 dark:text-white">
                                          {item.rank}. {title}
                                        </div>
                                        <div className="text-[12px] text-gray-500 dark:text-gray-400">
                                          Model: {modelLabel}
                                          {typeof item.score === "number" ? ` · Score ${item.score}` : ""}
                                        </div>
                                        {item.rationale ? (
                                          <div className="mt-1 text-[12px] text-gray-600 dark:text-gray-300">
                                            {item.rationale}
                                          </div>
                                        ) : null}
                                      </div>
                                    );
                                  })}
                              </div>
                            ) : null}
                          </>
                        )}
                      </div>
                    ) : null}
                    <div className="flex flex-wrap gap-2">
                      {Object.keys(results).map((modelId) => {
                        const label = labelForModelId(modelId);
                        const active = activeTab === modelId;

                        return (
                          <button
                            key={modelId}
                            type="button"
                            onClick={() => setActiveTab(modelId)}
                            className={cx(
                              "rounded-full border px-3 py-1.5 text-sm font-semibold transition",
                              "border-black/10 dark:border-white/10",
                              active
                                ? "bg-blue-600 text-white"
                                : "bg-white/50 dark:bg-white/5 text-gray-800 dark:text-gray-200 hover:bg-white/70 dark:hover:bg-white/10"
                            )}
                          >
                            {label}
                          </button>
                        );
                      })}
                    </div>

                    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-5 lg:p-6">
                      {Object.entries(results).map(([modelId, htmlContent]) => (
                        <div key={modelId} className={activeTab === modelId ? "block" : "hidden"}>
                          <div className="prose dark:prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: htmlContent }} />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : resultsView === "insights" ? (
              <div className="mt-4 space-y-4">
                {!showInsights ? (
                  <div className="rounded-xl border border-dashed border-black/15 dark:border-white/15 p-10 text-center">
                    <div className="mx-auto max-w-md text-left space-y-4">
                      <div className="rounded-xl bg-white/60 dark:bg-white/5 px-4 py-3 text-center space-y-1">
                        <p className="text-sm font-semibold text-gray-900 dark:text-white">No comparison insights yet</p>
                        <p className="text-sm text-gray-700 dark:text-gray-200">
                          Go to <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results</span> and click the <span className="font-semibold text-indigo-700 dark:text-indigo-300">Compare Results</span> button to load the generated comparison results.
                        </p>
                      </div>

                      <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-4 text-left">
                        <div className="text-sm font-semibold text-gray-900 dark:text-white text-center">Compare Results quick tips</div>
                        <div className="mt-3 space-y-1.5 text-sm text-gray-800 dark:text-gray-100">
                          {[
                            <>Open <span className="font-semibold text-indigo-700 dark:text-indigo-300">Compare Results</span> from <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results</span>.</>,
                            "Click Show under Select two runs.",
                            <>Choose <span className="font-semibold text-indigo-700 dark:text-indigo-300">Run A</span> and <span className="font-semibold text-indigo-700 dark:text-indigo-300">Run B</span> from the list.</>,
                            "Make sure both runs used the same Industry, Persona, and Constraints.",
                            <>Click <span className="font-semibold text-indigo-700 dark:text-indigo-300">Compare</span> to generate the Diff Insight.</>,
                            "Review the winner and key changes, then export if needed.",
                          ].map((tip, idx) => (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 text-[11px] font-semibold text-white/95 shadow-sm">
                                {idx + 1}
                              </span>
                              <span className="leading-tight">{tip}</span>
                            </div>
                          ))}
                        </div>
                        <div className="mt-3 rounded-lg bg-indigo-600/15 px-3 py-2 text-xs font-semibold text-indigo-900 dark:text-indigo-100">
                          Diff Mode compares two saved runs with the same configuration using their top-ranked outputs, highlights what changed, and explains which one is stronger.
                        </div>
                      </div>
                    </div>
                  </div>
                ) : null}

                {compareResult ? (
                  <>
                    <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex items-center gap-2">
                        <div className="text-[15px] font-semibold text-gray-900 dark:text-white">Diff Insight</div>
                          <span className="rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                            Compared top-ranked outputs
                          </span>
                          <HelpTooltip content="Diff Mode compares two saved runs with the same configuration by using the top-ranked output from each run. It highlights key changes, explains why one is stronger, and saves the insight for later. Use Saved Results → Compare Results to generate." />
                        </div>
                        <div className="flex items-center gap-2 text-[12px]">
                          <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 font-semibold text-emerald-700 dark:text-emerald-300">
                            Winner: {compareResult.winner_run_id ? formatRunLabel(compareResult.winner_run_id) : "Tie"}
                          </span>
                          {compareResult.cached ? (
                            <span className="rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-white/70">
                              Saved
                            </span>
                          ) : null}
                        </div>
                      </div>
                      <p className="mt-2 text-[15px] text-gray-700 dark:text-gray-200">
                        {compareResult.comparison.summary}
                      </p>
                      {compareResult.comparison.top_outputs ? (
                        <div className="mt-2 rounded-lg border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 px-3 py-2 text-[12px] text-gray-600 dark:text-gray-300">
                          <div className="font-semibold text-gray-800 dark:text-gray-100">Top outputs compared</div>
                          <div className="mt-1">
                            A: {compareResult.comparison.top_outputs.run_a?.title || "Untitled result"}{" "}
                            <span className="text-gray-500 dark:text-gray-400">
                              ({compareResult.comparison.top_outputs.run_a?.model_label || "Model"})
                            </span>
                            {typeof compareResult.comparison.top_outputs.run_a?.score === "number" ? (
                              <span className="text-gray-500 dark:text-gray-400">
                                {" "}· Score {compareResult.comparison.top_outputs.run_a?.score}
                              </span>
                            ) : null}
                          </div>
                          <div className="mt-1">
                            B: {compareResult.comparison.top_outputs.run_b?.title || "Untitled result"}{" "}
                            <span className="text-gray-500 dark:text-gray-400">
                              ({compareResult.comparison.top_outputs.run_b?.model_label || "Model"})
                            </span>
                            {typeof compareResult.comparison.top_outputs.run_b?.score === "number" ? (
                              <span className="text-gray-500 dark:text-gray-400">
                                {" "}· Score {compareResult.comparison.top_outputs.run_b?.score}
                              </span>
                            ) : null}
                          </div>
                        </div>
                      ) : null}
                      {compareResult.comparison.key_changes?.length ? (
                        <ul className="mt-2 space-y-1 text-[13px] text-gray-600 dark:text-gray-300">
                          {compareResult.comparison.key_changes.map((item, idx) => (
                            <li key={idx}>• {item}</li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="mt-2 text-[13px] text-gray-600 dark:text-gray-300">
                        <span className="font-semibold text-gray-800 dark:text-gray-100">Why:</span>{" "}
                        {compareResult.comparison.winner_rationale}
                      </div>
                      {compareResult.comparison.risks?.length ? (
                        <div className="mt-2 text-[13px] text-amber-600 dark:text-amber-300">
                          Risk: {compareResult.comparison.risks.join(" ")}
                        </div>
                      ) : null}
                    </div>

                    {compareResult.comparison.top_outputs ? (
                      <div className="grid gap-4 lg:grid-cols-2">
                        {(["run_a", "run_b"] as const).map((key) => {
                          const top = compareResult.comparison.top_outputs?.[key];
                          if (!top?.output_html) return null;
                          const runId = key === "run_a" ? compareResult.run_a_id : compareResult.run_b_id;
                          const isWinner = compareResult.winner_run_id === runId;
                          return (
                            <div
                              key={key}
                              className={cx(
                                "rounded-2xl border p-4",
                                "border-black/10 dark:border-white/10",
                                isWinner ? "bg-emerald-500/10 border-emerald-500/40" : "bg-white/60 dark:bg-white/5"
                              )}
                            >
                              <div className="flex flex-wrap items-center justify-between gap-2 text-[13px] font-semibold text-gray-900 dark:text-white">
                                <div>
                                  {key === "run_a" ? "Run A" : "Run B"}: {top.title || "Untitled result"}{" "}
                                  <span className="text-gray-500 dark:text-gray-400">
                                    ({top.model_label || "Model"})
                                  </span>
                                  {typeof top.score === "number" ? (
                                    <span className="ml-2 rounded-full border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-cyan-700 dark:text-cyan-300">
                                      Score {top.score}
                                    </span>
                                  ) : null}
                                </div>
                                {isWinner ? (
                                  <span className="rounded-full border border-emerald-500/40 bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:text-emerald-300">
                                    Winner
                                  </span>
                                ) : null}
                              </div>
                              <div
                                className="prose dark:prose-invert max-w-none mt-3"
                                dangerouslySetInnerHTML={{ __html: top.output_html }}
                              />
                            </div>
                          );
                        })}
                      </div>
                    ) : null}
                  </>
                ) : null}

              </div>
            ) : resultsView === "decision" ? (
              <div className="mt-4 space-y-4">
                {!decisionReport ? (
                  <div className="rounded-xl border border-dashed border-black/15 dark:border-white/15 p-10 text-center">
                    <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-3 text-center space-y-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">No decision report loaded</p>
                      <p className="text-sm text-gray-700 dark:text-gray-200">
                        Go to <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results</span> and click the <span className="font-semibold text-indigo-700 dark:text-indigo-300">Decision Summary Report</span> button to load the decision summary reports.
                      </p>
                    </div>

                    <div className="mt-6 text-left">
                      <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-4">
                        <div className="text-sm font-semibold text-gray-900 dark:text-white text-center">Decision Summary quick tips</div>
                        <div className="mt-3 space-y-1.5 text-sm text-gray-800 dark:text-gray-100">
                          {[
                            <>Open <span className="font-semibold text-indigo-700 dark:text-indigo-300">Decision Summary Report</span> from <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results</span>.</>,
                            <>Click Show under <span className="font-semibold text-indigo-700 dark:text-indigo-300">Select runs for the report</span>.</>,
                            "Choose 1–5 runs you want to summarize.",
                            <>Make sure all selected runs share the same <span className="font-semibold text-indigo-700 dark:text-indigo-300">Industry</span>.</>,
                            <>Click <span className="font-semibold text-indigo-700 dark:text-indigo-300">Decision Summary Report</span> to generate the summary.</>,
                            "Review ranked runs, insights, risks, and next steps.",
                            "Export or email the report if needed.",
                          ].map((tip, idx) => (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 text-[11px] font-semibold text-white/95 shadow-sm">
                                {idx + 1}
                              </span>
                              <span className="leading-tight">{tip}</span>
                            </div>
                          ))}
                        </div>
                        <div className="mt-3 rounded-lg bg-indigo-600/15 px-3 py-2 text-xs font-semibold text-indigo-900 dark:text-indigo-100">
                          The Decision Summary Report ranks the selected runs, highlights the best choice, and packages insights, risks, and next steps in one shareable summary.
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-black/10 dark:border-white/10 bg-white/60 dark:bg-white/5 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className="text-[15px] font-semibold text-gray-900 dark:text-white">Decision Summary Report</div>
                          <HelpTooltip content="Decision Summary Report ranks selected runs, highlights the best choice, and packages insights, risks, and next steps in one shareable summary." />
                        </div>
                        <div className="mt-1 text-[13px] text-gray-600 dark:text-gray-300">
                          Saved: {formatSavedDate(decisionReport.created_at)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={openExecutionPlanPicker}
                          disabled={stakeholderGenerating || reportLoading}
                          className={cx(
                            "inline-flex items-center gap-2 rounded-lg border border-black/10 dark:border-white/10 px-3 py-1.5 text-[12px] font-semibold",
                            stakeholderGenerating || reportLoading
                              ? "text-gray-500 dark:text-gray-400 cursor-not-allowed"
                              : "text-indigo-700 dark:text-indigo-300 hover:bg-white/80 dark:hover:bg-white/10"
                          )}
                        >
                          {stakeholderGenerating ? <Spinner className="h-3.5 w-3.5" /> : null}
                          {stakeholderGenerating ? "Generating Plan..." : "Generate Execution Plan"}
                        </button>
                        <button
                          type="button"
                          onClick={() => decisionReport.id && downloadSavedReport(decisionReport.id)}
                          disabled={reportDownloadId === decisionReport.id}
                          className={cx(
                            "inline-flex items-center gap-2 rounded-lg border border-black/10 dark:border-white/10 px-3 py-1.5 text-[12px] font-semibold",
                            reportDownloadId === decisionReport.id
                              ? "text-gray-500 dark:text-gray-400 cursor-not-allowed"
                              : "text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                          )}
                        >
                          {reportDownloadId === decisionReport.id ? <Spinner className="h-3.5 w-3.5" /> : null}
                          {reportDownloadId === decisionReport.id ? "Preparing PDF..." : "Download PDF"}
                        </button>
                      </div>
                    </div>
                    {decisionReport.report?.summary ? (
                      <div className="mt-3 text-[15px] text-gray-700 dark:text-gray-200">
                        {decisionReport.report.summary}
                      </div>
                    ) : null}
                    {Array.isArray(decisionReport.report?.ranked_runs) && decisionReport.report?.ranked_runs?.length ? (
                      <div className="mt-4 rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-3">
                        <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Ranked runs</div>
                        <div className="mt-2 space-y-2 text-[12px] text-gray-600 dark:text-gray-300">
                          {decisionReport.report?.ranked_runs?.map((item, idx) => {
                            const runId = item.run_id;
                            const run = decisionReport.runs_snapshot?.find((r) => r.id === runId);
                            const outputs = getRunOutputsMeta(run);
                            const topModelId = getTopModelIdForRun(run);
                            const personaLabel = run ? labelForPersona(run.tone || "") : "Not specified";
                            const constraintsLabel = run ? formatConstraints(run.constraints || []) : "Not specified";
                            const runLabel = run
                              ? `${run.industry || "Saved run"} • ${formatSavedDate(run.created_at || "")}`
                              : runId
                              ? formatRunLabel(runId)
                              : "Saved run";
                            return (
                              <div key={`${runId}-${idx}`}>
                                <div className="font-semibold text-gray-900 dark:text-white">
                                  {idx + 1}. {runLabel}
                                  {typeof item.score === "number" ? ` · Score ${item.score}` : ""}
                                </div>
                                {outputs.length ? (
                                  <div className="mt-2 text-[12px] text-gray-500 dark:text-gray-400">
                                    <div className="text-[12px] font-semibold text-gray-700 dark:text-gray-300">Outputs</div>
                                    <ul className="mt-1 space-y-1">
                                      {outputs.map((output) => {
                                        const isTop = output.modelId && output.modelId === topModelId;
                                        return (
                                          <li key={output.modelId}>
                                            <span className={isTop ? "text-emerald-600 dark:text-emerald-300 font-semibold" : ""}>
                                              {output.modelLabel}: {output.title}
                                            </span>
                                            {isTop ? (
                                              <span className="ml-2 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-semibold text-emerald-700 dark:text-emerald-300">
                                                Top
                                              </span>
                                            ) : null}
                                          </li>
                                        );
                                      })}
                                    </ul>
                                  </div>
                                ) : null}
                                <div className="mt-1 text-[12px] text-gray-500 dark:text-gray-400">
                                  Persona: {personaLabel} · Constraints: {constraintsLabel}
                                </div>
                                {item.rationale ? (
                                  <div className="mt-1 text-gray-600 dark:text-gray-300">{item.rationale}</div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                    {Array.isArray(decisionReport.report?.key_insights) && decisionReport.report?.key_insights?.length ? (
                      <div className="mt-4 text-[12px] text-gray-600 dark:text-gray-300">
                        <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Key insights</div>
                        <ul className="mt-2 space-y-1">
                          {decisionReport.report.key_insights.map((item, idx) => (
                            <li key={idx}>• {item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {Array.isArray(decisionReport.report?.risks) && decisionReport.report?.risks?.length ? (
                      <div className="mt-4 text-[12px] text-amber-600 dark:text-amber-300">
                        <div className="text-[13px] font-semibold text-amber-700 dark:text-amber-200">Risks</div>
                        <ul className="mt-2 space-y-1">
                          {decisionReport.report.risks.map((item, idx) => (
                            <li key={idx}>• {item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {Array.isArray(decisionReport.report?.next_steps) && decisionReport.report?.next_steps?.length ? (
                      <div className="mt-4 text-[12px] text-gray-600 dark:text-gray-300">
                        <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Next steps</div>
                        <ul className="mt-2 space-y-1">
                          {decisionReport.report.next_steps.map((item, idx) => (
                            <li key={idx}>• {item}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            ) : (
              <div className="mt-4 space-y-4">
                {!stakeholderReport ? (
                  <div className="rounded-xl border border-dashed border-black/15 dark:border-white/15 p-10 text-center">
                    <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-3 text-center space-y-1">
                      <p className="text-sm font-semibold text-gray-900 dark:text-white">No execution plan loaded</p>
                      <p className="text-sm text-gray-700 dark:text-gray-200">
                        Generate from <span className="font-semibold text-indigo-700 dark:text-indigo-300">Decision Summary Report</span> or open <span className="font-semibold text-indigo-700 dark:text-indigo-300">Saved Results → Execution Plan</span>.
                      </p>
                    </div>

                    <div className="mt-6 text-left">
                      <div className="mx-auto max-w-md rounded-xl bg-white/60 dark:bg-white/5 px-4 py-4">
                        <div className="text-sm font-semibold text-gray-900 dark:text-white text-center">Execution Plan quick tips</div>
                        <div className="mt-3 space-y-1.5 text-sm text-gray-800 dark:text-gray-100">
                          {[
                            <>Open <span className="font-semibold text-indigo-700 dark:text-indigo-300">Decision Summary Report</span> tab.</>,
                            <>Generate or load a decision report first.</>,
                            <>Click <span className="font-semibold text-indigo-700 dark:text-indigo-300">Generate Execution Plan</span>.</>,
                            "Review execution plan, resources, cost, and profit forecast.",
                            "Use Saved Results → Execution Plan to reload previous plans.",
                          ].map((tip, idx) => (
                            <div key={idx} className="flex items-center gap-2">
                              <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-400 to-violet-500 text-[11px] font-semibold text-white/95 shadow-sm">
                                {idx + 1}
                              </span>
                              <span className="leading-tight">{tip}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="rounded-2xl border border-amber-500/45 dark:border-amber-400/45 bg-white/60 dark:bg-white/5 p-4 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <div className="text-[15px] font-semibold text-gray-900 dark:text-white">Execution Plan</div>
                          <InfoPillTooltip
                            content="This is your final business-readiness report. It converts one selected model output into a decision package that includes go/no-go recommendation, execution phases, budget, forecast, risks, and stakeholder actions."
                          />
                        </div>
                        <div className="mt-1 text-[14px] font-semibold text-gray-900 dark:text-white">
                          {executionReportTitle}
                          {labelForModelId(stakeholderReport?.dossier?.decision?.winner?.model_id || "") ? (
                            <span className="ml-2 text-[12px] font-medium text-cyan-700 dark:text-cyan-300">
                              ({labelForModelId(stakeholderReport?.dossier?.decision?.winner?.model_id || "")})
                            </span>
                          ) : null}
                        </div>
                        <div className="mt-1 text-[13px] text-gray-600 dark:text-gray-300">
                          Saved: {formatSavedDate(stakeholderReport.created_at)} · Scenario: {stakeholderReport.scenario_profile}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-[11px] font-semibold text-gray-600 dark:text-gray-300">
                          Horizon: {stakeholderReport.horizon_months} months
                        </span>
                        <button
                          type="button"
                          onClick={downloadPDF}
                          disabled={pdfLoading || executionPresentationLoading}
                          className={cx(
                            "inline-flex items-center gap-2 rounded-lg border border-black/10 dark:border-white/10 px-3 py-1.5 text-[12px] font-semibold",
                            pdfLoading || executionPresentationLoading
                              ? "text-gray-500 dark:text-gray-400 cursor-not-allowed"
                              : "text-gray-700 dark:text-gray-200 hover:bg-white/80 dark:hover:bg-white/10"
                          )}
                        >
                          {pdfLoading ? <Spinner className="h-3.5 w-3.5" /> : null}
                          {pdfLoading ? "Preparing PDF..." : "Download PDF"}
                        </button>
                        <button
                          type="button"
                          onClick={downloadExecutionPresentation}
                          disabled={executionPresentationLoading || pdfLoading}
                          className={cx(
                            "inline-flex items-center gap-2 rounded-lg border border-black/10 dark:border-white/10 px-3 py-1.5 text-[12px] font-semibold",
                            executionPresentationLoading || pdfLoading
                              ? "text-gray-500 dark:text-gray-400 cursor-not-allowed"
                              : "text-indigo-700 dark:text-indigo-300 hover:bg-white/80 dark:hover:bg-white/10"
                          )}
                        >
                          {executionPresentationLoading ? <Spinner className="h-3.5 w-3.5" /> : null}
                          {executionPresentationLoading ? "Preparing deck..." : "Presentation Report"}
                        </button>
                      </div>
                    </div>

                    {stakeholderReport.dossier?.proposal_disclaimer?.message ? (
                      <div className="rounded-xl border border-amber-500/35 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-100">
                        <div className="font-semibold text-amber-200">
                          {stakeholderReport.dossier?.proposal_disclaimer?.title || "Proposal estimate notice"}
                        </div>
                        <div className="mt-1">{stakeholderReport.dossier?.proposal_disclaimer?.message}</div>
                        <div className="mt-1 text-[11px] text-amber-200/90">
                          Basis: {stakeholderReport.dossier?.proposal_disclaimer?.data_basis || "industry benchmarks and deterministic model"}
                          {stakeholderReport.dossier?.proposal_disclaimer?.updated_at
                            ? ` · Updated ${stakeholderReport.dossier?.proposal_disclaimer?.updated_at}`
                            : ""}
                        </div>
                      </div>
                    ) : null}

                    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                      <div className="flex items-center gap-2">
                        <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Executive decision</div>
                        <InfoPillTooltip
                          content="Use this card as the one-screen summary. It explains whether the plan is Go or No-Go, the financial gates behind that verdict, confidence level, and the most important actions required before approval."
                        />
                      </div>
                      <div className="mt-2 text-[13px] text-gray-600 dark:text-gray-300">
                        {stakeholderReport.dossier?.decision?.thesis || "No thesis available."}
                      </div>
                      <div className={cx("mt-3 rounded-lg border px-3 py-2 text-[12px]", executionDecisionTone)}>
                        <div className="font-semibold">
                          {executionDecisionLabel}
                          {executionSupport?.forced_by_rules ? " (financial gates enforced)" : ""}
                        </div>
                        {Array.isArray(executionSupport?.reasons) && executionSupport?.reasons?.length ? (
                          <ul className="mt-1 space-y-1">
                            {executionSupport?.reasons?.slice(0, 3).map((reason, idx) => (
                              <li key={idx}>• {reason}</li>
                            ))}
                          </ul>
                        ) : (
                          <div className="mt-1 opacity-90">Financial gates are within acceptable range for this horizon.</div>
                        )}
                      </div>
                      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                        <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            <TechnicalLabel
                              label="Recommendation"
                              tooltip="Final decision status based on execution quality and financial gate checks."
                            />
                          </div>
                          <div className="mt-1 text-[13px] font-semibold text-gray-900 dark:text-white">{executionDecisionLabel}</div>
                        </div>
                        <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            <TechnicalLabel
                              label="Confidence"
                              tooltip="Confidence in the selected winning output quality; this is not a profit guarantee."
                            />
                          </div>
                          <div className="mt-1 text-[13px] font-semibold text-gray-900 dark:text-white">
                            {typeof stakeholderReport.dossier?.decision?.confidence === "number"
                              ? `${Math.round((stakeholderReport.dossier?.decision?.confidence || 0) * 100)}%`
                              : "N/A"}
                          </div>
                        </div>
                        <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            <TechnicalLabel
                              label="Year 1 Net"
                              tooltip="Projected first-year net profit after all costs (revenue minus COGS and OpEx)."
                            />
                          </div>
                          <div className="mt-1 text-[13px] font-semibold text-gray-900 dark:text-white">
                            {formatCurrencyOrNA(executionGates?.year_1_net_profit, stakeholderReport.currency)}
                          </div>
                        </div>
                        <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            <TechnicalLabel
                              label="Break-even"
                              tooltip="First month where cumulative net profit becomes zero or positive."
                            />
                          </div>
                          <div className="mt-1 text-[13px] font-semibold text-gray-900 dark:text-white">
                            Month {executionGates?.break_even_month || stakeholderReport.dossier?.revenue_profit?.break_even_month || "N/A"}
                          </div>
                        </div>
                        <div className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                          <div className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
                            <TechnicalLabel
                              label="Expected Year 1 Net"
                              tooltip="Probability-weighted Year 1 net profit across conservative, base, and aggressive scenarios."
                            />
                          </div>
                          <div className="mt-1 text-[13px] font-semibold text-gray-900 dark:text-white">
                            {formatCurrencyOrNA(executionGates?.expected_year_1_net_profit, stakeholderReport.currency)}
                          </div>
                        </div>
                      </div>
                      {Array.isArray(executionSupport?.required_actions) && executionSupport?.required_actions?.length ? (
                        <div className="mt-3 text-[12px] text-gray-600 dark:text-gray-300">
                          <div className="font-semibold text-gray-800 dark:text-gray-200">Required before approval</div>
                          <ul className="mt-1 space-y-1">
                            {executionSupport?.required_actions?.slice(0, 3).map((action, idx) => (
                              <li key={idx}>• {action}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                      <div className="mt-3 text-[12px] text-gray-500 dark:text-gray-400">
                        Winner: {stakeholderReport.dossier?.decision?.winner?.title || "N/A"} · Model: {labelForModelId(stakeholderReport.dossier?.decision?.winner?.model_id || "")}
                      </div>
                    </div>

                    <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-4">
                      <div className="flex items-center gap-2">
                        <div className="text-[13px] font-semibold text-sky-100">Business terms and definitions</div>
                        <InfoPillTooltip
                          content="This glossary explains finance and strategy terms used across the report (ARPU, COGS, OpEx, break-even, etc.) so non-technical readers can interpret every card without guesswork."
                        />
                      </div>
                      <div className="mt-1 text-[12px] text-sky-100/90">
                        {executionIndustry
                          ? `This plan is targeted to ${executionIndustry} buyers.`
                          : "This plan converts a ranked idea into an implementation and profitability decision."}
                      </div>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2 text-[12px] text-sky-50/95">
                        <div><span className="font-semibold">ARPU:</span> average revenue earned from one paying customer each month.</div>
                        <div><span className="font-semibold">ICP:</span> ideal customer profile; the exact buyer this plan is built for.</div>
                        <div><span className="font-semibold">OpEx:</span> monthly operating costs (team, tools, cloud, support, marketing).</div>
                        <div><span className="font-semibold">COGS:</span> service delivery cost per customer (AI usage, support, infra).</div>
                        <div><span className="font-semibold">Break-even:</span> first month where cumulative profit turns zero or positive.</div>
                        <div><span className="font-semibold">Confidence:</span> confidence in the selected winner output, not a guarantee of profit.</div>
                      </div>
                    </div>

                    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                      <div className="flex items-center gap-2">
                        <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Execution blueprint</div>
                        <InfoPillTooltip
                          content="This is the delivery timeline. It shows phase-by-phase work, ownership, deliverables, and dependencies so teams know what must happen first, what can run in parallel, and what blocks launch."
                        />
                      </div>
                      {Array.isArray(stakeholderReport.dossier?.execution_blueprint?.phases) && stakeholderReport.dossier?.execution_blueprint?.phases?.length ? (
                        <div className="mt-2 space-y-2">
                          {stakeholderReport.dossier?.execution_blueprint?.phases?.map((phase, idx) => (
                            <div key={idx} className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-3">
                              <div className="text-[12px] font-semibold text-gray-900 dark:text-white">
                                {phase.name || "Phase"} ({phase.start_month || 0}-{phase.end_month || 0})
                              </div>
                              <div className="mt-1 text-[12px] text-gray-600 dark:text-gray-300">
                                Workstreams: {(phase.workstreams || []).join(", ") || "N/A"}
                              </div>
                              <div className="text-[12px] text-gray-600 dark:text-gray-300">
                                Deliverables: {(phase.deliverables || []).join(", ") || "N/A"}
                              </div>
                              <div className="text-[12px] text-gray-500 dark:text-gray-400">
                                Owners: {(phase.owner_roles || []).join(", ") || "N/A"} · Dependencies: {(phase.dependencies || []).join(", ") || "N/A"}
                              </div>
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="mt-2 text-[12px] text-gray-500 dark:text-gray-400">No phase plan available.</div>
                      )}
                      {Array.isArray(stakeholderReport.dossier?.execution_blueprint?.critical_path) && stakeholderReport.dossier?.execution_blueprint?.critical_path?.length ? (
                        <div className="mt-3 text-[12px] text-gray-600 dark:text-gray-300">
                          <div className="font-semibold text-gray-800 dark:text-gray-200">Critical path</div>
                          <ul className="mt-1 space-y-1">
                            {stakeholderReport.dossier?.execution_blueprint?.critical_path?.map((item, idx) => (
                              <li key={idx}>• {item}</li>
                            ))}
                          </ul>
                        </div>
                      ) : null}
                    </div>

                    <div className="grid gap-4 lg:grid-cols-2">
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Budget and unit economics</div>
                          <InfoPillTooltip
                            content="This card combines one-time setup costs with per-customer economics. It helps you check if customer revenue can realistically cover delivery and operating costs as you scale."
                          />
                        </div>
                        <div className="mt-2 space-y-1 text-[12px] text-gray-600 dark:text-gray-300">
                          <div>Setup total: {formatCurrency(stakeholderReport.dossier?.costs?.setup_cost?.total, stakeholderReport.currency)}</div>
                          <div>Engineering: {formatCurrency(stakeholderReport.dossier?.costs?.setup_cost?.engineering, stakeholderReport.currency)}</div>
                          <div>Legal/Compliance: {formatCurrency(stakeholderReport.dossier?.costs?.setup_cost?.legal_compliance, stakeholderReport.currency)}</div>
                          <div>Launch Marketing: {formatCurrency(stakeholderReport.dossier?.costs?.setup_cost?.launch_marketing, stakeholderReport.currency)}</div>
                          <div>
                            <TechnicalLabel
                              label="ARPU (avg revenue per customer/month)"
                              tooltip="Average Revenue Per User: expected monthly revenue generated by one paying customer."
                            />: {formatCurrency(stakeholderReport.dossier?.revenue_profit?.pricing?.arpu_monthly, stakeholderReport.currency)}
                          </div>
                          <div>
                            <TechnicalLabel
                              label="Service delivery cost (COGS) per customer/month"
                              tooltip="Cost of Goods Sold: direct monthly cost to serve one customer (AI, support, infrastructure)."
                            />: {formatCurrency(stakeholderReport.dossier?.costs?.unit_cogs?.per_customer_monthly, stakeholderReport.currency)}
                          </div>
                        </div>
                      </div>
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Stakeholder ask</div>
                          <InfoPillTooltip
                            content="This card states exactly what decision-makers need to approve now: budget, required team support, and immediate next-30-day actions to start execution without delay."
                          />
                        </div>
                        <div className="mt-2 text-[12px] text-gray-600 dark:text-gray-300">
                          Budget required: {formatCurrency(stakeholderReport.dossier?.stakeholder_ask?.budget_required, stakeholderReport.currency)}
                        </div>
                        <div className="mt-1 text-[12px] text-gray-600 dark:text-gray-300">
                          Decision required: {stakeholderReport.dossier?.stakeholder_ask?.decision_required || "N/A"}
                        </div>
                        {Array.isArray(stakeholderReport.dossier?.stakeholder_ask?.team_required) && stakeholderReport.dossier?.stakeholder_ask?.team_required?.length ? (
                          <div className="mt-1 text-[12px] text-gray-500 dark:text-gray-400">
                            Team required: {stakeholderReport.dossier?.stakeholder_ask?.team_required?.join(", ")}
                          </div>
                        ) : null}
                        {Array.isArray(stakeholderReport.dossier?.stakeholder_ask?.next_30_days) && stakeholderReport.dossier?.stakeholder_ask?.next_30_days?.length ? (
                          <div className="mt-2 text-[12px] text-gray-600 dark:text-gray-300">
                            <div className="font-semibold text-gray-800 dark:text-gray-200">Next 30 days</div>
                            <ul className="mt-1 space-y-1">
                              {stakeholderReport.dossier?.stakeholder_ask?.next_30_days?.map((item, idx) => (
                                <li key={idx}>• {item}</li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                      </div>
                    </div>

                    {Array.isArray(stakeholderReport.dossier?.scenarios) && stakeholderReport.dossier?.scenarios?.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Scenario outcomes (Year 1)</div>
                          <InfoPillTooltip
                            content="This compares conservative, base, and aggressive market outcomes. Read it to understand downside risk, expected case, and upside potential before committing resources."
                          />
                        </div>
                        <div className="mt-2 overflow-x-auto">
                          <table className="min-w-full text-[12px]">
                            <thead>
                              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-black/10 dark:border-white/10">
                                <th className="py-1 pr-3 font-semibold">Scenario</th>
                                <th className="py-1 pr-3 font-semibold">
                                  <TechnicalLabel label="Probability" tooltip="Likelihood assigned to each scenario. All scenario probabilities should sum to about 100%." />
                                </th>
                                <th className="py-1 pr-3 font-semibold">
                                  <TechnicalLabel label="Year 1 Revenue" tooltip="Total projected revenue in the first 12 months for this scenario." />
                                </th>
                                <th className="py-1 pr-3 font-semibold">
                                  <TechnicalLabel label="Year 1 Net Profit" tooltip="Projected first-year net profit after subtracting COGS and OpEx." />
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {stakeholderReport.dossier?.scenarios?.map((item, idx) => (
                                <tr key={idx} className="border-b border-black/5 dark:border-white/5 text-gray-700 dark:text-gray-200">
                                  <td className="py-1 pr-3 font-semibold">{item.name || "Scenario"}</td>
                                  <td className="py-1 pr-3">{Math.round(Number(item.probability || 0) * 100)}%</td>
                                  <td className="py-1 pr-3">{formatCurrency(item.year_1_revenue, stakeholderReport.currency)}</td>
                                  <td className="py-1 pr-3">{formatCurrency(item.year_1_net_profit, stakeholderReport.currency)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}

                    {Array.isArray(stakeholderReport.dossier?.sensitivity_analysis?.tests) &&
                    stakeholderReport.dossier?.sensitivity_analysis?.tests?.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Sensitivity analysis</div>
                          <InfoPillTooltip
                            content="This stress-tests the plan by changing key levers like price, conversion, and operating cost. It shows whether your recommendation remains stable when assumptions move."
                          />
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                          Stress tests on ARPU, conversion, and OpEx to evaluate recommendation stability.
                        </div>
                        <div className="mt-2 overflow-x-auto">
                          <table className="min-w-full text-[12px]">
                            <thead>
                              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-black/10 dark:border-white/10">
                                <th className="py-1 pr-3 font-semibold">Test</th>
                                <th className="py-1 pr-3 font-semibold">Year 1 Revenue</th>
                                <th className="py-1 pr-3 font-semibold">Year 1 Net Profit</th>
                                <th className="py-1 pr-3 font-semibold">Break-even</th>
                              </tr>
                            </thead>
                            <tbody>
                              {stakeholderReport.dossier?.sensitivity_analysis?.tests?.map((item, idx) => (
                                <tr key={idx} className="border-b border-black/5 dark:border-white/5 text-gray-700 dark:text-gray-200">
                                  <td className="py-1 pr-3 font-semibold">{item.name || "Test"}</td>
                                  <td className="py-1 pr-3">{formatCurrency(item.year_1_revenue, stakeholderReport.currency)}</td>
                                  <td className="py-1 pr-3">{formatCurrency(item.year_1_net_profit, stakeholderReport.currency)}</td>
                                  <td className="py-1 pr-3">Month {item.break_even_month || "N/A"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {stakeholderReport.dossier?.sensitivity_analysis?.interpretation ? (
                          <div className="mt-2 text-[12px] text-gray-600 dark:text-gray-300">
                            {stakeholderReport.dossier?.sensitivity_analysis?.interpretation}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    {Array.isArray(stakeholderReport.dossier?.revenue_profit?.monthly_projection) && stakeholderReport.dossier?.revenue_profit?.monthly_projection?.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Monthly financial projection</div>
                          <InfoPillTooltip
                            content="This month-by-month table explains how customers, revenue, costs, and profit evolve over time. Use it to identify the loss period, improvement trend, and break-even timing."
                          />
                        </div>
                        <div className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                          Table legend: Revenue = total income · OpEx = operating expenses · Net = revenue minus total costs · Cumulative = running profit or loss.
                        </div>
                        <div
                          className="mt-2 max-h-64 overflow-y-auto overflow-x-auto ig-scrollbar pr-2"
                          style={{ scrollbarGutter: "stable both-edges" as any }}
                        >
                          <table className="min-w-[720px] w-full table-fixed text-[12px]">
                            <colgroup>
                              <col className="w-[7%]" />
                              <col className="w-[15%]" />
                              <col className="w-[19%]" />
                              <col className="w-[19%]" />
                              <col className="w-[19%]" />
                              <col className="w-[21%]" />
                            </colgroup>
                            <thead className="sticky top-0 bg-white/95 dark:bg-slate-900/95">
                              <tr className="text-gray-500 dark:text-gray-400 border-b border-black/10 dark:border-white/10">
                                <th className="py-1.5 px-2 font-semibold text-left whitespace-nowrap">Month</th>
                                <th className="py-1.5 px-2 font-semibold text-right whitespace-nowrap">
                                  <TechnicalLabel label="Customers" tooltip="Projected paying customers at each month." />
                                </th>
                                <th className="py-1.5 px-2 font-semibold text-right whitespace-nowrap">
                                  <TechnicalLabel label="Revenue" tooltip="Total monthly income from customers." />
                                </th>
                                <th className="py-1.5 px-2 font-semibold text-right whitespace-nowrap">
                                  <TechnicalLabel label="OpEx" tooltip="Operating expenses: salaries, tools, cloud, support, marketing, and other recurring costs." />
                                </th>
                                <th className="py-1.5 px-2 font-semibold text-right whitespace-nowrap">
                                  <TechnicalLabel label="Net" tooltip="Net profit for the month after all costs." />
                                </th>
                                <th className="py-1.5 px-2 font-semibold text-right whitespace-nowrap">
                                  <TechnicalLabel label="Cumulative" tooltip="Running total of net profit/loss from month 1 onward." />
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {stakeholderReport.dossier?.revenue_profit?.monthly_projection?.map((row, idx) => (
                                <tr key={idx} className="border-b border-black/5 dark:border-white/5 text-gray-700 dark:text-gray-200">
                                  <td className="py-1.5 px-2 text-left tabular-nums whitespace-nowrap">{row.month}</td>
                                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">{Number(row.customers || 0).toLocaleString()}</td>
                                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(row.revenue, stakeholderReport.currency)}</td>
                                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(row.opex, stakeholderReport.currency)}</td>
                                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(row.net_profit, stakeholderReport.currency)}</td>
                                  <td className="py-1.5 px-2 text-right tabular-nums whitespace-nowrap">{formatCurrency(row.cumulative_net_profit, stakeholderReport.currency)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}

                    {Array.isArray(stakeholderReport.dossier?.resources?.roles) && stakeholderReport.dossier?.resources?.roles?.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Resource plan</div>
                          <InfoPillTooltip
                            content="This staffing plan shows which roles are needed, in what capacity (FTE), and at what cost. It helps align hiring pace with delivery scope and financial limits."
                          />
                        </div>
                        <div className="mt-2 overflow-x-auto">
                          <table className="w-full table-fixed text-[12px]">
                            <colgroup>
                              <col className="w-[33%]" />
                              <col className="w-[20%]" />
                              <col className="w-[17%]" />
                              <col className="w-[30%]" />
                            </colgroup>
                            <thead>
                              <tr className="text-gray-500 dark:text-gray-400 border-b border-black/10 dark:border-white/10">
                                <th className="py-1 pr-3 font-semibold text-left">Role</th>
                                <th className="py-1 pr-3 font-semibold text-left">Type</th>
                                <th className="py-1 pr-3 font-semibold text-right">
                                  <TechnicalLabel label="Avg FTE" tooltip="Average Full-Time Equivalent staffing level for this role across the horizon." />
                                </th>
                                <th className="py-1 pr-3 font-semibold text-right">Avg Monthly Cost</th>
                              </tr>
                            </thead>
                            <tbody>
                              {stakeholderReport.dossier?.resources?.roles?.map((role, idx) => {
                                const ftes = role.fte_by_month || [];
                                const costs = role.cost_monthly || [];
                                const avgFte = ftes.length ? (ftes.reduce((sum, val) => sum + Number(val || 0), 0) / ftes.length) : 0;
                                const avgCost = costs.length ? (costs.reduce((sum, val) => sum + Number(val || 0), 0) / costs.length) : 0;
                                return (
                                  <tr key={idx} className="border-b border-black/5 dark:border-white/5 text-gray-700 dark:text-gray-200">
                                    <td className="py-1 pr-3 font-semibold">{role.role || "Role"}</td>
                                    <td className="py-1 pr-3">{role.employment_type || "N/A"}</td>
                                    <td className="py-1 pr-3 text-right tabular-nums">{avgFte.toFixed(2)}</td>
                                    <td className="py-1 pr-3 text-right tabular-nums">{formatCurrency(avgCost, stakeholderReport.currency)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                        {Array.isArray(stakeholderReport.dossier?.resources?.tooling) && stakeholderReport.dossier?.resources?.tooling?.length ? (
                          <div className="mt-3 text-[12px] text-gray-600 dark:text-gray-300">
                            Tooling: {stakeholderReport.dossier?.resources?.tooling?.map((tool) => `${tool.name} (${formatCurrency(tool.monthly_cost, stakeholderReport.currency)}/mo)`).join(" · ")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    {Array.isArray(stakeholderReport.dossier?.risks) && stakeholderReport.dossier?.risks?.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Risk register</div>
                          <InfoPillTooltip
                            content="This is the risk control sheet. It lists major risks, likely impact and probability, mitigation approach, owner, and trigger conditions to support accountable execution."
                          />
                        </div>
                        <div className="mt-2 space-y-2">
                          {stakeholderReport.dossier?.risks?.map((risk, idx) => (
                            <div key={idx} className="rounded-lg border border-black/10 dark:border-white/10 bg-white/80 dark:bg-white/5 p-2">
                              <div className="text-[12px] font-semibold text-gray-900 dark:text-white">
                                {risk.category || "Risk"} · Impact {risk.impact || "N/A"} · Probability {risk.probability || "N/A"}
                              </div>
                              <div className="mt-1 text-[12px] text-gray-600 dark:text-gray-300">{risk.description || "No description."}</div>
                              <div className="mt-1 text-[12px] text-gray-500 dark:text-gray-400">
                                Mitigation: {risk.mitigation || "N/A"} · Owner: {risk.owner_role || "N/A"} · Trigger: {risk.trigger || "N/A"}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {Array.isArray(stakeholderReport.assumptions) && stakeholderReport.assumptions.length ? (
                      <div className="rounded-xl border border-black/10 dark:border-white/10 bg-white/70 dark:bg-white/5 p-4">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-gray-800 dark:text-gray-200">Assumptions</div>
                          <InfoPillTooltip
                            content="These are the input assumptions used to compute the forecast (pricing, customer growth, costs, and constraints). If assumptions change, outputs and recommendation can change."
                          />
                        </div>
                        <div className="mt-2 max-h-56 overflow-auto ig-scrollbar">
                          <table className="min-w-full text-[12px]">
                            <thead className="sticky top-0 bg-white/95 dark:bg-slate-900/95">
                              <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-black/10 dark:border-white/10">
                                <th className="py-1 pr-3 pl-2 sm:pl-3 font-semibold">Key</th>
                                <th className="py-1 pr-3 font-semibold">Value</th>
                                <th className="py-1 pr-3 font-semibold">Unit</th>
                                <th className="py-1 pr-3 font-semibold">Source</th>
                                <th className="py-1 pr-3 font-semibold">
                                  <TechnicalLabel label="Confidence" tooltip="Reliability level of each assumption source (low, medium, high)." />
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {stakeholderReport.assumptions.map((item, idx) => (
                                <tr key={idx} className="border-b border-black/5 dark:border-white/5 text-gray-700 dark:text-gray-200">
                                  <td className="py-1 pr-3 pl-2 sm:pl-3">{item.key}</td>
                                  <td className="py-1 pr-3">{String(item.value)}</td>
                                  <td className="py-1 pr-3">{item.unit}</td>
                                  <td className="py-1 pr-3">{item.source}</td>
                                  <td className="py-1 pr-3">{item.confidence}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ) : null}

                    {executionRecovery?.enabled ? (
                      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
                        <div className="flex items-center gap-2">
                          <div className="text-[13px] font-semibold text-amber-200">Profitability recovery plan</div>
                          <InfoPillTooltip
                            content="This card appears when the plan needs financial correction. It proposes concrete levers, recovery scenarios, and 90-day experiments to close the profit gap and re-qualify for approval."
                          />
                        </div>
                        <div className="text-[12px] text-amber-100/90">
                          Monthly profit gap to close: <span className="font-semibold">{formatCurrencyOrNA(executionRecovery?.monthly_profit_gap, stakeholderReport.currency)}</span>
                        </div>
                        {Array.isArray(executionRecovery?.levers) && executionRecovery?.levers?.length ? (
                          <div className="grid gap-2 sm:grid-cols-3">
                            {executionRecovery?.levers?.map((lever, idx) => (
                              <div key={idx} className="rounded-lg border border-amber-500/20 bg-black/10 p-2">
                                <div className="text-[12px] font-semibold text-amber-100">{lever.name || "Lever"}</div>
                                <div className="mt-1 text-[11px] text-amber-50/90">{lever.target || "N/A"}</div>
                                <div className="mt-1 text-[11px] text-amber-200/90">
                                  Impact: {formatCurrencyOrNA(lever.estimated_monthly_impact, stakeholderReport.currency)}/month
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}
                        {Array.isArray(executionRecovery?.scenarios) && executionRecovery?.scenarios?.length ? (
                          <div className="overflow-x-auto">
                            <table className="min-w-full text-[12px]">
                              <thead>
                                <tr className="text-left text-amber-100/80 border-b border-amber-500/20">
                                  <th className="py-1 pr-3 font-semibold">Recovery scenario</th>
                                  <th className="py-1 pr-3 font-semibold">
                                    <TechnicalLabel label="Monthly impact" tooltip="Estimated monthly profit uplift if this recovery scenario is executed." />
                                  </th>
                                  <th className="py-1 pr-3 font-semibold">
                                    <TechnicalLabel label="Est. Year 1 Net" tooltip="Estimated first-year net profit after applying the recovery scenario." />
                                  </th>
                                  <th className="py-1 pr-3 font-semibold">
                                    <TechnicalLabel label="Est. break-even" tooltip="Estimated break-even month after applying this recovery scenario." />
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {executionRecovery?.scenarios?.map((scenario, idx) => (
                                  <tr key={idx} className="border-b border-amber-500/10 text-amber-50/95">
                                    <td className="py-1 pr-3 font-semibold">
                                      {scenario.name || "Scenario"}
                                      {Array.isArray(scenario.moves) && scenario.moves.length ? (
                                        <div className="font-normal text-[11px] text-amber-100/80 mt-0.5">{scenario.moves.slice(0, 2).join(" • ")}</div>
                                      ) : null}
                                    </td>
                                    <td className="py-1 pr-3">{formatCurrencyOrNA(scenario.estimated_monthly_impact, stakeholderReport.currency)}</td>
                                    <td className="py-1 pr-3">{formatCurrencyOrNA(scenario.estimated_year_1_net_profit, stakeholderReport.currency)}</td>
                                    <td className="py-1 pr-3">Month {scenario.estimated_break_even_month || "N/A"}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : null}
                        {Array.isArray(executionRecovery?.experiments_90_days) && executionRecovery?.experiments_90_days?.length ? (
                          <div className="text-[12px] text-amber-100/95">
                            <div className="font-semibold text-amber-100">90-day experiments</div>
                            <ul className="mt-1 space-y-1">
                              {executionRecovery?.experiments_90_days?.slice(0, 5).map((exp, idx) => (
                                <li key={idx}>
                                  • <span className="font-semibold">{exp.name || "Experiment"}</span> ({exp.owner || "Owner"}) — {exp.target_metric || "Target metric"} · D{exp.deadline_days || 0} · {formatCurrencyOrNA(exp.expected_monthly_impact, stakeholderReport.currency)}/month
                                </li>
                              ))}
                            </ul>
                          </div>
                        ) : null}
                        {executionRecovery?.approval_gate ? (
                          <div className="text-[12px] text-amber-100 border-t border-amber-500/20 pt-2">
                            <span className="font-semibold">Approval gate:</span> {executionRecovery.approval_gate}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="text-[11px] text-gray-500 dark:text-gray-400">
                      Source: {stakeholderReport.source_type} #{stakeholderReport.source_id} · Model: {stakeholderReport.model || "N/A"} ·
                      Generator: {stakeholderReport.dossier?.provenance?.generator_version || "N/A"}
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        </GlassCard>
      </section>
    </div>
  );
}

export default function Product() {
  const { user, isLoaded } = useUser();
  const { getToken } = useAuth();

  const [isPremium, setIsPremium] = useState(false);
  const [planLoading, setPlanLoading] = useState(true);
  const [initialUsage, setInitialUsage] = useState<any>({});

  const displayName = !isLoaded
    ? ""
    : user?.fullName || user?.firstName || user?.username || user?.primaryEmailAddress?.emailAddress || "";

  useEffect(() => {
    let cancelled = false;

    if (!isLoaded) return () => {
      cancelled = true;
    };

    if (!user) {
      setIsPremium(false);
      setInitialUsage({});
      setPlanLoading(false);
      return () => {
        cancelled = true;
      };
    }

    (async () => {
      try {
        setPlanLoading(true);
        const jwt = await getToken(tokenOptions());
        if (!jwt) throw new Error("no_token");

        const res = await fetch("/api/subscription", {
          method: "GET",
          headers: { Authorization: `Bearer ${jwt}` },
        });
        if (!res.ok) throw new Error(`subscription_${res.status}`);

        const data = await res.json();
        const premiumByFlag = Boolean(data?.is_premium);
        const plan = String(data?.plan || "");
        const premiumByPlan = plan === "u:premium_subscription" || plan.includes("premium");

        if (!cancelled) {
          setIsPremium(premiumByFlag || premiumByPlan);
          setInitialUsage(data.usage || {});
        }
      } catch {
        if (!cancelled) {
          setIsPremium(false);
          setInitialUsage({});
        }
      } finally {
        if (!cancelled) setPlanLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [getToken, isLoaded, user]);

  return (
    <main className="min-h-screen overflow-x-hidden bg-[radial-gradient(1200px_circle_at_20%_-10%,rgba(59,130,246,0.25),transparent_55%),radial-gradient(900px_circle_at_90%_20%,rgba(99,102,241,0.22),transparent_55%),linear-gradient(to_bottom,#050814,#040615)]">
      {planLoading ? (
        <FullPageLoader
          title="Checking your plan"
          subtitle="Syncing your plan and usage limits…"
          note="This usually takes a few seconds."
          tip=""
        />
      ) : null}
      <div className="sticky top-0 z-40 border-b border-white/10 bg-black/20 backdrop-blur">
        <div className="mx-auto max-w-[1400px] px-4 py-4 flex items-center justify-between">
          <Link href="/" className="text-lg font-semibold text-white tracking-tight">
            IdeaGen
          </Link>

          <div className="flex items-center gap-4">

            {displayName ? (
              <span className="hidden sm:inline text-sm text-white/80 truncate max-w-[180px]">
                {displayName}
              </span>
            ) : null}

            <span
              className={cx(
                "hidden sm:inline rounded-full border px-2 py-1 text-[11px] font-semibold",
                planLoading ? "border-white/10 bg-white/5 text-white/70" : isPremium
                ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
                : "border-white/10 bg-white/5 text-white/70"
              )}
            >
              {planLoading ? "Checking…" : isPremium ? "Premium" : "Free"}
            </span>

            <UserButton afterSignOutUrl="/" />
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] px-4 py-10 overflow-x-hidden">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-semibold text-white tracking-tight">Business Idea Generator</h1>
          <p className="mt-2 text-sm sm:text-base text-white/70">
            Turn early ideas into confident business decisions in one guided flow—generate concepts, compare the best options,
            select the strongest direction, and export an executive-ready plan for stakeholder approval.
          </p>
        </div>

        <Protect plan="premium_subscription" fallback={<IdeaGenerator isPremium={false} planLoaded={true} />}>
          <IdeaGenerator isPremium={isPremium} planLoaded={!planLoading} initialUsage={initialUsage} />
        </Protect>

        {!isPremium && !planLoading ? (
          <section
            id="pricing-table"
            className="mt-14 scroll-mt-24 rounded-3xl border border-white/10 bg-white/5 p-6 sm:p-8 text-white shadow-[0_30px_80px_-60px_rgba(15,23,42,0.9)]"
          >
            <div className="mb-6">
              <p className="text-[11px] uppercase tracking-[0.35em] text-emerald-200/80">
                Upgrade
              </p>
              <h2 className="mt-2 text-2xl sm:text-3xl font-semibold text-white">
                Unlock Premium access
              </h2>
              <p className="mt-2 text-sm text-white/70">
                Upgrade to remove limits and access all models, comparisons, and export features.
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-black/30 p-4">
              <PricingTable />
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
