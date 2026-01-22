"use client"

import { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { useAuth, UserButton, Protect } from '@clerk/nextjs';

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
  
    // --- NEW: higher-signal, agent-native verticals ---
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
    "SMB Back Office (Accounting, Payroll, Invoicing)"
  ];

const CONSTRAINTS = [
    "None",
    "Low Startup Cost (<$5k)",
    "No-Code Solution",
    "Enterprise Scale",
    "B2B SaaS",
    "B2C Mobile App",
    "Bootstrapped Friendly",
  
    // --- NEW: design-enforcing constraints ---
    "Human-in-the-Loop Required",
    "Regulated Environment (HIPAA, SOC2, GDPR)",
    "Data Cannot Leave Customer Environment",
    "API-First (No UI MVP)",
    "Single-Person Buyer (Founder / Manager)",
    "Long Sales Cycle (6+ months)",
    "Usage-Based Pricing Required",
    "Offline / Low-Connectivity Environment",
    "International / Multi-Language Users",
    "Legacy Systems Only (Email, Excel, PDFs)"
  ];

const PERSONAS = [
    {
      id: "Neutral",
      label: "Neutral / Professional (Execution Focused)"
    },
    {
      id: "Critical VC",
      label: "Critical VC Investor (Risk, Moat, Distribution)"
    },
    {
      id: "Optimistic Visionary",
      label: "Optimistic Visionary (Platform & Expansion)"
    },
  
    // --- NEW personas that meaningfully change outputs ---
    {
      id: "Operator",
      label: "Experienced Operator (Workflow & ROI Focused)"
    },
    {
      id: "Compliance Officer",
      label: "Compliance / Risk Officer (Safety & Controls)"
    },
    {
      id: "Solo Founder",
      label: "Solo Founder (Speed, Simplicity, Cashflow)"
    },
    {
      id: "Enterprise Buyer",
      label: "Enterprise Buyer (Security, Procurement, Governance)"
    },
    {
      id: "Growth Marketer",
      label: "Growth Marketer (Acquisition & Retention)"
    }
  ];



const MODELS = [{ id: "gpt-5-nano", label: "OpenAI" }, { id: "gemini-3-pro-preview", label: "Gemini" }, { id: "deepseek-chat", label: "DeepSeek" }, { id: "grok-4-1-fast-reasoning", label: "Grok" }];

type IdeaResults = { [key: string]: string; };

function IdeaGenerator({ isPremium = false }: { isPremium?: boolean }) {
    const { getToken } = useAuth();
    
    const [results, setResults] = useState<IdeaResults>({});
    const [isLoading, setIsLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<string>('');
    const [industry, setIndustry] = useState(INDUSTRIES[0]);
    const [constraints, setConstraints] = useState<string[]>([CONSTRAINTS[0]]);
    const [tone, setTone] = useState(PERSONAS[0].id);
    const [selectedModels, setSelectedModels] = useState<string[]>([MODELS[0].id]);
    const [email, setEmail] = useState('');
    const [sendingEmail, setSendingEmail] = useState(false);
    const [emailStatus, setEmailStatus] = useState('');
    const [recoLoading, setRecoLoading] = useState(false);
    const [recoHtml, setRecoHtml] = useState<string>("");


    useEffect(() => {
        if (!isPremium) {
          // keep only free-allowed constraints (first 3)
          const allowed = new Set(CONSTRAINTS.slice(0, 3));
          const filtered = constraints.filter(c => allowed.has(c));
      
          // if user has none after filtering, default to first option
          if (filtered.length === 0) {
            setConstraints([CONSTRAINTS[0]]);
          } else if (filtered.length !== constraints.length) {
            setConstraints(filtered);
          }
      
          // enforce free persona
          const toneIdx = PERSONAS.findIndex(p => p.id === tone);
          if (toneIdx > 0) setTone(PERSONAS[0].id);
      
          // only first model
          setSelectedModels(prev => prev.length > 0 ? [prev[0]] : prev);
        }
      }, [isPremium, constraints, tone, setConstraints, setTone, setSelectedModels]);
      

    const handleModelSelection = (modelId: string, isChecked: boolean) => {
        setSelectedModels(prev => isChecked ? [...prev, modelId] : prev.filter(id => id !== modelId));
    };
    
    const generateIdeas = async () => {
        if (selectedModels.length === 0) return alert("Please select at least one AI model.");
        setIsLoading(true);
        setResults({});
        setActiveTab(selectedModels[0]);
        const jwt = await getToken();
        try {
            const response = await fetch('/api', {
                method: "POST",
                headers: { Authorization: `Bearer ${jwt}`, "Content-Type": "application/json" },
                body: JSON.stringify({ industry, constraints, tone, models: selectedModels }),
            });
            if (!response.ok) throw new Error(`API Error: ${response.statusText}`);
            const data = await response.json();
            setResults(data);
        } catch (e: any) {
            alert(`An error occurred: ${e.message}`);
        } finally {
            setIsLoading(false);
        }
    };

    const recommendCombination = async () => {
      if (!isPremium) return;
    
      setRecoLoading(true);
      setRecoHtml("");
    
      const jwt = await getToken();
    
      try {
        const res = await fetch("/api/recommend-combination", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${jwt}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            industry,
            constraints: CONSTRAINTS,
            personas: PERSONAS,
          }),
        });
    
        const data = await res.json();
        if (!res.ok) throw new Error(data?.detail || res.statusText);
    
        // IMPORTANT: plural field name + array
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
    
      
    
    const getReportPayload = () => ({ industry, constraints, tone, models: selectedModels, results });

    const downloadPDF = async () => {
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
    
      // sanitize industry for filenames
      const safeIndustry = String(industry || "industry")
        .trim()
        .replace(/\s+/g, "_")
        .replace(/[^a-zA-Z0-9_-]/g, "");
    
      // timestamp (no time)
      const d = new Date();
      const yyyy = d.getFullYear();
      const mm = String(d.getMonth() + 1).padStart(2, "0");
      const dd = String(d.getDate()).padStart(2, "0");
      const hh = String(d.getHours()).padStart(2, "0");
      const mi = String(d.getMinutes()).padStart(2, "0");
      const ss = String(d.getSeconds()).padStart(2, "0");
      const stamp = `${yyyy}${mm}${dd}_${hh}${mi}${ss}`;
    
      const filename = `IdeaGen_${safeIndustry}_${stamp}.pdf`;
    
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      a.remove();
    
      window.URL.revokeObjectURL(url);
    };
    

    const sendEmail = async () => {
        if (!email) return;
        setSendingEmail(true);
        setEmailStatus('');
        const jwt = await getToken();
        const response = await fetch('/api/email', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwt}` },
            body: JSON.stringify({ ...getReportPayload(), to_email: email }),
        });
        setEmailStatus(response.ok ? 'Email sent successfully!' : 'Failed to send email.');
        setSendingEmail(false);
    };

    return (
        <div className="max-w-[100rem] mx-auto grid grid-cols-1 md:grid-cols-12 gap-8">
            <div className="md:col-span-4 bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-6 h-fit">
                <div className="space-y-6">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">Configuration</h2>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Target Industry</label>
                        <select value={industry} onChange={(e) => setIndustry(e.target.value)} className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl">
                            {INDUSTRIES.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                        </select>
                    </div>
                    <div className="relative">
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Constraints
                        </label>

                        {/* Free users: single select */}
                        {!isPremium ? (
                            <select
                            value={constraints[0] ?? CONSTRAINTS[0]}
                            onChange={(e) => setConstraints([e.target.value])}
                            className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl"
                            >
                            {CONSTRAINTS.map((c, i) => (
                                <option key={c} value={c} disabled={i >= 3}>
                                {c}{i >= 3 ? " (Premium)" : ""}
                                </option>
                            ))}
                            </select>
                        ) : (
                            <ConstraintMultiSelectDropdown
                            options={CONSTRAINTS}
                            value={constraints}
                            onChange={setConstraints}
                            maxSelected={3} // optional cap
                            />
                        )}
                    </div>



                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">AI Persona</label>
                        <select value={tone} onChange={(e) => setTone(e.target.value)} className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl">
                            {PERSONAS.map((p, i) => <option key={p.id} value={p.id} disabled={!isPremium && i > 0}>{p.label}{!isPremium && i > 0 ? " (Premium)" : ""}</option>)}
                        </select>
                    </div>
                    <div>
                        <button
                        onClick={recommendCombination}
                        disabled={!isPremium || recoLoading}
                        className={`w-full py-3 rounded-xl font-semibold border ${
                            !isPremium
                            ? "opacity-50 cursor-not-allowed"
                            : recoLoading
                            ? "opacity-70 cursor-wait"
                            : "hover:bg-gray-50 dark:hover:bg-gray-700"
                        }`}
                        >
                        {recoLoading ? "Recommending..." : "Recommend Combination (Premium)"}
                        </button>

                        {recoHtml && (
                          <div className="mt-3 p-4 rounded-xl border bg-gray-50 dark:bg-gray-700">
                            <div
                              className="max-h-70 overflow-y-auto pr-2 text-sm leading-relaxed"
                              style={{ scrollbarGutter: "stable" as any }}
                              dangerouslySetInnerHTML={{ __html: recoHtml }}
                            />
                            <style jsx>{`
                              :global([data-section="recommendation_reason"] ul) { margin: 0.5rem 0 0.25rem 1rem; }
                              :global([data-section="recommendation_reason"] li) { margin: 0.35rem 0; }
                              :global([data-section="recommendation_reason"] h3) { margin: 0 0 0.5rem 0; font-weight: 700; }
                            `}</style>
                          </div>
                        )}


                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">AI Models</label>
                        <div className="space-y-2">
                            {MODELS.map((model, index) => {
                                const isLocked = !isPremium && index > 0;
                                return (
                                    <label key={model.id} className={`flex items-center p-3 rounded-xl border ${isLocked ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700'}`}>
                                        <input type="checkbox" value={model.id} checked={selectedModels.includes(model.id)} onChange={(e) => !isLocked && handleModelSelection(model.id, e.target.checked)} disabled={isLocked} className="w-4 h-4 text-blue-600 rounded"/>
                                        <span className="ml-3 text-sm font-medium">{model.label}{isLocked && " (Premium)"}</span>
                                    </label>
                                );
                            })}
                        </div>
                    </div>

                    <button onClick={generateIdeas} disabled={isLoading} className={`w-full py-3 rounded-xl text-white font-semibold ${isLoading ? 'bg-gray-400' : 'bg-blue-600 hover:bg-blue-700'}`}>
                        {isLoading ? 'Generating...' : 'Generate Ideas'}
                    </button>
                    {!isLoading && Object.keys(results).length > 0 && (
                        <div className="pt-6 mt-6 border-t space-y-4">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Export Report</h3>
                            {isPremium ? (
                                <div className="space-y-4">
                                    <button onClick={downloadPDF} className="w-full py-3 border rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">Download PDF</button>
                                    <input type="email" placeholder="Enter email" value={email} onChange={(e) => setEmail(e.target.value)} className="w-full p-3 border rounded-lg"/>
                                    <button onClick={sendEmail} disabled={sendingEmail || !email} className="w-full py-3 rounded-lg text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400">Send Email</button>
                                    {emailStatus && <p className="text-xs text-center">{emailStatus}</p>}
                                </div>
                            ) : <p className="text-sm text-center text-gray-500">Export is a premium feature.</p>}
                        </div>
                    )}
                </div>
            </div>
            <div className="md:col-span-8">
                <div className="bg-white dark:bg-gray-800 rounded-2xl shadow-xl p-8 min-h-[600px]">
                    {isLoading && <div className="text-center">Loading...</div>}
                    {!isLoading && Object.keys(results).length === 0 && <div className="text-center text-gray-500">Your generated ideas will appear here.</div>}
                    {!isLoading && Object.keys(results).length > 0 && (
                        <div>
                            <div className="border-b border-gray-200 dark:border-gray-700">
                                <nav className="-mb-px flex space-x-6">
                                    {selectedModels.map(modelId => (
                                        <button key={modelId} onClick={() => setActiveTab(modelId)} className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm ${activeTab === modelId ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>{MODELS.find(m=>m.id===modelId)?.label}</button>
                                    ))}
                                </nav>
                            </div>
                            <div className="pt-6">
                                {Object.entries(results).map(([modelId, htmlContent]) => (
                                    <div key={modelId} className={activeTab === modelId ? 'block' : 'hidden'}>
                                        <div className="prose dark:prose-invert max-w-none" dangerouslySetInnerHTML={{ __html: htmlContent }} />
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
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
  }: {
    options: string[];
    value: string[];
    onChange: (next: string[]) => void;
    maxSelected?: number;
  }) {
    const [open, setOpen] = useState(false);
    const ref = useRef<HTMLDivElement | null>(null);
  
    // Close when clicking outside
    useEffect(() => {
      const onDocMouseDown = (e: MouseEvent) => {
        if (!ref.current) return;
        if (!ref.current.contains(e.target as Node)) setOpen(false);
      };
      document.addEventListener("mousedown", onDocMouseDown);
      return () => document.removeEventListener("mousedown", onDocMouseDown);
    }, []);
  
    const toggle = (opt: string) => {
      const exists = value.includes(opt);
      if (exists) {
        const next = value.filter((v) => v !== opt);
        onChange(next.length ? next : [options[0]]);
        return;
      }
      if (value.length >= maxSelected) return;
      onChange([...value, opt]);
    };
  
    const clear = () => onChange([options[0]]);
  
    const summary = value?.length ? value.join(", ") : "None";
    const buttonLabel =
      value.length === 0
        ? "Select constraints…"
        : value.length === 1
        ? value[0]
        : `${value.length} selected`;
  
    return (
      <div className="relative" ref={ref}>
        {/* Button looks like a dropdown */}
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl flex items-center justify-between"
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <span className={`text-sm ${value.length ? "text-gray-900 dark:text-gray-100" : "text-gray-500"}`}>
            {buttonLabel}
          </span>
          <span className="text-gray-500 dark:text-gray-300 text-sm">▾</span>
        </button>
  
        {/* Dropdown panel */}
        {open && (
          <div className="absolute z-50 mt-2 w-full rounded-xl border bg-white dark:bg-gray-800 shadow-lg">
            <div className="p-2 max-h-64 overflow-auto">
              {options.map((opt) => {
                const checked = value.includes(opt);
                const disabled = !checked && value.length >= maxSelected;
  
                return (
                  <label
                    key={opt}
                    className={`flex items-center gap-2 px-2 py-2 rounded-lg ${
                      disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => {
                        if (!disabled) toggle(opt);
                      }}
                    />
                    <span className="text-sm text-gray-900 dark:text-gray-100">{opt}</span>
                  </label>
                );
              })}
            </div>
  
            <div className="flex items-center justify-between gap-2 p-2 border-t dark:border-gray-700">
              <div className="text-xs text-gray-500 dark:text-gray-300">
                Max {maxSelected} • Selected: {summary}
              </div>
              <button
                type="button"
                onClick={clear}
                className="text-xs font-semibold px-2 py-1 rounded-lg border hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Reset
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }
  

export default function Product() {
    return (
        <main className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 dark:from-gray-900 dark:to-gray-800">
            <div className="container mx-auto px-4 py-12">
                <nav className="flex justify-between items-center mb-12">
                    <Link href="/" className="text-2xl font-bold text-gray-800 dark:text-gray-200">IdeaGen</Link>
                    <UserButton afterSignOutUrl="/" />
                </nav>
                <header className="text-center mb-12">
                    <h1 className="text-5xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent mb-4">Business Idea Generator</h1>
                    <p className="text-lg text-gray-600 dark:text-gray-400">Compare ideas from multiple AI models to find the perfect one.</p>
                </header>
                <Protect fallback={<IdeaGenerator isPremium={false} />}>
                    <IdeaGenerator isPremium={true} />
                </Protect>
            </div>
        </main>
    );
}