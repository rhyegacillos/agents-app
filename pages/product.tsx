"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Protect, UserButton, useAuth, useUser, useClerk } from "@clerk/nextjs";



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

const MODELS = [
  { id: "gpt-5-nano", label: "OpenAI" },
  { id: "gemini-2.5-pro", label: "Gemini" },
  { id: "deepseek-chat", label: "DeepSeek" },
  { id: "grok-4-1-fast-reasoning", label: "Grok" },
];

type IdeaResults = { [key: string]: string };

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

function HelpTooltip({ content }: { content: string }) {
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
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 p-2.5 text-xs leading-relaxed text-white bg-slate-800 border border-white/10 rounded-lg shadow-xl z-50 pointer-events-none">
          {content}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-800" />
        </div>
      )}
    </div>
  );
}

function FullPageLoader({
  title,
  subtitle,
  chips,
}: {
  title: string;
  subtitle?: string;
  chips?: string[];
}) {
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

                  <div className="mt-6 text-sm text-white/60">
                    Reasoning models may take longer. Keep this tab open — results will appear automatically.
                  </div>

                  <div className="mt-6 border-t border-white/10 pt-5 flex items-center justify-between">
                    <div className="text-xs text-white/50">
                      Tip: selecting fewer models returns faster.
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

function LimitModal({
  open,
  onClose,
  title,
  message,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  message: string;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[200] grid place-items-center bg-black/60 p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-md rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl p-6 text-white shadow-2xl">
        <div className="text-lg font-semibold text-red-200">{title}</div>
        <p className="mt-2 text-sm text-white/70">
          {message}
        </p>
        <div className="mt-5 flex gap-2">
          <button
            type="button"
            className="flex-1 rounded-xl border border-white/10 bg-white/5 px-4 py-2 text-sm font-semibold hover:bg-white/10"
            onClick={onClose}
          >
            Close
          </button>
        </div>
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

  const clear = () => onChange([NONE]);

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

              // "None" is always allowed; premium lock applies to the rest
              const optionPremiumLocked = opt !== NONE && !isPremium && idx >= freeAllowedCount;

              // enforce max only on non-NONE selections
              const nonNoneCount = value.filter((v) => v !== NONE).length;
              const disabledByCount = opt !== NONE && !checked && nonNoneCount >= maxSelected;

              const disabled = optionPremiumLocked || disabledByCount;

              return (
                <label
                  key={opt}
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
            <button
              type="button"
              onClick={clear}
              className="text-[11px] font-semibold px-2 py-1 rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 text-white/80"
            >
              Reset
            </button>
          </div>
        </div>
      )}
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

  const [results, setResults] = useState<IdeaResults>({});
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("");
  const [industry, setIndustry] = useState(INDUSTRIES[0]);
  const [constraints, setConstraints] = useState<string[]>([CONSTRAINTS[0]]);
  const [tone, setTone] = useState(PERSONAS[0].id);
  const [selectedModels, setSelectedModels] = useState<string[]>([MODELS[0].id]);
  const [temperature, setTemperature] = useState(0.7);
  const [topP, setTopP] = useState(0.9);
  const [tokenUsage, setTokenUsage] = useState<any>(initialUsage);
  const [limitModal, setLimitModal] = useState({ open: false, title: "", message: "" });

  const apiLimit = isPremium ? 5 : 1;
  const emailLimit = isPremium ? 10 : 0;
  const isApiLimited = (tokenUsage.api_calls_count || 0) >= apiLimit;
  const isEmailLimited = (tokenUsage.emails_sent_count || 0) >= emailLimit;

  useEffect(() => {
    if (initialUsage && typeof initialUsage.total_tokens === 'number') {
      setTokenUsage(initialUsage);
    }
  }, [initialUsage]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const jwt = await getToken();
        if (!jwt) return;
        const res = await fetch("/api/subscription", {
          headers: { Authorization: `Bearer ${jwt}` },
        });
        if (res.ok) {
          const data = await res.json();
          if (data.usage) setTokenUsage(data.usage);
        }
      } catch (e) {
        // silent
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [getToken]);

  const [email, setEmail] = useState("");
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailStatus, setEmailStatus] = useState("");

  const [recoLoading, setRecoLoading] = useState(false);
  const [recoHtml, setRecoHtml] = useState<string>("");

  const [pdfLoading, setPdfLoading] = useState(false);

  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const FREE_ALLOWED_CONSTRAINTS = 3; // first 3 options (including "None")
  const FREE_MAX_CONSTRAINTS = 1;
  const FREE_MAX_MODELS = 1;

  const { openUserProfile, openSignIn } = useClerk();
  const { isSignedIn } = useUser();

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

  const selectedModelLabels = useMemo(
    () =>
      selectedModels
        .map((id) => MODELS.find((m) => m.id === id)?.label ?? id)
        .filter(Boolean),
    [selectedModels]
  );

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

    setIsLoading(true);
    setResults({});
    setActiveTab(safeModels[0]);
    setEmailStatus("");

    const jwt = await getToken();

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

      if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
      const data = await response.json();
      
      const resultsData = data.results || data;
      setResults(resultsData);
      addUsage(data.usage);
      
      const keys = Object.keys(resultsData);
      if (keys.length > 0) setActiveTab(keys[0]);
    } catch (e: any) {
      if (e.message.includes("429")) {
        setLimitModal({
          open: true,
          title: "Rate Limit Reached",
          message: "You have reached the API call limit for this minute. Please wait a moment before trying again."
        });
      } else {
        alert(`An error occurred: ${e.message}`);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const recommendCombination = async () => {
    if (!isPremium) {
      if (planLoaded) openUserProfile();
      return;
    }

    setRecoLoading(true);
    setRecoHtml("");

    const jwt = await getToken();

    try {
      const res = await fetch("/api/recommend-combination", {
        method: "POST",
        headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
        body: JSON.stringify({ industry, constraints: CONSTRAINTS, personas: PERSONAS }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || res.statusText);

      addUsage(data.usage);

      const nextConstraints: string[] =
        Array.isArray(data?.recommended_constraints) && data.recommended_constraints.length
          ? data.recommended_constraints
          : [CONSTRAINTS[0]];

      setConstraints(nextConstraints);
      if (data?.recommended_persona) setTone(data.recommended_persona);
      if (data?.reason_html) setRecoHtml(data.reason_html);
    } catch (e: any) {
      alert(`Recommend error: ${e.message}`);
    } finally {
      setRecoLoading(false);
    }
  };

  const getReportPayload = () => ({ industry, constraints, tone, models: Object.keys(results), results });

  const downloadPDF = async () => {
    if (!isPremium) {
      if (planLoaded) openUpgrade();
      return;
    }

    setPdfLoading(true);
    try {
      const response = await fetch("/api/download-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(getReportPayload()),
      });

      if (!response.ok) {
        alert("Failed to download PDF.");
        return;
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);

      const safeIndustry = String(industry || "industry")
        .trim()
        .replace(/\s+/g, "_")
        .replace(/[^a-zA-Z0-9_-]/g, "");

      const d = new Date();
      const stamp =
        `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}_` +
        `${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}${String(d.getSeconds()).padStart(2, "0")}`;

      const filename = `IdeaGen_${safeIndustry}_${stamp}.pdf`;

      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } finally {
      setPdfLoading(false);
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

    const jwt = await getToken();
    try {
      const response = await fetch("/api/email", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${jwt}` },
        body: JSON.stringify({ ...getReportPayload(), to_email: email }),
      });

      setEmailStatus(response.ok ? "Email sent successfully!" : "Failed to send email.");
    } catch {
      setEmailStatus("Failed to send email.");
    } finally {
      setSendingEmail(false);
    }
  };

  const hasResults = !isLoading && Object.keys(results).length > 0;

  // UI gating values (keeps premium UI; free is locked)
  const maxConstraints = isPremium ? 3 : FREE_MAX_CONSTRAINTS;
  const freeAllowedConstraints = FREE_ALLOWED_CONSTRAINTS;
  const maxModels = isPremium ? MODELS.length : FREE_MAX_MODELS;

  // inside your component (near other state)
  const [industryOpen, setIndustryOpen] = useState(false);
  const [industryQuery, setIndustryQuery] = useState("");
  const [industryActive, setIndustryActive] = useState(0);
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


  // AI Persona dropdown (Target-Industry style, single select)
  const [personaOpen, setPersonaOpen] = useState(false);
  const [personaQuery, setPersonaQuery] = useState("");
  const [personaActive, setPersonaActive] = useState(0);
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



  return (
    <div className="grid grid-cols-1 lg:grid-cols-[380px_1fr] gap-6 lg:gap-8">
      <UpgradeModal open={upgradeOpen} onClose={() => setUpgradeOpen(false)} onUpgrade={upgradeTo} />
      <LimitModal 
        open={limitModal.open} 
        onClose={() => setLimitModal({ ...limitModal, open: false })} 
        title={limitModal.title} 
        message={limitModal.message} 
      />

      {isLoading ? (
        <FullPageLoader
          title="Generating ideas"
          subtitle={`Running ${selectedModels.length} model(s)…`}
          chips={selectedModelLabels}
        />
      ) : null}

      {/* Sidebar */}
      <aside className="lg:sticky lg:top-24 h-fit overflow-visible">
        <GlassCard className="p-5 overflow-visible">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">Configuration</h2>
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
                onClick={handleAccountClick}
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
                    <div className="p-2 max-h-64 overflow-y-auto ig-scrollbar bg-slate-950/95" role="listbox">
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
                              onMouseEnter={() => setIndustryActive(idx)}
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
                      <div className="p-2 max-h-64 overflow-y-auto ig-scrollbar bg-slate-950/95">
                        {filteredPersonas.length === 0 ? (
                          <div className="px-2 py-3 text-sm text-gray-400">No matches.</div>
                        ) : (
                          filteredPersonas.map((p, idx) => {
                            const active = idx === personaActive;
                            const selected = p.id === tone;

                            const originalIdx = PERSONAS.findIndex((x) => x.id === p.id);
                            const locked = !isPremium && originalIdx > 0;

                            return (
                              <button
                                key={p.id}
                                type="button"
                                onMouseEnter={() => setPersonaActive(idx)}
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
                    </div>
                  )}
                </div>
              </div>


            </div>

            <div>
              <button
                type="button"
                onClick={recommendCombination}
                disabled={recoLoading || isApiLimited}
                className={cx(
                  "w-full rounded-xl border px-3 py-2.5 text-sm font-semibold",
                  "border-black/10 dark:border-white/10",
                  "bg-white/50 dark:bg-white/5",
                  (recoLoading || isApiLimited) && "opacity-70 cursor-not-allowed",
                  (!recoLoading && !isApiLimited) && "hover:bg-white/70 dark:hover:bg-white/10"
                )}
              >
                <span className="inline-flex items-center justify-center gap-2">
                  {recoLoading ? <Spinner className="h-4 w-4" /> : null}
                  <span>
                    {recoLoading ? "Recommending..." : isApiLimited ? "Rate Limit Reached" : "Recommend Combination"}
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
                    <HelpTooltip content="Fine-tune the AI's output behavior. Only available on Premium." />
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
              disabled={isLoading || isApiLimited}
              className={cx(
                "w-full rounded-xl px-3 py-3 text-sm font-semibold text-white",
                (isLoading || isApiLimited) ? "bg-gray-400 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
              )}
            >
              <span className="inline-flex items-center justify-center gap-2">
                {isLoading ? <Spinner className="h-4 w-4" /> : null}
                <span>
                  {isLoading ? "Generating..." : isApiLimited ? "Rate Limit Reached" : "Generate Ideas"}
                </span>
              </span>
            </button>

            {hasResults && (
              <div className="pt-5 mt-5 border-t border-black/10 dark:border-white/10 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Export</h3>
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
      <section>
        <GlassCard className="mb-6 p-5">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white mb-4">Current Usage</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              
              <div className="flex flex-col">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Tokens</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">Total usage</p>
                <div className="mt-1 text-lg font-bold text-gray-900 dark:text-white">
                  {(tokenUsage.total_tokens || 0).toLocaleString()}
                  <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                    {" / " + (isPremium ? "2M" : "100k")}
                  </span>
                </div>
              </div>

              <div className="flex flex-col">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">API Calls</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">Last minute</p>
                <div className="mt-1 text-lg font-bold text-gray-900 dark:text-white">
                  {(tokenUsage.api_calls_count || 0)}
                  <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                    {" / " + (isPremium ? "5" : "1")}
                  </span>
                </div>
              </div>

              <div className="flex flex-col">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">Emails</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400">Today</p>
                <div className="mt-1 text-lg font-bold text-gray-900 dark:text-white">
                  {(tokenUsage.emails_sent_count || 0)}
                  <span className="text-sm font-normal text-gray-500 dark:text-gray-400">
                    {" / " + (isPremium ? "10" : "0")}
                  </span>
                </div>
              </div>

            </div>
          </GlassCard>

        <GlassCard className="min-h-[680px] p-6 lg:p-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-gray-900 dark:text-white">Results</h2>
              <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">Switch tabs to compare model outputs.</p>
            </div>

            {hasResults && (
              <div className="text-xs text-gray-600 dark:text-gray-400">
                {selectedModels.length} model{selectedModels.length > 1 ? "s" : ""}
              </div>
            )}
          </div>

          <div className="mt-5">
            {!isLoading && Object.keys(results).length === 0 && (
              <div className="rounded-xl border border-dashed border-black/15 dark:border-white/15 p-10 text-center">
                <div className="mx-auto max-w-md">
                  <p className="text-sm font-semibold text-gray-900 dark:text-white">Your generated ideas will appear here</p>
                  <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                    Select a model, set constraints/persona, then click “Generate Ideas”.
                  </p>
                </div>
              </div>
            )}

            {!isLoading && Object.keys(results).length > 0 && (
              <div className="space-y-5">
                <div className="flex flex-wrap gap-2">
                  {Object.keys(results).map((modelId) => {
                    const label = MODELS.find((m) => m.id === modelId)?.label ?? modelId;
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

    (async () => {
      try {
        setPlanLoading(true);
        const jwt = await getToken();
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
        if (!cancelled) setIsPremium(false);
      } finally {
        if (!cancelled) setPlanLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [getToken]);

  return (
    <main className="min-h-screen bg-[radial-gradient(1200px_circle_at_20%_-10%,rgba(59,130,246,0.25),transparent_55%),radial-gradient(900px_circle_at_90%_20%,rgba(99,102,241,0.22),transparent_55%),linear-gradient(to_bottom,#050814,#040615)]">
      <div className="sticky top-0 z-40 border-b border-white/10 bg-black/20 backdrop-blur">
        <div className="mx-auto max-w-7xl px-4 py-4 flex items-center justify-between">
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

      <div className="mx-auto max-w-7xl px-4 py-10">
        <div className="mb-8">
          <h1 className="text-3xl sm:text-4xl font-semibold text-white tracking-tight">Business Idea Generator</h1>
          <p className="mt-2 text-sm sm:text-base text-white/70">
            Generate, compare, and refine business concepts across multiple AI models
            —then export a professionally formatted report ready to share with stakeholders.
          </p>
        </div>

        <Protect fallback={<IdeaGenerator isPremium={false} planLoaded={true} />}>
          <IdeaGenerator isPremium={isPremium} planLoaded={!planLoading} initialUsage={initialUsage} />
        </Protect>
      </div>
    </main>
  );
}
