"use client"

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth, UserButton, Protect } from '@clerk/nextjs';

const INDUSTRIES = ["FinTech", "HealthTech", "EdTech", "AgriTech", "E-commerce", "Real Estate", "Cybersecurity", "LegalTech", "MarTech", "CleanTech", "Gaming", "Logistics", "Travel & Tourism", "HR Tech", "PropTech"];
const CONSTRAINTS = ["None", "Low Startup Cost (<$5k)", "No-Code Solution", "Enterprise Scale", "B2B SaaS", "B2C Mobile App", "Bootstrapped Friendly"];
const PERSONAS = [{ id: "Neutral", label: "Neutral / Professional" }, { id: "Critical VC", label: "Critical VC Investor (Risk Focused)" }, { id: "Optimistic Visionary", label: "Optimistic Visionary (Growth Focused)" }];
const MODELS = [{ id: "gpt-5-nano", label: "OpenAI" }, { id: "gemini-3-pro-preview", label: "Gemini" }, { id: "deepseek-chat", label: "DeepSeek" }, { id: "grok-4-1-fast-reasoning", label: "Grok" }];

type IdeaResults = { [key: string]: string; };

function IdeaGenerator({ isPremium = false }: { isPremium?: boolean }) {
    const { getToken } = useAuth();
    
    const [results, setResults] = useState<IdeaResults>({});
    const [isLoading, setIsLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<string>('');
    const [industry, setIndustry] = useState(INDUSTRIES[0]);
    const [constraint, setConstraint] = useState(CONSTRAINTS[0]);
    const [tone, setTone] = useState(PERSONAS[0].id);
    const [selectedModels, setSelectedModels] = useState<string[]>([MODELS[0].id]);
    const [email, setEmail] = useState('');
    const [sendingEmail, setSendingEmail] = useState(false);
    const [emailStatus, setEmailStatus] = useState('');

    useEffect(() => {
        if (!isPremium) {
            if (CONSTRAINTS.indexOf(constraint) >= 3) setConstraint(CONSTRAINTS[0]);
            if (PERSONAS.findIndex(p => p.id === tone) > 0) setTone(PERSONAS[0].id);
            setSelectedModels(prev => prev.filter((_, i) => i === 0));
        }
    }, [isPremium, constraint, tone]);

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
                body: JSON.stringify({ industry, constraint, tone, models: selectedModels }),
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
    
    const getReportPayload = () => ({ industry, constraint, tone, models: selectedModels, results });

    const downloadPDF = async () => {
        const response = await fetch('/api/download-pdf', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(getReportPayload()),
        });
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'business-idea-report.pdf';
            a.click();
            a.remove();
        } else {
            alert('Failed to download PDF.');
        }
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
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Constraints</label>
                        <select value={constraint} onChange={(e) => setConstraint(e.target.value)} className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl">
                            {CONSTRAINTS.map((c, i) => <option key={c} value={c} disabled={!isPremium && i >= 3}>{c}{!isPremium && i >= 3 ? " (Premium)" : ""}</option>)}
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">AI Persona</label>
                        <select value={tone} onChange={(e) => setTone(e.target.value)} className="w-full p-3 bg-gray-50 dark:bg-gray-700 border rounded-xl">
                            {PERSONAS.map((p, i) => <option key={p.id} value={p.id} disabled={!isPremium && i > 0}>{p.label}{!isPremium && i > 0 ? " (Premium)" : ""}</option>)}
                        </select>
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