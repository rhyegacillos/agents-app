"use client"

import { useState, FormEvent, ChangeEvent, useEffect, useRef, useMemo, useCallback, type ReactNode } from 'react';
import { useAuth, useClerk } from '@clerk/nextjs';
import DatePicker from 'react-datepicker';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import Link from 'next/link';
import { Protect, PricingTable, UserButton } from '@clerk/nextjs';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import ThemeToggle from '../components/ThemeToggle';

const GENERAL_CHIPS = [
    'How do I create a consultation note?',
    'What fields should I fill first?',
    'What file formats can I upload?',
    'How do Patient History timeline and date range work?',
];

function getClinicalChips(patientName: string): string[] {
    const name = (patientName || 'this patient').trim();
    return [
        `Summarize the latest visit for ${name}`,
        `What changed since the previous visit for ${name}?`,
        `List current medications and doses for ${name}`,
        `Any drug interaction concerns for ${name}?`,
        `Draft a referral letter for ${name}`,
        `Create patient-friendly follow-up instructions for ${name}`,
    ];
}

const SUMMARY_JOB_STORAGE_KEY = 'medinotes_summary_job_id';
const SUMMARY_OUTPUT_STORAGE_KEY = 'medinotes_summary_output';
const SUMMARY_ACTIONS_STORAGE_KEY = 'medinotes_summary_actions';
const SUMMARY_EVIDENCE_STORAGE_KEY = 'medinotes_summary_evidence';

const URL_REGEX = /\b(?:https?:\/\/|www\.)[^\s<>()]+/gi;

function sanitizeMarkdownLinks(text: string): string {
    if (!text) return '';
    // Remove stray backticks inside markdown link URLs: ](https://...`)
    return text.replace(/\]\(([^)\s]+?)`+\)/g, ']($1)');
}

function linkifyText(text: string): string {
    return text.replace(URL_REGEX, (match) => {
        let url = match;
        let trailing = '';
        while (/[),.;!?`]+$/.test(url)) {
            trailing = url.slice(-1) + trailing;
            url = url.slice(0, -1);
        }
        const href = url.startsWith('http') ? url : `https://${url}`;
        return `[${url}](${href})${trailing}`;
    });
}

function stripMarkdownCodeFences(text: string): string {
    if (!text) return '';
    return text.replace(/```[a-zA-Z0-9_-]*\n([\s\S]*?)```/g, '$1');
}

function normalizeChatMarkdown(text: string): string {
    const cleaned = sanitizeMarkdownLinks(text);
    const withoutFences = stripMarkdownCodeFences(cleaned);
    return linkifyText(withoutFences);
}

function HelpPill({ label, tooltipId, tooltipContent, align = 'right' }: { label: string; tooltipId: string; tooltipContent: ReactNode; align?: 'right' | 'left'; }) {
    const [open, setOpen] = useState(false);
    const alignment = align === 'left' ? 'left-0' : 'right-0';
    return (
        <div className="relative">
            <button
                type="button"
                onMouseEnter={() => setOpen(true)}
                onMouseLeave={() => setOpen(false)}
                onFocus={() => setOpen(true)}
                onBlur={() => setOpen(false)}
                className="inline-flex min-h-10 items-center gap-1 rounded-full border border-emerald-200 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 shadow-sm transition hover:border-emerald-400 hover:text-emerald-800 dark:border-emerald-800 dark:bg-slate-900 dark:text-emerald-200 dark:hover:border-emerald-500"
                aria-describedby={tooltipId}
            >
                {label}
            </button>
            {open && (
                <div
                    id={tooltipId}
                    role="tooltip"
                    className={`absolute ${alignment} z-30 mt-2 w-72 max-w-xs rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700 shadow-lg dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200`}
                >
                    {tooltipContent}
                </div>
            )}
        </div>
    );
}

function renderHistoryHighlighted(text: string) {
    const raw = text || '';
    const trimmed = raw.trim();
    const isHistory = /^history:/i.test(trimmed);
    if (!isHistory) return raw;
    const rest = trimmed.replace(/^history:\s*/i, '');
    return (
        <span className="inline-block rounded-md bg-emerald-100/80 px-2 py-1 text-sm font-medium text-emerald-900 dark:bg-emerald-800/70 dark:text-emerald-100">
            History: {rest}
        </span>
    );
}

type TokenGetter = (opts?: { skipCache?: boolean; template?: string }) => Promise<string | null>;

class AuthError extends Error {
    status: number;

    constructor(status: number) {
        super(`Auth error ${status}`);
        this.status = status;
    }
}

const CLERK_JWT_TEMPLATE = process.env.NEXT_PUBLIC_CLERK_JWT_TEMPLATE || '';

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

async function getFreshToken(getToken: TokenGetter): Promise<string | null> {
    try {
        return await getToken(tokenOptions(true));
    } catch {
        return await getToken(tokenOptions());
    }
}

const AUTH_FAILURE_WINDOW_MS = 30000;
const AUTH_FAILURE_THRESHOLD = 2;
const AUTH_RETRY_COUNT = 3;

const noopAuthFailure = async () => {};

async function fetchWithAuthRetry(
    getToken: TokenGetter,
    input: RequestInfo,
    init: RequestInit,
    onAuthFailure: () => Promise<void>
): Promise<Response | null> {
    let token = await getToken(tokenOptions());
    if (!token) {
        await onAuthFailure();
        return null;
    }

    const doFetch = async (token: string) => {
        const headers = new Headers(init.headers || {});
        headers.set('Authorization', `Bearer ${token}`);
        return fetch(input, { ...init, headers });
    };

    let res = await doFetch(token);
    let attempts = 0;
    while ((res.status === 401 || res.status === 403) && attempts < AUTH_RETRY_COUNT) {
        attempts += 1;
        const fresh = await getFreshToken(getToken);
        if (!fresh) {
            break;
        }
        token = fresh;
        res = await doFetch(token);
    }

    if (res.status === 401 || res.status === 403) {
        await onAuthFailure();
    }

    return res;
}

// --- Chat Interface Component ---

type Message = {
    role: 'user' | 'assistant';
    content: string;
};

type ChatInterfaceProps = {
    patientName: string;
    currentSummary: string;
    onSessionExpired: () => Promise<void>;
};

// ... (existing code)

function ChatInterface({ patientName, currentSummary, onSessionExpired }: ChatInterfaceProps) {
    const { getToken } = useAuth();
    const [isOpen, setIsOpen] = useState(false);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const lastCheckedPatientRef = useRef<string>('');

    // State for patient switching
    const [chatPatientName, setChatPatientName] = useState('');
    const [showPatientList, setShowPatientList] = useState(false);
    const [patientList, setPatientList] = useState<string[]>([]);
    const [patientListLoading, setPatientListLoading] = useState(false);
    const [showQuickPrompts, setShowQuickPrompts] = useState(true);
    const quickPromptsRef = useRef<HTMLDivElement | null>(null);
    const chatAbortRef = useRef<AbortController | null>(null);

    // Sync chat's patient context from the main form
    useEffect(() => {
        // Only sync if the chat is not actively focused on another patient
        if (!showPatientList) {
            setChatPatientName(patientName);
        }
    }, [patientName]);
    
    const activeChips = useMemo(() => {
        if (chatPatientName || currentSummary) {
            return getClinicalChips(chatPatientName || patientName || 'this patient');
        }
        return GENERAL_CHIPS;
    }, [chatPatientName, currentSummary, patientName]);

    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages]);

    useEffect(() => {
        if (showQuickPrompts) {
            quickPromptsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, [showQuickPrompts]);

    // This is the primary auto-briefing trigger.
    // It runs when the chat's patient context changes.
    useEffect(() => {
        if (chatPatientName && chatPatientName !== lastCheckedPatientRef.current) {
            lastCheckedPatientRef.current = chatPatientName;
            setMessages([]); // Clear chat for new patient context
            setShowQuickPrompts(false);
            
            // Use a short timeout to allow the UI to clear before sending the new message
            setTimeout(() => {
                handleSend(`Briefly summarize the history for ${chatPatientName}`);
            }, 100);
        }
    }, [chatPatientName]);

    async function fetchPatientList() {
        if (patientListLoading) return;
        setPatientListLoading(true);
        try {
            const res = await fetchWithAuthRetry(
                getToken,
                '/api/patients?limit=50',
                {},
                noopAuthFailure
            );
            if (res?.ok) {
                const data = await res.json();
                const names = Array.isArray(data) ? data : data?.items || [];
                setPatientList(names);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setPatientListLoading(false);
        }
    }

    function handleSwitchPatientClick() {
        setShowPatientList(!showPatientList);
        if (!showPatientList) {
            fetchPatientList();
        }
    }

    function selectPatient(name: string) {
        setChatPatientName(name);
        setShowQuickPrompts(false);
        setShowPatientList(false);
    }

    async function handleSend(textOverride?: string) {
        const text = textOverride || input;
        if (!text.trim() || loading) return;
        setShowQuickPrompts(false);

        const userMsg: Message = { role: 'user', content: text };
        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        const jwt = await getFreshToken(getToken);
        if (!jwt) {
            setMessages((prev) => [...prev, { role: 'assistant', content: 'Authentication error.' }]);
            setLoading(false);
            return;
        }

        try {
            let assistantMsg = '';
            
            setMessages((prev) => [...prev, { role: 'assistant', content: '' }]);

            const runStream = async (token: string) => {
                const controller = new AbortController();
                chatAbortRef.current = controller;
                await fetchEventSource('/api/chat', {
                    method: 'POST',
                    signal: controller.signal,
                    openWhenHidden: true,
                    headers: {
                        'Content-Type': 'application/json',
                        Authorization: `Bearer ${token}`,
                    },
                    body: JSON.stringify({
                        messages: [...messages, userMsg],
                        patient_name: chatPatientName, // Use chat-specific patient name
                        current_summary: chatPatientName === patientName ? currentSummary : '', // Only send summary if patient matches form
                    }),
                    onopen: async (res) => {
                        if (res.status === 401 || res.status === 403) {
                            throw new AuthError(res.status);
                        }
                    },
                    onmessage(ev) {
                        assistantMsg += ev.data + '\n'; // Add newline as SSE collapses them
                        setMessages((prev) => {
                            const newMsgs = [...prev];
                            if (newMsgs.length > 0) {
                               newMsgs[newMsgs.length - 1] = { role: 'assistant', content: assistantMsg };
                            }
                            return newMsgs;
                        });
                    },
                    onclose() {
                        chatAbortRef.current = null;
                        if (!assistantMsg) {
                            setMessages((prev) => {
                                const newMsgs = [...prev];
                                newMsgs[newMsgs.length - 1] = { role: 'assistant', content: 'I apologize, but I received no response. Please try again.' };
                                return newMsgs;
                            });
                        }
                        setLoading(false);
                    },
                    onerror(err) {
                        chatAbortRef.current = null;
                        throw err;
                    }
                });
            };

            let attempts = 0;
            let token = jwt;
            while (attempts <= AUTH_RETRY_COUNT) {
                try {
                    await runStream(token);
                    break;
                } catch (err) {
                    if (err instanceof AuthError) {
                        attempts += 1;
                        if (attempts > AUTH_RETRY_COUNT) {
                            chatAbortRef.current?.abort();
                            await onSessionExpired();
                            setMessages((prev) => {
                                const newMsgs = [...prev];
                                if (newMsgs.length > 0) {
                                    newMsgs[newMsgs.length - 1] = {
                                        role: 'assistant',
                                        content: 'Session expired. Please retry.',
                                    };
                                }
                                return newMsgs;
                            });
                            setLoading(false);
                            break;
                        }
                        const fresh = await getFreshToken(getToken);
                        if (!fresh) {
                            continue;
                        }
                        token = fresh;
                    } else {
                        throw err;
                    }
                }
            }
        } catch (err) {
            console.error(err);
            setMessages((prev) => {
                const newMsgs = [...prev];
                newMsgs[newMsgs.length - 1] = { role: 'assistant', content: 'Sorry, I encountered an error.' };
                return newMsgs;
            });
            setLoading(false);
        }
    }

    return (
        <>
            {/* Floating Toggle Button */}
            <button
                onClick={() => setIsOpen(!isOpen)}
                className={`safe-fixed-fab fixed z-50 h-14 w-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-600/30 transition hover:scale-105 hover:bg-emerald-700 focus:outline-none focus:ring-4 focus:ring-emerald-400/30 dark:bg-emerald-500 dark:hover:bg-emerald-400 ${
                    isOpen ? 'hidden sm:flex' : 'flex'
                }`}
                aria-label="Open MediNotes Assistant"
            >
                {isOpen ? (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="h-6 w-6">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="h-6 w-6">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 12a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 01-2.555-.337A5.972 5.972 0 015.41 20.97a5.969 5.969 0 01-.474-.065 4.48 4.48 0 00.978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25z" />
                    </svg>
                )}
            </button>

            {/* Chat Panel */}
            {isOpen && (
                <div className="safe-fixed-chat-panel fixed z-50 flex h-auto flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white/95 shadow-2xl backdrop-blur sm:h-[600px] sm:w-96 dark:border-slate-700 dark:bg-slate-900/95">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-slate-100 bg-white/50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/50">
                        <div>
                            <h3 className="font-semibold text-slate-900 dark:text-slate-100">MediNotes Assistant</h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                {chatPatientName ? `Patient: ${chatPatientName}` : 'No patient selected'}
                            </p>
                        </div>
                        <div className="flex items-center gap-1">
                            <button onClick={handleSwitchPatientClick} className="min-h-10 rounded-md px-3 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-slate-800">
                                {showPatientList ? 'Go Back' : 'Patient List'}
                            </button>
                            <button
                                type="button"
                                onClick={() => setIsOpen(false)}
                                className="flex h-10 w-10 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 sm:hidden dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                                aria-label="Close MediNotes Assistant"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor" className="h-5 w-5">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>
                        </div>

                    {/* Patient Selector */}
                    {showPatientList && (
                        <div className="absolute inset-x-0 bottom-0 top-14 z-10 bg-white/80 p-4 backdrop-blur-sm dark:bg-slate-900/80">
                            <h4 className="font-semibold mb-2">Select Patient</h4>
                            {patientListLoading ? <p>Loading...</p> : (
                                <ul className="max-h-96 overflow-y-auto rounded-md border dark:border-slate-700">
                                    {patientList.map(name => (
                                        <li key={name} onClick={() => selectPatient(name)} className="cursor-pointer p-2 hover:bg-emerald-50 dark:hover:bg-slate-800 border-b dark:border-slate-700">
                                            {name}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </div>
                    )}

                    {/* Messages */}
                    <div className="relative flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50 dark:bg-slate-950/30">
                        {showQuickPrompts && (
                            <div ref={quickPromptsRef} className="mt-4 text-center">
                                {messages.length === 0 && (
                                    <p className="text-sm text-slate-500 mb-6 dark:text-slate-400">
                                        {chatPatientName 
                                            ? "I'm ready to assist with this consultation." 
                                            : "I can guide you through the app features."}
                                    </p>
                                )}
                                <div className="flex flex-col gap-2">
                                    {activeChips.map((chip) => (
                                        <button
                                            key={chip}
                                            onClick={() => {
                                                setShowQuickPrompts(false);
                                                handleSend(chip);
                                            }}
                                            className="min-h-11 rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-emerald-500 dark:hover:text-emerald-400"
                                        >
                                            {chip}
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}
                        {messages.map((msg, idx) => (
                            <div
                                key={idx}
                                className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                            >
                                <div
                                    className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
                                        msg.role === 'user'
                                            ? 'bg-emerald-600 text-white rounded-br-none'
                                            : 'bg-white text-slate-700 shadow-sm border border-slate-100 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 rounded-bl-none'
                                    }`}
                                >
                                    {msg.role === 'assistant' && msg.content === '' && loading ? (
                                        <div className="flex space-x-1 py-1">
                                            <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]"></div>
                                            <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]"></div>
                                            <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce"></div>
                                        </div>
                                    ) : (
                                        <div className="prose prose-sm max-w-none break-words dark:prose-invert prose-p:leading-relaxed prose-ul:my-1 prose-ul:list-disc prose-li:my-0 prose-a:text-emerald-600 dark:prose-a:text-emerald-400 hover:prose-a:underline prose-pre:whitespace-pre-wrap prose-pre:break-words prose-code:break-words">
                                            <ReactMarkdown 
                                                remarkPlugins={[remarkGfm, remarkBreaks]}
                                                components={{
                                                    a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                                                    code: ({ children, className, ...props }) => {
                                                        const isBlock = Boolean(className && className.trim());
                                                        return (
                                                        <code
                                                            {...props}
                                                            className={[
                                                                'font-sans break-words',
                                                                isBlock ? '' : 'rounded bg-emerald-50/70 px-1 py-0.5 dark:bg-slate-700/60',
                                                                className || '',
                                                            ].join(' ').trim()}
                                                        >
                                                            {children}
                                                        </code>
                                                        );
                                                    },
                                                    pre: ({ children, ...props }) => (
                                                        <pre
                                                            {...props}
                                                            className="font-sans whitespace-pre-wrap break-words rounded bg-emerald-50/60 p-2 dark:bg-slate-800/70"
                                                        >
                                                            {children}
                                                        </pre>
                                                    ),
                                                }}
                                            >
                                                {normalizeChatMarkdown(msg.content)}
                                            </ReactMarkdown>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                        <div ref={messagesEndRef} />
                    </div>

                    {/* Input */}
                    <div className="bg-slate-50/50 p-3 dark:bg-slate-950/30">
                        {messages.length > 0 && !showQuickPrompts && !showPatientList && (
                            <div className="mb-2 flex justify-center">
                                <div className="inline-flex rounded-2xl border border-slate-100 bg-white px-2 py-1 shadow-sm dark:border-slate-700 dark:bg-slate-800">
                                <button
                                    type="button"
                                    onClick={() => setShowQuickPrompts(true)}
                                    className="min-h-10 rounded-full px-4 py-1 text-xs font-semibold text-slate-700 transition hover:text-emerald-700 dark:text-slate-200 dark:hover:text-emerald-400"
                                >
                                    Go back to chips
                                </button>
                                </div>
                            </div>
                        )}
                        <form
                            onSubmit={(e) => {
                                e.preventDefault();
                                handleSend();
                            }}
                            className="relative"
                        >
                            <input
                                type="text"
                                value={input}
                                onChange={(e) => setInput(e.target.value)}
                                placeholder="Type a message..."
                                className="w-full rounded-full border border-slate-200 bg-slate-50 py-3 pl-4 pr-14 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                            />
                            <button
                                type="submit"
                                disabled={!input.trim() || loading}
                                className="absolute right-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full bg-emerald-600 text-white transition hover:bg-emerald-700 disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                                    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
                                </svg>
                            </button>
                        </form>
                    </div>
                </div>
            )}
        </>
    );
}

const SUMMARY_TEMPLATES = [
    { id: 'generic', label: 'Generic Summary', premium: false },
    { id: 'soap', label: 'SOAP', premium: true },
    { id: 'discharge', label: 'Discharge Summary', premium: true },
    { id: 'referral', label: 'Referral Letter', premium: true },
    { id: 'follow_up', label: 'Follow-Up Visit', premium: true },
    { id: 'surgery', label: 'Surgery Note', premium: true },
    { id: 'med_review', label: 'Medication Review', premium: true },
];

const LANGUAGE_OPTIONS = [
    'English',
    'Afrikaans',
    'Albanian',
    'Arabic',
    'Armenian',
    'Azerbaijani',
    'Basque',
    'Belarusian',
    'Bengali',
    'Bosnian',
    'Bulgarian',
    'Burmese',
    'Catalan',
    'Chinese (Simplified)',
    'Chinese (Traditional)',
    'Croatian',
    'Czech',
    'Danish',
    'Dutch',
    'Estonian',
    'Finnish',
    'French',
    'Georgian',
    'German',
    'Greek',
    'Gujarati',
    'Hausa',
    'Hebrew',
    'Hindi',
    'Hungarian',
    'Icelandic',
    'Indonesian',
    'Irish',
    'Italian',
    'Japanese',
    'Kannada',
    'Kazakh',
    'Khmer',
    'Korean',
    'Lao',
    'Latvian',
    'Lithuanian',
    'Macedonian',
    'Malay',
    'Malayalam',
    'Marathi',
    'Mongolian',
    'Nepali',
    'Norwegian',
    'Persian',
    'Polish',
    'Portuguese (Brazil)',
    'Portuguese (Portugal)',
    'Punjabi',
    'Romanian',
    'Russian',
    'Serbian',
    'Sinhala',
    'Slovak',
    'Slovenian',
    'Somali',
    'Spanish',
    'Swahili',
    'Swedish',
    'Tagalog',
    'Tamil',
    'Telugu',
    'Thai',
    'Turkish',
    'Ukrainian',
    'Urdu',
    'Uzbek',
    'Vietnamese',
    'Yoruba',
    'Zulu',
];

type HistoryPatient = {
    id: string;
    name: string;
    lastVisit?: string;
    noteCount?: number;
};

type EvidenceChunk = {
    id: string;
    source?: string;
    label?: string;
    text?: string;
    sources?: { title?: string; url?: string }[];
};

type EvidenceMap = {
    chunks?: EvidenceChunk[];
    citations?: {
        sentence?: string;
        chunk_ids?: string[];
        snippets?: Record<string, string>;
    }[];
};

type EvidenceCitation = {
    sentence?: string;
    chunk_ids?: string[];
    snippets?: Record<string, string>;
};

type HistoryEntry = {
    date: string;
    time?: string;
    type?: string;
    summary: string;
    evidence?: EvidenceMap | null;
    has_evidence?: boolean;
    doc_id?: string;
    deleted?: boolean;
    deleted_at?: number;
    encounter_id?: string;
    template_id?: string;
};

function sortHistoryEntries(items: HistoryEntry[], order: 'asc' | 'desc'): HistoryEntry[] {
    const toKey = (v: HistoryEntry) => {
        const date = v?.date ?? '';
        const time = (v as any)?.time ?? '00:00:00';
        return `${date}T${time}`;
    };
    const sorted = [...(items || [])].sort((a, b) => {
        const A = toKey(a);
        const B = toKey(b);
        return order === 'asc' ? A.localeCompare(B) : B.localeCompare(A);
    });
    return sorted;
}


type WorkspaceTab = 'current' | 'history';

type ConsultationFormProps = {
    isPremium?: boolean;
    onSessionExpired: () => Promise<void>;
};

type PatientHistoryPanelProps = {
    onAuthFailure: () => void;
};

function PatientHistoryPanel({ onAuthFailure }: PatientHistoryPanelProps) {
    const { getToken } = useAuth();
    const authFailure = useCallback(async () => {
        onAuthFailure();
    }, [onAuthFailure]);

    const [searchTerm, setSearchTerm] = useState('');
    const [dropdownOpen, setDropdownOpen] = useState(false);
    const [patientOptions, setPatientOptions] = useState<HistoryPatient[]>([]);
    const [optionsLoading, setOptionsLoading] = useState(false);
    const [optionsError, setOptionsError] = useState('');
    const [optionsOffset, setOptionsOffset] = useState(0);
    const [optionsHasMore, setOptionsHasMore] = useState(false);
    const [optionsQuery, setOptionsQuery] = useState('');
    const loadMoreCooldownRef = useRef<number>(0);
    const [selectedPatient, setSelectedPatient] = useState<HistoryPatient | null>(null);
    const [historyItems, setHistoryItems] = useState<HistoryEntry[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [historyAnimating, setHistoryAnimating] = useState(false);
    const [historyError, setHistoryError] = useState('');
    const [historyNextOffset, setHistoryNextOffset] = useState<number | null>(null);
    const [historyOrder, setHistoryOrder] = useState<'asc' | 'desc'>('desc');
    const loadMoreHistoryCooldownRef = useRef<number>(0);
    const [pendingDelete, setPendingDelete] = useState<HistoryEntry | null>(null);
    const [deleteLoading, setDeleteLoading] = useState(false);
    const [restoreLoadingId, setRestoreLoadingId] = useState<string | null>(null);
    const [selectedVisit, setSelectedVisit] = useState<HistoryEntry | null>(null);

    const selectedIsDeleted =
        !!selectedVisit &&
        (
            selectedVisit.deleted === true ||
            !!selectedVisit.deleted_at ||
            !!(selectedVisit as any).deletedAt
        );

    const todayIso = useMemo(() => new Date().toISOString().slice(0, 10), []);
    const yearStartIso = useMemo(() => `${new Date().getFullYear()}-01-01`, []);
    const [historyStartDate, setHistoryStartDate] = useState(yearStartIso);
    const [historyEndDate, setHistoryEndDate] = useState(todayIso);
    const historyStartRef = useRef<HTMLInputElement | null>(null);
    const historyEndRef = useRef<HTMLInputElement | null>(null);
    const [copyStatus, setCopyStatus] = useState('');
    const [historyQuery, setHistoryQuery] = useState('');
    const timelineRef = useRef<HTMLDivElement | null>(null);
    const [isPanning, setIsPanning] = useState(false);
    const panStartX = useRef(0);
    const panScrollLeft = useRef(0);
    const [renameOpen, setRenameOpen] = useState(false);
    const [renameValue, setRenameValue] = useState('');
    const [renameLoading, setRenameLoading] = useState(false);
    const [chatPatient, setChatPatient] = useState('');
    const [showDeleted, setShowDeleted] = useState(false);
    const handleHistorySessionExpired = useCallback(async () => {
        setHistoryError('Session expired. Please sign in again.');
    }, []);

    const filteredPatients = patientOptions; // server-side filtering handles search
    const timelineItems = useMemo(() => {
        return historyItems.map((item) => ({
            date: item.date,
            type: item.type || 'Visit',
            hasEvidence: !!item.has_evidence,
            docId: item.doc_id,
        }));
    }, [historyItems]);

    const groupedHistory = useMemo(() => {
        const map = new Map<string, HistoryEntry[]>();
        for (const raw of (historyItems as any[])) {
            const item = raw as any;
            const date = (item?.date ?? 'Unknown date') as string;
            const encounterId = (item?.encounter_id ?? item?.encounterId ?? null) as (string | null);
            const templateId = (item?.template_id ?? item?.templateId ?? 'generic') as string;
            const key = `${encounterId ?? date}-${templateId}`;
            const arr = map.get(key) ?? [];
            arr.push(raw as HistoryEntry);
            map.set(key, arr);
        }
        return Array.from(map.values());
    }, [historyItems]);

    async function loadPatients(fetchOffset?: number, fetchQuery?: string, replace?: boolean) {
        const targetOffset = typeof fetchOffset === 'number' ? fetchOffset : optionsOffset;
        const targetQuery = fetchQuery !== undefined ? fetchQuery : optionsQuery;
        if (optionsLoading) return;
        if (!replace && fetchOffset === undefined && patientOptions.length > 0 && targetQuery === optionsQuery) {
            // already have first page for this query
            return;
        }
        if (replace) {
            setPatientOptions([]);
            setOptionsOffset(0);
            setOptionsHasMore(false);
            setOptionsQuery(targetQuery);
        }
        setOptionsLoading(true);
        setOptionsError('');
        try {
            const queryParam = targetQuery ? `&q=${encodeURIComponent(targetQuery)}` : '';
            const res = await fetchWithAuthRetry(
                getToken,
                `/api/patients?limit=50&offset=${targetOffset}${queryParam}`,
                {},
                authFailure
            );
            if (!res?.ok) {
                setOptionsError('Unable to load patients.');
                return;
            }
            const data = await res.json();
            const items = Array.isArray(data) ? data : data?.items || [];
            const details = Array.isArray(data?.details) ? data.details : null;
            const nextOffset = data?.next_offset ?? targetOffset + items.length;
            const hasMore = data?.has_more ?? false;
            const mapped: HistoryPatient[] = details
                ? details.map((entry: any, idx: number) => ({
                    id: `${targetOffset + idx}-${entry?.name}`,
                    name: entry?.name,
                    lastVisit: entry?.last_visit,
                    noteCount: entry?.note_count,
                }))
                : (items || []).map((name: string, idx: number) => ({
                    id: `${targetOffset + idx}-${name}`,
                    name,
                }));
            setPatientOptions((prev) => replace ? mapped : [...prev, ...mapped]);
            setOptionsOffset(nextOffset);
            setOptionsHasMore(Boolean(hasMore));
            setOptionsQuery(targetQuery);
        } catch (err) {
            console.error(err);
            setOptionsError('Unable to load patients.');
        } finally {
            setOptionsLoading(false);
        }
    }

    async function loadHistory(patientName: string, startDate?: string, endDate?: string, keyword?: string, includeDeleted?: boolean) {
        if (!patientName) return;
        setHistoryLoading(true);
        setHistoryAnimating(true);
        setHistoryError('');
		// Avoid layout "twitch": keep the current list rendered while loading filters/actions
		// and only hard-reset when switching to a different patient.
		const isSwitchingPatient = Boolean(selectedPatient?.name && selectedPatient.name !== patientName);
		if (isSwitchingPatient) {
			setHistoryItems([]);
			setSelectedVisit(null);
		}
		setHistoryNextOffset(null);
        try {
            const dateParams = [
                startDate ? `start_date=${encodeURIComponent(startDate)}` : null,
                endDate ? `end_date=${encodeURIComponent(endDate)}` : null,
                keyword ? `q=${encodeURIComponent(keyword)}` : null,
                includeDeleted ? `include_deleted=true` : null,
            ].filter(Boolean).join('&');
            const dateQuery = dateParams ? `&${dateParams}` : '';
            const res = await fetchWithAuthRetry(
                getToken,
                `/api/patient-history?patient=${encodeURIComponent(patientName)}&limit=10${dateQuery}`,
                {},
                handleHistorySessionExpired
            );
            if (!res?.ok) {
                setHistoryError('Unable to load history.');
                return;
            }
            const data = await res.json();
            setHistoryItems(sortHistoryEntries((data?.items || []) as HistoryEntry[], historyOrder));
            setHistoryNextOffset((typeof data?.next_offset === 'number') ? data.next_offset : (data?.next_offset ?? null));
        } catch (err) {
            console.error(err);
            setHistoryError('Unable to load history.');
        } finally {
            setHistoryLoading(false);
            window.setTimeout(() => setHistoryAnimating(false), 260);
        }
    }

    async function loadMoreHistory() {
        if (!selectedPatient) return;
        if (historyLoading) return;
        if (historyNextOffset == null) return;

        const now = Date.now();
        if (now - loadMoreHistoryCooldownRef.current < 350) return;
        loadMoreHistoryCooldownRef.current = now;

        setHistoryLoading(true);
        setHistoryError('');
        try {
            const dateParams = [
                historyStartDate ? `start_date=${encodeURIComponent(historyStartDate)}` : null,
                historyEndDate ? `end_date=${encodeURIComponent(historyEndDate)}` : null,
                historyQuery ? `q=${encodeURIComponent(historyQuery)}` : null,
                showDeleted ? `include_deleted=true` : null,
                `offset=${historyNextOffset}`,
            ].filter(Boolean).join('&');
            const dateQuery = dateParams ? `&${dateParams}` : '';
            const res = await fetchWithAuthRetry(
                getToken,
                `/api/patient-history?patient=${encodeURIComponent(selectedPatient.name)}&limit=10${dateQuery}`,
                {},
                handleHistorySessionExpired
            );
            if (!res?.ok) {
                return;
            }
            const data = await res.json();
            const items = (data?.items || []) as HistoryEntry[];
            setHistoryItems((prev) => sortHistoryEntries([...prev, ...items], historyOrder));
            setHistoryNextOffset((typeof data?.next_offset === 'number') ? data.next_offset : (data?.next_offset ?? null));
        } catch (err) {
            console.error(err);
        } finally {
            setHistoryLoading(false);
        }
    }


    const handleSelect = (patient: HistoryPatient) => {
        setSelectedPatient(patient);
        setSearchTerm(''); // clear search so full list shows next time
        setDropdownOpen(false);
        loadHistory(patient.name, historyStartDate, historyEndDate, historyQuery, showDeleted);
        setSelectedVisit(null);
        setChatPatient(patient.name);
    };

    const handleLoadMorePatients = () => {
        const now = Date.now();
        if (now - loadMoreCooldownRef.current < 350) return;
        loadMoreCooldownRef.current = now;
        if (optionsLoading || !optionsHasMore) return;
        loadPatients(optionsOffset, optionsQuery, false);
    };

    async function handleRenamePatient() {
        if (!selectedPatient) return;
        const nextName = renameValue.trim();
        if (!nextName) return;
        setRenameLoading(true);
        try {
            const res = await fetchWithAuthRetry(
                getToken,
                '/api/patient/rename',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ old_name: selectedPatient.name, new_name: nextName }),
                },
                authFailure
            );
            if (!res?.ok) {
                setRenameLoading(false);
                return;
            }
            // refresh patients and history under new name
            setRenameOpen(false);
            setSelectedPatient({ ...selectedPatient, name: nextName });
            setRenameValue('');
            setPatientOptions((prev) =>
                prev.map((p) => (p.name === selectedPatient.name ? { ...p, name: nextName } : p))
            );
            await loadPatients(0, '', true);
            await loadHistory(nextName, historyStartDate, historyEndDate, historyQuery);
        } catch (err) {
            console.error(err);
        } finally {
            setRenameLoading(false);
        }
    }

    async function handleRestoreVisit(docId?: string) {
        if (!docId) return;
        try {
            setRestoreLoadingId(docId);
            const res = await fetchWithAuthRetry(
                getToken,
                '/api/patient/restore-entry',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ doc_id: docId }),
                },
                handleHistorySessionExpired
            );
            if (!res?.ok) return;

            // optimistic: clear deleted flags locally
            setHistoryItems((prev) =>
                prev.map((h) =>
                    h.doc_id === docId
                        ? ({ ...h, deleted: false, deleted_at: undefined, is_deleted: false } as HistoryEntry)
                        : h
                )
            );
            setSelectedVisit((prev) =>
                prev && prev.doc_id === docId
                    ? ({ ...prev, deleted: false, deleted_at: undefined, is_deleted: false } as HistoryEntry)
                    : prev
            );

            // keep patient list fresh (last visit / counts may change) and refresh history
            await loadPatients(0, '', true);
            if (selectedPatient) {
                await loadHistory(selectedPatient.name, historyStartDate, historyEndDate, historyQuery, showDeleted);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setRestoreLoadingId(null);
        }
    }

    function handleDeleteVisit(entry: HistoryEntry) {
        setPendingDelete(entry);
    }

    async function confirmDeleteVisit() {
        if (!pendingDelete?.doc_id) return;
        const docId = pendingDelete.doc_id;
        try {
            setDeleteLoading(true);
            const res = await fetchWithAuthRetry(
                getToken,
                '/api/patient/delete-entry',
                {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ doc_id: docId }),
                },
                handleHistorySessionExpired
            );
            if (!res?.ok) return;

            // optimistic UI:
            // - if "show deleted" is ON, keep the entry and mark it deleted so it stays visible immediately
            // - if OFF, remove it from the list (since deleted entries are hidden)
            let deletedAt: number | null = null;
            try {
                const data = await res.json().catch(() => null);
                const raw = data?.deleted_at ?? data?.deletedAt ?? null;

                if (typeof raw === 'number') {
                    deletedAt = raw;
                } else if (typeof raw === 'string') {
                    const parsed = Date.parse(raw);
                    if (!Number.isNaN(parsed)) deletedAt = parsed;
                }
            } catch {
                // ignore json parse errors
            }
            if (deletedAt === null) deletedAt = Date.now();

            setHistoryItems((prev) => {
                if (showDeleted) {
                    return prev.map((h) =>
                        h.doc_id === docId ? { ...h, deleted: true, deleted_at: deletedAt } : h
                    );
                }
                return prev.filter((h) => h.doc_id !== docId);
            });

            setSelectedVisit((prev) => {
                if (prev?.doc_id !== docId) return prev;
                if (showDeleted) return { ...prev, deleted: true, deleted_at: deletedAt };
                return null;
            });

            setPendingDelete(null);

            // refresh counts and history so server state stays in sync with filters
            await loadPatients(0, '', true);
            if (selectedPatient) {
                await loadHistory(selectedPatient.name, historyStartDate, historyEndDate, historyQuery, showDeleted);
            }
        } catch (err) {
            console.error(err);
        } finally {
            setDeleteLoading(false);
        }
    }

    const handleCopySummary = async (text: string) => {
        try {
            await navigator.clipboard.writeText(text);
            setCopyStatus('Copied');
            setTimeout(() => setCopyStatus(''), 1500);
        } catch (err) {
            console.error('Copy failed', err);
            setCopyStatus('Copy failed');
            setTimeout(() => setCopyStatus(''), 1500);
        }
    };

    useEffect(() => {
        // Fetch first page when tab opens
        loadPatients(0, '', true);
    }, []);

    useEffect(() => {
        const handle = setTimeout(() => {
            loadPatients(0, searchTerm, true);
        }, 250);
        return () => clearTimeout(handle);
    }, [searchTerm]);

    useEffect(() => {
        setHistoryItems((prev) => sortHistoryEntries(prev, historyOrder));
    }, [historyOrder]);

    useEffect(() => {
        const el = timelineRef.current;
        if (!el) return;

        const onMouseDown = (e: MouseEvent) => {
            setIsPanning(true);
            panStartX.current = e.pageX;
            panScrollLeft.current = el.scrollLeft;
            document.body.style.userSelect = 'none';
        };

        const onMouseUp = () => {
            setIsPanning(false);
            document.body.style.userSelect = '';
        };

        const onMouseMove = (e: MouseEvent) => {
            if (!isPanning) return;
            e.preventDefault();
            const walk = (e.pageX - panStartX.current);
            el.scrollLeft = panScrollLeft.current - walk;
        };

        el.addEventListener('mousedown', onMouseDown);
        window.addEventListener('mouseup', onMouseUp);
        window.addEventListener('mousemove', onMouseMove);

        return () => {
            el.removeEventListener('mousedown', onMouseDown);
            window.removeEventListener('mouseup', onMouseUp);
            window.removeEventListener('mousemove', onMouseMove);
            document.body.style.userSelect = '';
        };
    }, [timelineItems, isPanning]);

    useEffect(() => {
        const el = timelineRef.current;
        if (!el) return;
        // Reset horizontal scroll when the selected patient or timeline data changes
        // so the first pill is fully visible and not clipped from prior pan state.
        el.scrollLeft = 0;
    }, [selectedPatient?.name, timelineItems.length]);

    return (
        <>
        <div className="mx-auto max-w-5xl px-6 pb-16">
            <section className="animate-fade-in rounded-2xl border border-emerald-100/80 bg-white/90 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.55)] backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.9)]">
                <div className="border-b border-emerald-100/80 px-6 py-5 dark:border-slate-700/80">
                    <div className="flex items-start justify-between gap-3">
                        <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                                Patient History
                            </p>
                            <h2 className="font-display text-[clamp(1.35rem,4.6vw,1.75rem)] text-slate-900 dark:text-slate-100">Longitudinal View</h2>
                            <p className="text-sm text-slate-500 dark:text-slate-300">
                                Choose a patient to see their past visits.
                            </p>
                        </div>
                        <div className="mt-1">
                            <HelpPill
                                label="Help"
                                tooltipId="history-help-tip"
                                tooltipContent={
                                    <div>
                                        <p className="mb-1 font-semibold text-slate-900 dark:text-slate-100">Patient History guide</p>
                                        <p className="mb-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-2 py-1 text-[11px] font-semibold text-emerald-900 shadow-sm dark:border-emerald-700/70 dark:bg-emerald-900/50 dark:text-emerald-100">
                                            Purpose: review prior visits quickly and safely. Objective: find the right patient, narrow the date range, and open the visit you need.
                                        </p>
                                        <ul className="list-disc space-y-1 pl-4">
                                            <li>Select a patient from the dropdown (search + load more).</li>
                                            <li>Date range defaults to year-to-date; adjust From/To and apply.</li>
                                            <li>Sort newest/oldest; keyword search filters server-side.</li>
                                            <li>Timeline pills mirror the list; click to view details.</li>
                                            <li>Use “Show deleted” to reveal soft-deleted visits and restore.</li>
                                            <li>Delete prompts are reversible; restored items regain normal styling.</li>
                                            <li>If uploads+template+date match an existing visit, a modal offers reuse vs regenerate.</li>
                                            <li>“Load more” paginates visits; respects current filters and sort.</li>
                                        </ul>
                                    </div>
                                }
                            />
                        </div>
                    </div>
                </div>

                <div className="px-6 py-6 space-y-6">
                    <div className="space-y-2">
                        <label className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                            Patient
                        </label>
                        <div className="relative">
                            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 shadow-sm focus-within:border-emerald-400 focus-within:ring-2 focus-within:ring-emerald-400/30 dark:border-slate-700 dark:bg-slate-900">
                                <svg
                                    xmlns="http://www.w3.org/2000/svg"
                                    fill="none"
                                    viewBox="0 0 24 24"
                                    strokeWidth={2}
                                    stroke="currentColor"
                                    className="h-5 w-5 text-slate-400"
                                >
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35m0 0A7.5 7.5 0 1010.5 18a7.5 7.5 0 006.15-3.35z" />
                                </svg>
                                <input
                                    type="text"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                    onFocus={() => {
                                        setDropdownOpen(true);
                                        loadPatients(undefined, searchTerm || '', false);
                                    }}
                                    placeholder="Search or select a patient"
                                    className="flex-1 bg-transparent text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none dark:text-slate-100 dark:placeholder:text-slate-500"
                                />
                                <button
                                    type="button"
                                    onClick={() => setDropdownOpen((prev) => !prev)}
                                    className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:text-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-400/40 dark:text-slate-300 dark:hover:text-emerald-300"
                                    aria-label="Toggle patient list"
                                >
                                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5">
                                        <path fillRule="evenodd" d="M12 14.25a.75.75 0 01-.53-.22l-4.5-4.5a.75.75 0 111.06-1.06L12 12.44l3.97-3.97a.75.75 0 111.06 1.06l-4.5 4.5a.75.75 0 01-.53.22z" clipRule="evenodd" />
                                    </svg>
                                </button>
                            </div>
                            {dropdownOpen && (
                                <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg dark:border-slate-700 dark:bg-slate-900">
                                    <ul className="max-h-64 overflow-y-auto">
                                        {optionsLoading && (
                                            <li className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                                Loading patients...
                                            </li>
                                        )}
                                        {optionsError && !optionsLoading && (
                                            <li className="px-4 py-3 text-sm text-rose-600 dark:text-rose-400">
                                                {optionsError}
                                            </li>
                                        )}
                                        {!optionsLoading && !optionsError && filteredPatients.length === 0 && (
                                            <li className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400">
                                                No matches found
                                            </li>
                                        )}
                                        {!optionsLoading && !optionsError && filteredPatients.map((patient) => (
                                            <li
                                                key={patient.id}
                                                onMouseDown={(e) => e.preventDefault()}
                                                onClick={() => handleSelect(patient)}
                                                className="cursor-pointer border-b border-slate-100 px-4 py-3 text-sm hover:bg-emerald-50 dark:border-slate-800 dark:hover:bg-slate-800"
                                            >
                                                <div className="flex items-center justify-between">
                                                    <span className="font-semibold text-slate-800 dark:text-slate-100">
                                                        {patient.name}
                                                    </span>
                                                    <span className="text-[11px] text-slate-500 dark:text-slate-400">
                                                        {patient.lastVisit ? `Last visit ${patient.lastVisit}` : 'No date'}
                                                    </span>
                                                </div>
                                                {typeof patient.noteCount === 'number' && (
                                                    <p className="text-xs text-slate-500 dark:text-slate-400">
                                                        {patient.noteCount} prior notes
                                                    </p>
                                                )}
                                            </li>
                                        ))}
                                        {!optionsLoading && !optionsError && optionsHasMore && (
                                            <li className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-center text-sm font-semibold text-emerald-700 hover:bg-emerald-100 dark:border-slate-800 dark:bg-slate-900 dark:text-emerald-300 dark:hover:bg-slate-800">
                                                <button
                                                    type="button"
                                                    onMouseDown={(e) => e.preventDefault()}
                                                    onClick={handleLoadMorePatients}
                                                    className="w-full"
                                                >
                                                    {optionsLoading ? 'Loading...' : 'Load 50 more'}
                                                </button>
                                            </li>
                                        )}
                                    </ul>
                                </div>
                            )}
                        </div>
                        <p className="text-xs text-slate-500 dark:text-slate-400">
                            Type to filter; the dropdown searches the patient list.
                        </p>
                    </div>

                    <div className="overflow-x-hidden rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-950">
                        {selectedPatient ? (
                            <div className="space-y-4">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                            <div>
                                                <p className="text-[11px] uppercase tracking-[0.25em] text-emerald-700 dark:text-emerald-300">
                                                    Overview
                                                </p>
                                                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                                    {selectedPatient.name}
                                                </h3>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <button
                                                    type="button"
                                                    onClick={() => {
                                                        setRenameValue(selectedPatient.name);
                                                        setRenameOpen(true);
                                                    }}
                                                    className="min-h-10 rounded-full border border-slate-200 px-4 py-1 text-xs font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                                >
                                                    Rename
                                                </button>
                                                <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                    {selectedPatient.lastVisit ? `Last visit ${selectedPatient.lastVisit}` : 'Recent visit'}
                                                </span>
                                            </div>
                                        </div>

                                {timelineItems.length > 0 && (
                                    <div className="rounded-xl border border-emerald-100 bg-emerald-50/50 p-4 shadow-sm dark:border-emerald-800/60 dark:bg-emerald-950/40">
                                        <div className="flex items-center justify-between">
                                            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                                                Timeline
                                            </p>
                                            <span className="text-[11px] font-semibold text-emerald-700 dark:text-emerald-200">
                                                {timelineItems.length} visits
                                            </span>
                                        </div>
                                        <div
                                            className={`mt-3 flex items-center gap-3 overflow-x-auto px-1 pb-2 ${isPanning ? 'cursor-grabbing' : 'cursor-grab'} select-none`}
                                            ref={timelineRef}
                                            onDragStart={(e) => e.preventDefault()}
                                        >
                                        {historyItems.map((item: HistoryEntry, idx: number) => {
                                            const isSelected = (selectedVisit?.doc_id ?? '') === (item.doc_id ?? '');
                                            const isDeleted = showDeleted && Boolean(item.deleted || item.deleted_at || (item as any).is_deleted);
                                            const pillClass = isDeleted
                                                ? 'border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-700 dark:bg-rose-950/60 dark:text-rose-100 ring-1 ring-rose-100 dark:ring-rose-900/40'
                                                : isSelected
                                                    ? 'border-emerald-400 bg-emerald-600 text-white ring-2 ring-inset ring-emerald-200'
                                                    : 'border-slate-200 bg-white text-emerald-700 hover:border-emerald-200 hover:bg-emerald-50 dark:border-slate-700 dark:bg-slate-900 dark:text-emerald-200 dark:hover:border-emerald-500 dark:hover:bg-slate-800';
                                            const dateTextClass = isDeleted
                                                ? 'text-rose-700 dark:text-rose-200'
                                                : isSelected
                                                    ? 'text-white/90'
                                                    : 'text-slate-600 dark:text-slate-300';
                                            return (
                                                <div key={`${item.doc_id || item.date}-${idx}`} className="flex items-center gap-2">
                                                    <button
                                                        type="button"
                                                        onClick={() => setSelectedVisit(item)}
                                                        className={`flex h-16 min-w-[120px] flex-col items-center justify-center rounded-full border px-4 py-2 text-center shadow-sm transition ${pillClass}`}
                                                    >
                                                        <span className="text-[11px] font-semibold uppercase tracking-wide leading-tight">
                                                            {item.type || 'Visit'}
                                                        </span>
                                                        <span className={`${dateTextClass} text-xs font-semibold leading-tight`}>
                                                            {item.date || '—'}
                                                        </span>
                                                    </button>
                                                    {idx < historyItems.length - 1 && (
                                                        <div className="h-px w-10 shrink-0 bg-emerald-200 dark:bg-emerald-800/60" />
                                                    )}
                                                </div>
                                            );
                                        })}
                                        </div>
                                    </div>
                                )}

                                <div className="rounded-lg border border-slate-100 bg-slate-50/60 p-4 dark:border-slate-800 dark:bg-slate-900/60">
                                    <div className="flex flex-wrap items-center justify-between gap-2">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Patient history</p>
                                    </div>
                                    <div className="mt-2 flex w-full flex-wrap items-center gap-2 text-xs">
                                            <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm sm:w-auto dark:border-slate-700 dark:bg-slate-800/80">
                                                <span className="text-slate-500 text-xs font-semibold uppercase tracking-wide dark:text-slate-400">From</span>
                                                <div className="relative flex min-w-0 flex-1 items-center sm:w-auto sm:flex-none">
                                                    <button
                                                        type="button"
                                                        onClick={() => historyStartRef.current?.showPicker ? historyStartRef.current.showPicker() : historyStartRef.current?.focus()}
                                                        className="absolute left-1.5 flex h-8 w-8 items-center justify-center rounded-md text-emerald-600 transition hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-300 dark:hover:bg-slate-800/80"
                                                        aria-label="Open start date picker"
                                                    >
                                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V5m8 2V5m-9 8h10M5 9h14a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2v-7a2 2 0 012-2z" />
                                                        </svg>
                                                    </button>
                                                    <input
                                                        type="date"
                                                        value={historyStartDate}
                                                        onChange={(e) => setHistoryStartDate(e.target.value)}
                                                        ref={historyStartRef}
                                                        className="min-w-0 w-full max-w-full appearance-none rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm font-semibold text-slate-800 shadow-inner focus:border-emerald-400 focus:outline-none sm:w-auto dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
                                                    />
                                                </div>
                                            </div>
                                            <div className="flex w-full min-w-0 items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm sm:w-auto dark:border-slate-700 dark:bg-slate-800/80">
                                                <span className="text-slate-500 text-xs font-semibold uppercase tracking-wide dark:text-slate-400">To</span>
                                                <div className="relative flex min-w-0 flex-1 items-center sm:w-auto sm:flex-none">
                                                    <button
                                                        type="button"
                                                        onClick={() => historyEndRef.current?.showPicker ? historyEndRef.current.showPicker() : historyEndRef.current?.focus()}
                                                        className="absolute left-1.5 flex h-8 w-8 items-center justify-center rounded-md text-emerald-600 transition hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-300 dark:hover:bg-slate-800/80"
                                                        aria-label="Open end date picker"
                                                    >
                                                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                                            <path strokeLinecap="round" strokeLinejoin="round" d="M8 7V5m8 2V5m-9 8h10M5 9h14a2 2 0 012 2v7a2 2 0 01-2 2H5a2 2 0 01-2-2v-7a2 2 0 012-2z" />
                                                        </svg>
                                                    </button>
                                                    <input
                                                        type="date"
                                                        value={historyEndDate}
                                                        onChange={(e) => setHistoryEndDate(e.target.value)}
                                                        ref={historyEndRef}
                                                        className="min-w-0 w-full max-w-full appearance-none rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm font-semibold text-slate-800 shadow-inner focus:border-emerald-400 focus:outline-none sm:w-auto dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
                                                    />
                                                </div>
                                            </div>
                                            <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap">
                                                <input
                                                    type="text"
                                                    value={historyQuery}
                                                    onChange={(e) => setHistoryQuery(e.target.value)}
                                                    placeholder="Filter by keyword"
                                                    className="min-w-0 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm focus:border-emerald-400 focus:outline-none sm:w-48 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                                                />
                                                <button
                                                    type="button"
                                                    disabled={!selectedPatient}
                                                    onClick={() => selectedPatient && loadHistory(selectedPatient.name, historyStartDate, historyEndDate, historyQuery, showDeleted)}
                                                    className="w-full min-h-10 rounded-lg border border-slate-200 px-4 py-1 font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 disabled:opacity-50 sm:w-auto dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                                >
                                                    Apply
                                                </button>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => {
                                                    setHistoryStartDate('');
                                                    setHistoryEndDate('');
                                                    setHistoryQuery('');
                                                    setShowDeleted(false);
                                                    if (selectedPatient) {
                                                        loadHistory(selectedPatient.name, '', '', '', false);
                                                    }
                                                }}
                                                className="w-full min-h-10 rounded-lg border border-slate-200 px-4 py-1 font-semibold text-slate-500 transition hover:border-slate-300 hover:text-slate-700 sm:w-auto dark:border-slate-700 dark:text-slate-300 dark:hover:border-emerald-400 dark:hover:text-emerald-200"
                                            >
                                                Clear
                                            </button>
                                            <button
                                                type="button"
                                                onClick={() => setHistoryOrder((v) => (v === 'asc' ? 'desc' : 'asc'))}
                                                className="inline-flex w-full min-h-10 items-center justify-center gap-1 rounded-full border border-slate-200 px-4 py-1 font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 sm:w-auto sm:justify-start dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                                    {historyOrder === 'asc' ? (
                                                        <path d="M10 3l4 4H6l4-4zm0 14l-4-4h8l-4 4z" />
                                                    ) : (
                                                        <path d="M10 17l-4-4h8l-4 4zm0-14l4 4H6l4-4z" />
                                                    )}
                                                </svg>
                                                {historyOrder === 'asc' ? 'Oldest first' : 'Newest first'}
                                            </button>

                                            <label className="inline-flex w-full min-h-10 items-center justify-center gap-2 rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 sm:ml-auto sm:w-auto dark:border-slate-700 dark:text-slate-200">
                                                <input
                                                    type="checkbox"
                                                    checked={showDeleted}
                                                    onChange={(e) => {
                                                        const next = e.target.checked;
                                                        setShowDeleted(next);
                                                        if (!next) {
                                                            // exit detail view when leaving deleted mode to avoid stale red state
                                                            setSelectedVisit(null);
                                                        }
                                                        if (selectedPatient) {
                                                            loadHistory(selectedPatient.name, historyStartDate, historyEndDate, historyQuery, next);
                                                        }
                                                    }}
                                                    className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500 dark:border-slate-600 dark:bg-slate-800"
                                                />
                                                Show deleted
                                            </label>
                                        </div>
                                    </div>
                                    {historyLoading && <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Loading history...</p>}
                                    {historyError && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{historyError}</p>}
                                    {!historyLoading && !historyError && historyItems.length === 0 && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No stored visits yet.</p>
                                    )}

                                    {!selectedVisit && (
                                    <div className={`mt-3 max-h-[48rem] space-y-3 overflow-x-hidden overflow-y-auto pr-1 transition-opacity duration-300 ease-out ${historyAnimating ? 'opacity-60' : 'opacity-100'}`}>
                                            {groupedHistory.map((group: HistoryEntry[], groupIdx: number) => {
                                                const first = (group?.[0] ?? {}) as any;
                                                const groupDate = (first?.date ?? 'Unknown date') as string;
                                                const templateId = (first?.template_id ?? first?.templateId ?? 'generic') as string;
                                                const groupKey = `${(first?.encounter_id ?? first?.encounterId ?? groupDate) as string}-${templateId}-${groupIdx}`;

                                                return (
                                                    <div
                                                        key={groupKey}
                                                        className="rounded-2xl border border-slate-200/70 bg-white p-4 shadow-[0_10px_30px_-22px_rgba(15,23,42,0.35)] dark:border-slate-800/70 dark:bg-slate-900/80 dark:shadow-[0_10px_30px_-22px_rgba(15,23,42,0.65)]"
                                                    >
                                                        <div className="flex flex-wrap items-center justify-between gap-2 pb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                                            <span className="flex min-w-0 flex-wrap items-center gap-2">
                                                                <span className="inline-flex items-center rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200">
                                                                    Visits
                                                                </span>
                                                                <span className="text-slate-700 dark:text-slate-200">{groupDate}</span>
                                                            </span>

                                                            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-200">
                                                                Template: {templateId}
                                                            </span>
                                                        </div>

                                                        <div className="space-y-3">
                                                            {group.map((entry: HistoryEntry, idx: number) => {
                                                                const {
                                                                    doc_id: docId = '',
                                                                    type = 'Visit',
                                                                    summary = 'No summary stored.',
                                                                    date = 'Unknown date',
                                                                    deleted: deletedFlag,
                                                                    deleted_at: deletedAt,
                                                                    has_evidence: hasEvidence,
                                                                } = entry;

                                                                const time = (entry as any)?.time as (string | undefined);
                                                                const deleted = Boolean(deletedFlag || deletedAt);
                                                                const selectedDocId = ((selectedVisit as HistoryEntry | null)?.doc_id) ?? '';
                                                                const isEvidence = (type || '').toLowerCase() === 'visit_evidence';
                                                                const isSelected = selectedDocId === docId;

                                                                return (
                                                                    <div key={docId || idx} className="flex w-full flex-col gap-2 sm:flex-row sm:items-start sm:gap-3">
                                                                        <button
                                                                            type="button"
                                                                            onClick={() => setSelectedVisit(entry)}
                                                                            className="min-w-0 w-full text-left sm:flex-1"
                                                                        >
                                                                            <div
                                                                                className={`rounded-lg border p-3 shadow-sm transition hover:-translate-y-px hover:border-emerald-200 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70 dark:hover:border-emerald-400/50 ${
                                                                                    isEvidence
                                                                                        ? 'border-emerald-200 bg-emerald-50/70 dark:bg-emerald-950/40'
                                                                                        : 'border-slate-200 bg-white/90'
                                                                                } ${isSelected ? 'ring-2 ring-emerald-200 dark:ring-emerald-700/60' : ''} ${
                                                                                    deleted
                                                                                        ? '!border-rose-300 !bg-[rgba(254,242,242,0.85)] ring-1 ring-rose-100 dark:!border-rose-800 dark:!bg-[rgba(76,5,25,0.55)] dark:ring-rose-900/50'
                                                                                        : ''
                                                                                }`}
                                                                            >
                                                                                <div className="flex flex-wrap items-start justify-between gap-2">
                                                                                    <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                                                                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                                                            {type}
                                                                                        </span>

                                                                                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                                                                                            {date}{time ? ` • ${time}` : ''}
                                                                                        </span>

                                                                                        {deleted && (
                                                                                            <span className="flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-rose-700 dark:bg-rose-900/40 dark:text-rose-200">
                                                                                                <svg
                                                                                                    xmlns="http://www.w3.org/2000/svg"
                                                                                                    className="h-3 w-3"
                                                                                                    fill="none"
                                                                                                    viewBox="0 0 24 24"
                                                                                                    strokeWidth={2}
                                                                                                    stroke="currentColor"
                                                                                                >
                                                                                                    <path
                                                                                                        strokeLinecap="round"
                                                                                                        strokeLinejoin="round"
                                                                                                        d="M6 7h12M10 11v6m4-6v6M9 7l1-2h4l1 2m-7 0h8l-.7 11.2a1 1 0 01-1 .8H10.7a1 1 0 01-1-.8L9 7z"
                                                                                                    />
                                                                                                </svg>
                                                                                                Deleted
                                                                                            </span>
                                                                                        )}
                                                                                    </div>

                                                                                    <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
                                                                                        {hasEvidence && (
                                                                                            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                                                                Evidence
                                                                                            </span>
                                                                                        )}
                                                                                        <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-300">
                                                                                            View details
                                                                                        </span>
                                                                                    </div>
                                                                                </div>

                                                                                <div className={`mt-2 rounded-lg p-3 text-[clamp(0.86rem,2.3vw,0.95rem)] leading-[1.45] text-slate-700 shadow-inner whitespace-pre-line break-words [overflow-wrap:anywhere] dark:text-slate-200 line-clamp-6 transition-colors ${deleted ? "bg-[rgba(254,242,242,0.55)] dark:bg-[rgba(76,5,25,0.35)]" : "bg-slate-50/60 dark:bg-slate-900/40"}`}>
                                                                                    <ReactMarkdown
                                                                                        remarkPlugins={[remarkGfm, remarkBreaks]}
                                                                                        components={{
                                                                                            a: ({ className, ...props }) => (
                                                                                                <a
                                                                                                    {...props}
                                                                                                    className={`${className || ''} break-all`.trim()}
                                                                                                    target="_blank"
                                                                                                    rel="noopener noreferrer"
                                                                                                />
                                                                                            ),
                                                                                            p: ({ children, ...props }) => (
                                                                                                <p {...props} className="mb-2 break-words [overflow-wrap:anywhere] last:mb-0">
                                                                                                    {children}
                                                                                                </p>
                                                                                            ),
                                                                                            li: ({ children, ...props }) => (
                                                                                                <li {...props} className="break-words [overflow-wrap:anywhere]">
                                                                                                    {children}
                                                                                                </li>
                                                                                            ),
                                                                                        }}
                                                                                    >
                                                                                        {normalizeChatMarkdown(summary)}
                                                                                    </ReactMarkdown>
                                                                                </div>
                                                                            </div>
                                                                        </button>

                                                                        {showDeleted && deleted ? (
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => handleRestoreVisit(docId)}
                                                                                disabled={restoreLoadingId === docId}
                                                                                className="w-full rounded-full border !border-rose-300 !bg-[rgba(254,242,242,0.85)] px-3 py-2 text-xs font-semibold text-rose-700 transition hover:!bg-[rgba(254,242,242,0.95)] disabled:opacity-50 sm:mt-1 sm:w-auto sm:px-2 sm:py-1 sm:text-[11px] dark:!border-rose-800 dark:!bg-[rgba(76,5,25,0.55)] dark:text-rose-200 dark:hover:!bg-[rgba(76,5,25,0.7)]"
                                                                                aria-label="Restore visit"
                                                                            >
                                                                                {restoreLoadingId === docId ? 'Restoring...' : 'Restore'}
                                                                            </button>
                                                                        ) : (
                                                                            <button
                                                                                type="button"
                                                                                onClick={() => handleDeleteVisit(entry)}
                                                                                className="w-full rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 transition hover:border-rose-300 hover:text-rose-600 sm:mt-1 sm:w-auto sm:px-2 sm:py-1 sm:text-[11px] dark:border-slate-700 dark:text-slate-300 dark:hover:border-rose-500 dark:hover:text-rose-300"
                                                                                aria-label="Delete visit"
                                                                            >
                                                                                Delete
                                                                            </button>
                                                                        )}
                                                                    </div>
                                                                );
                                                            })}
                                                        </div>
                                                    </div>
                                                );
                                            })}
{historyNextOffset != null && (
                                            <div className="mt-3 flex justify-center">
                                                <button
                                                    type="button"
                                                    onClick={loadMoreHistory}
                                                    disabled={historyLoading}
                                                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:border-emerald-500 dark:hover:text-emerald-200"
                                                >
                                                    {historyLoading ? 'Loading...' : 'Load more'}
                                                </button>
                                            </div>
                                        )}
                                        </div>
                                    )}

                                    {selectedVisit && (
                                        <div className="mt-3 space-y-3">
                                            <div className={`rounded-lg border p-4 shadow-md ${
                                                (selectedVisit.type || '').toLowerCase() === 'visit_evidence'
                                                    ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/50'
                                                    : 'border-slate-200 bg-white/95 dark:border-slate-800 dark:bg-slate-900/85'
                                            } ${selectedIsDeleted
                                                ? '!border-rose-300 !bg-[rgba(254,242,242,0.85)] ring-1 ring-rose-100 dark:!border-rose-800 dark:!bg-[rgba(76,5,25,0.55)] dark:ring-rose-900/50'
                                                : ''}`}>
                                                <div className="flex flex-wrap items-center justify-between gap-3">
                                                    <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                            {selectedVisit.type || 'Visit'}
                                                        </span>
                                                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                                                            {selectedVisit.date || 'Unknown date'}
                                                        </span>
                                                    </div>
                                                    <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto">
                                                        <button
                                                            type="button"
                                                            onClick={() => setSelectedVisit(null)}
                                                            className="w-full rounded-full border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 sm:w-auto sm:py-1 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                                        >
                                                            Return to list
                                                        </button>
                                                        {selectedIsDeleted ? (
                                                        <button
                                                            type="button"
                                                            onClick={() => handleRestoreVisit(selectedVisit.doc_id)}
                                                            disabled={restoreLoadingId === selectedVisit.doc_id}
                                                            className="w-full rounded-full border border-emerald-200 px-3 py-2 text-xs font-semibold text-emerald-700 transition hover:border-emerald-400 hover:text-emerald-800 disabled:opacity-50 sm:w-auto sm:py-1 dark:border-emerald-700 dark:text-emerald-200 dark:hover:border-emerald-500 dark:hover:text-emerald-100"
                                                        >
                                                            {restoreLoadingId === selectedVisit.doc_id ? 'Restoring...' : 'Restore'}
                                                        </button>
                                                    ) : (
                                                        <button
                                                            type="button"
                                                            onClick={() => selectedVisit && handleDeleteVisit(selectedVisit)}
                                                            className="w-full rounded-full border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 transition hover:border-rose-400 hover:text-rose-800 sm:w-auto sm:py-1 dark:border-rose-700 dark:text-rose-300 dark:hover:border-rose-500 dark:hover:text-rose-200"
                                                        >
                                                            Delete
                                                        </button>
                                                    )}
                                                        <button
                                                            type="button"
                                                            onClick={() => selectedVisit.summary && handleCopySummary(selectedVisit.summary)}
                                                            className="w-full rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100 sm:w-auto sm:py-1 dark:border-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200 dark:hover:bg-emerald-900/70"
                                                        >
                                                            Copy summary
                                                        </button>
                                                        {copyStatus && (
                                                            <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-300">
                                                                {copyStatus}
                                                            </span>
                                                        )}
                                                    </div>
                                                </div>
                                                <div className="mt-3 rounded-lg bg-slate-50/80 p-4 text-[clamp(0.9rem,2.5vw,1rem)] leading-[1.55] text-slate-800 shadow-inner whitespace-pre-line break-words [overflow-wrap:anywhere] dark:bg-slate-900/60 dark:text-slate-200">
                                                    <ReactMarkdown
                                                        remarkPlugins={[remarkGfm, remarkBreaks]}
                                                        components={{
                                                            a: ({ className, ...props }) => (
                                                                <a
                                                                    {...props}
                                                                    className={`${className || ''} break-all`.trim()}
                                                                    target="_blank"
                                                                    rel="noopener noreferrer"
                                                                />
                                                            ),
                                                            p: ({ children, ...props }) => (
                                                                <p {...props} className="mb-3 break-words [overflow-wrap:anywhere] last:mb-0">
                                                                    {typeof children === 'string'
                                                                        ? renderHistoryHighlighted(children)
                                                                        : children}
                                                                </p>
                                                            ),
                                                            li: ({ children, ...props }) => (
                                                                <li {...props} className="mb-1 break-words [overflow-wrap:anywhere] last:mb-0">
                                                                    {typeof children === 'string'
                                                                        ? renderHistoryHighlighted(children)
                                                                        : children}
                                                                </li>
                                                            ),
                                                        }}
                                                    >
                                                        {normalizeChatMarkdown(selectedVisit.summary || 'No summary stored.')}
                                                    </ReactMarkdown>
                                                </div>
                                                {selectedVisit.evidence?.chunks && selectedVisit.evidence.chunks.length > 0 && (
                                                    <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4 shadow-sm dark:border-emerald-800 dark:bg-emerald-950/60">
                                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                                            <div>
                                                                <p className="text-[11px] uppercase tracking-[0.25em] text-emerald-700 dark:text-emerald-300">
                                                                    Evidence
                                                                </p>
                                                                <p className="text-[clamp(0.84rem,2.2vw,0.95rem)] leading-[1.45] text-slate-700 dark:text-slate-200">
                                                                    Source snippets supporting this visit
                                                                </p>
                                                            </div>
                                                            <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-emerald-700 shadow-sm dark:bg-slate-900 dark:text-emerald-200">
                                                                {selectedVisit.evidence.chunks.length} sources
                                                            </span>
                                                        </div>
                                                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                                                            {selectedVisit.evidence.chunks.map((chunk, idx) => (
                                                                <div key={chunk.id || idx} className="overflow-hidden rounded-lg border border-emerald-100 bg-white/95 p-3 shadow-[0_10px_30px_-22px_rgba(16,185,129,0.6)] dark:border-emerald-800/50 dark:bg-slate-900/80 dark:shadow-[0_10px_30px_-22px_rgba(16,185,129,0.35)]">
                                                                    <div className="flex min-w-0 flex-wrap items-start justify-between gap-2 text-xs">
                                                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200">
                                                                            {chunk.source || 'Source'}
                                                                        </span>
                                                                        {chunk.label && (
                                                                            <span className="w-full break-all text-[clamp(0.66rem,2vw,0.72rem)] font-semibold text-slate-500 sm:w-auto sm:text-right dark:text-slate-300">
                                                                                {chunk.label}
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                    {(() => {
                                                                        const raw = chunk.text || '—';
                                                                        const trimmed = raw.trim();
                                                                        const isHistory = /^history:/i.test(trimmed);
                                                                        const isUpload = /^upload:/i.test(trimmed) || /^uploaded:/i.test(trimmed);
                                                                        const rest = isHistory
                                                                            ? trimmed.replace(/^history:\s*/i, '')
                                                                            : isUpload
                                                                                ? trimmed.replace(/^upload(ed)?:\s*/i, '')
                                                                                : raw;
                                                                        const bg = isHistory
                                                                            ? 'border border-emerald-300 bg-emerald-50/80 dark:border-emerald-800 dark:bg-emerald-950/50'
                                                                            : isUpload
                                                                                ? 'border border-cyan-300 bg-cyan-50/80 dark:border-cyan-800 dark:bg-cyan-950/50'
                                                                                : 'border border-slate-100 bg-white/80 dark:border-slate-800/50 dark:bg-slate-900/70';
                                                                        return (
                                                                            <div
                                                                                className={`mt-2 rounded-lg p-3 text-[clamp(0.86rem,2.2vw,0.95rem)] leading-[1.45] text-slate-700 break-words whitespace-pre-wrap [overflow-wrap:anywhere] dark:text-slate-200 ${bg}`}
                                                                            >
                                                                                {isHistory && (
                                                                                    <span className="mr-2 inline-block rounded-md bg-emerald-600 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-white dark:bg-emerald-500">
                                                                                        History
                                                                                    </span>
                                                                                )}
                                                                                {isUpload && (
                                                                                    <span className="mr-2 inline-block rounded-md bg-cyan-600 px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-white dark:bg-cyan-500">
                                                                                        Upload
                                                                                    </span>
                                                                                )}
                                                                                <span className="align-middle break-words [overflow-wrap:anywhere]">
                                                                                    {(isHistory && `History: ${rest}`) ||
                                                                                        (isUpload && `Upload: ${rest}`) ||
                                                                                        raw}
                                                                                </span>
                                                                            </div>
                                                                        );
                                                                    })()}
                                                                    {chunk.sources && chunk.sources.length > 0 && (
                                                                        <div className="mt-3 space-y-1 text-[clamp(0.66rem,2vw,0.72rem)] text-emerald-700 dark:text-emerald-300">
                                                                            {chunk.sources.map((s, i) => (
                                                                                <a
                                                                                    key={i}
                                                                                    href={s.url || '#'}
                                                                                    target="_blank"
                                                                                    rel="noopener noreferrer"
                                                                                    className="flex items-start gap-1 break-all [overflow-wrap:anywhere] underline decoration-emerald-400 underline-offset-2 hover:text-emerald-800 dark:hover:text-emerald-100"
                                                                                >
                                                                                    <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                                                                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H19.5V12M19.5 6L10.5 15L7.5 12L4.5 15" />
                                                                                    </svg>
                                                                                    {s.title || 'Source link'}
                                                                                </a>
                                                                            ))}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}
                                                {(!selectedVisit.evidence?.chunks || selectedVisit.evidence.chunks.length === 0) && (selectedVisit.type || '').toLowerCase() === 'visit_evidence' && (
                                                    <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 text-sm text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
                                                        Evidence text is available but no structured snippets were saved for this visit. Newer visits will show linked sources here.
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="flex flex-col items-center justify-center gap-3 py-8 text-center">
                                    <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200">
                                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="h-6 w-6">
                                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.75a.75.75 0 01.75.75v3.75h3.75a.75.75 0 010 1.5H12.75v3.75a.75.75 0 01-1.5 0V12.75H7.5a.75.75 0 010-1.5h3.75V7.5a.75.75 0 01.75-.75z" />
                                        </svg>
                                    </div>
                                    <div>
                                        <h4 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Select a patient</h4>
                                        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                                            Use the dropdown above to load historical visits and evidence.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </section>
            </div>
            <ChatInterface
                patientName={chatPatient || selectedPatient?.name || ''}
                currentSummary=""
                onSessionExpired={handleHistorySessionExpired}
            />
            {renameOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4">
                    <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Rename patient</h3>
                        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                            Current: {selectedPatient?.name || '—'}
                        </p>
                        <div className="mt-3 space-y-2">
                            <label className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                New name
                            </label>
                            <input
                                type="text"
                                value={renameValue}
                                onChange={(e) => setRenameValue(e.target.value)}
                                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm focus:border-emerald-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                            />
                        </div>
                        <div className="mt-4 flex justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => setRenameOpen(false)}
                                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                disabled={renameLoading || !renameValue.trim()}
                                onClick={handleRenamePatient}
                                className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
                            >
                                {renameLoading ? 'Renaming...' : 'Rename'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

    {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4">
            <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                <div className="flex items-start justify-between gap-3">
                            <div>
                                <h3 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                                    Remove visit from history?
                                </h3>
                                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                                    This will hide the visit from the default view. You can restore it later from “Show deleted”.
                                </p>
                            </div>
                            <button
                                type="button"
                                onClick={() => setPendingDelete(null)}
                                className="rounded-lg p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                                aria-label="Close"
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                        </div>

                        <div className="mt-4 flex justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => setPendingDelete(null)}
                                disabled={deleteLoading}
                                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300 hover:text-slate-800 disabled:opacity-50 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={confirmDeleteVisit}
                                disabled={deleteLoading}
                                className="rounded-lg bg-rose-600 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-700 disabled:opacity-50 dark:bg-rose-500 dark:hover:bg-rose-400"
                            >
                                {deleteLoading ? 'Removing...' : 'Remove'}
                            </button>
                        </div>
                    </div>
                </div>
            )}

        </>
    );
}

type UploadPayload = {
    filename: string;
    file_b64: string;
    mime: string;
};

type PrescriptionEntry = {
    filename: string;
    text: string;
};

function ConsultationForm({ isPremium = true, onSessionExpired }: ConsultationFormProps) {
    const { getToken } = useAuth();

    // Form state
    const [patientName, setPatientName] = useState('');
    const [visitDate, setVisitDate] = useState<Date | null>(new Date());
    const [notes, setNotes] = useState('');
    const [templateId, setTemplateId] = useState('generic');
    const [patientEmail, setPatientEmail] = useState('');
    const [patientEmailError, setPatientEmailError] = useState(false);
    const [doctorName, setDoctorName] = useState('');
    const [doctorPhone, setDoctorPhone] = useState('');
    const [clinicName, setClinicName] = useState('');
    const [doctorEmail, setDoctorEmail] = useState('');
    const [regenPromptOpen, setRegenPromptOpen] = useState(false);
    const [regenMatch, setRegenMatch] = useState<HistoryEntry | null>(null);
    const [attachmentFiles, setAttachmentFiles] = useState<UploadPayload[]>([]);
    const [attachmentError, setAttachmentError] = useState('');
    const [parsingFile, setParsingFile] = useState(false);
    const [imageFiles, setImageFiles] = useState<UploadPayload[]>([]);
    const [imageError, setImageError] = useState('');
    const [parsingImage, setParsingImage] = useState(false);
    const [audioFiles, setAudioFiles] = useState<UploadPayload[]>([]);
    const [audioError, setAudioError] = useState('');
    const [parsingAudio, setParsingAudio] = useState(false);
    const [statusMessage, setStatusMessage] = useState('');
    const [sendingEmail, setSendingEmail] = useState(false);
    const [emailStatus, setEmailStatus] = useState('');
    const [selectedLanguage, setSelectedLanguage] = useState('English');
    const [prescriptions, setPrescriptions] = useState<PrescriptionEntry[]>([]);
    const [actions, setActions] = useState<any[]>([]);
    const [evidenceMap, setEvidenceMap] = useState<{
        chunks: EvidenceChunk[];
        citations: EvidenceCitation[];
    } | null>(null);
    const [evidenceOpen, setEvidenceOpen] = useState(false);
    const [doctorFieldErrors, setDoctorFieldErrors] = useState({
        name: false,
        phone: false,
        clinic: false,
        email: false,
    });
    const attachmentInputRef = useRef<HTMLInputElement | null>(null);
    const imageInputRef = useRef<HTMLInputElement | null>(null);
    const audioInputRef = useRef<HTMLInputElement | null>(null);

    // Streaming state
    const [output, setOutput] = useState('');
    const [loading, setLoading] = useState(false);
    const consultAbortRef = useRef<AbortController | null>(null);
    const summaryStatusActiveRef = useRef(false);
    const summaryStatusIndexRef = useRef(0);
    const summaryResumeRef = useRef(false);
    const summaryStreamingRef = useRef(false);
    const summaryStatusMessages = [
        'Generating summary...',
        'Analyzing context...',
        'Reviewing medications...',
        'Finalizing summary...',
    ];

    useEffect(() => {
        if (!loading) {
            summaryStatusActiveRef.current = false;
            return;
        }
        const interval = setInterval(() => {
            if (!summaryStatusActiveRef.current) return;
            summaryStatusIndexRef.current =
                (summaryStatusIndexRef.current + 1) % summaryStatusMessages.length;
            setStatusMessage(summaryStatusMessages[summaryStatusIndexRef.current]);
        }, 2200);
        return () => clearInterval(interval);
    }, [loading]);

    useEffect(() => {
        return () => {
            if (typeof window === 'undefined') {
                return;
            }
            localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_OUTPUT_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_ACTIONS_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_EVIDENCE_STORAGE_KEY);
        };
    }, []);

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }
        const savedOutput = localStorage.getItem(SUMMARY_OUTPUT_STORAGE_KEY);
        if (!savedOutput) {
            return;
        }
        setOutput(savedOutput);
        const savedActions = localStorage.getItem(SUMMARY_ACTIONS_STORAGE_KEY);
        if (savedActions) {
            try {
                const parsed = JSON.parse(savedActions);
                if (Array.isArray(parsed)) {
                    setActions(parsed);
                }
            } catch {
                // Ignore parse failures
            }
        }
        const savedEvidence = localStorage.getItem(SUMMARY_EVIDENCE_STORAGE_KEY);
        if (savedEvidence) {
            try {
                const parsed = JSON.parse(savedEvidence);
                if (parsed?.chunks && parsed?.citations) {
                    setEvidenceMap(parsed);
                    setEvidenceOpen(true);
                }
            } catch {
                // Ignore parse failures
            }
        }
        setLoading(false);
        setStatusMessage('');
        summaryResumeRef.current = true;
    }, []);

    const streamSummary = useCallback(async (token: string, jobId?: string) => {
        let buffer = '';
        let hadError = false;
        let finalized = false;
        const controller = new AbortController();
        consultAbortRef.current = controller;
        summaryStreamingRef.current = true;
        const url = jobId ? `/api/consultation?job_id=${encodeURIComponent(jobId)}` : '/api/consultation';
        const isResume = Boolean(jobId);
        await fetchEventSource(url, {
            signal: controller.signal,
            method: jobId ? 'GET' : 'POST',
            openWhenHidden: true,
            headers: {
                ...(jobId ? {} : { 'Content-Type': 'application/json' }),
                Authorization: `Bearer ${token}`,
            },
            body: jobId ? undefined : JSON.stringify({
                patient_name: patientName,
                date_of_visit: visitDate?.toISOString().slice(0, 10),
                notes,
                template_id: templateId,
                uploaded_notes: null,
                uploaded_filename: null,
                uploaded_file_b64: null,
                uploaded_mime: null,
                uploaded_files: attachmentFiles.length ? attachmentFiles : null,
                image_filename: null,
                image_file_b64: null,
                image_mime: null,
                image_files: imageFiles.length ? imageFiles : null,
                audio_filename: null,
                audio_file_b64: null,
                audio_mime: null,
                audio_files: audioFiles.length ? audioFiles : null,
            }),
            onopen: async (res) => {
                if (!res.ok) {
                    if (res.status === 401 || res.status === 403) {
                        throw new AuthError(res.status);
                    }
                    const contentType = res.headers.get('content-type') || '';

                    if (contentType.includes('application/json')) {
                        try {
                            const data = await res.clone().json();
                            const detail = data?.detail || JSON.stringify(data);
                            setOutput(detail || `Request failed (${res.status}). Please try again.`);
                        } catch {
                            setOutput(`Request failed (${res.status}). Please try again.`);
                        }
                    } else {
                        try {
                            const text = await res.text();
                            setOutput(text || `Request failed (${res.status}). Please try again.`);
                        } catch {
                            setOutput(`Request failed (${res.status}). Please try again.`);
                        }
                    }

                    setStatusMessage('');
                    if (isResume && res.status === 404 && typeof window !== 'undefined') {
                        localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
                    }
                    throw new Error(`HTTP ${res.status}`);
                }
                summaryStatusIndexRef.current = 0;
                summaryStatusActiveRef.current = true;
                setStatusMessage(summaryStatusMessages[0]);
            },
            onmessage(ev) {
                if (ev.event === 'job') {
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.job_id && typeof window !== 'undefined') {
                            localStorage.setItem(SUMMARY_JOB_STORAGE_KEY, data.job_id);
                        }
                    } catch {
                        // Ignore job id parse failures
                    }
                    return;
                }
                if (ev.event === 'metadata') {
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.doctor_name) {
                            const cleaned = cleanDoctorName(data.doctor_name);
                            setDoctorName((prev) => prev || cleaned);
                            setDoctorFieldErrors((prev) => ({ ...prev, name: false }));
                        }
                        if (data.doctor_phone) {
                            setDoctorPhone((prev) => prev || data.doctor_phone);
                            setDoctorFieldErrors((prev) => ({ ...prev, phone: false }));
                        }
                        if (data.clinic_name) {
                            setClinicName((prev) => prev || data.clinic_name);
                            setDoctorFieldErrors((prev) => ({ ...prev, clinic: false }));
                        }
                        if (data.doctor_email) {
                            setDoctorEmail((prev) => prev || data.doctor_email);
                            setDoctorFieldErrors((prev) => ({ ...prev, email: false }));
                        }
                        if (!patientEmail.trim() && data.patient_email) {
                            setPatientEmail(data.patient_email);
                            setPatientEmailError(!isValidEmail(data.patient_email));
                        }
                        if (Array.isArray(data.prescription_texts)) {
                            const entries = data.prescription_texts
                                .map((text: string, index: number) => ({
                                    text,
                                    filename: Array.isArray(data.prescription_filenames)
                                        ? data.prescription_filenames[index] || ''
                                        : '',
                                }))
                                .filter((entry: PrescriptionEntry) => entry.text);
                            setPrescriptions(entries);
                        } else if (data.prescription_text) {
                            setPrescriptions([
                                {
                                    text: data.prescription_text,
                                    filename: data.prescription_filename || '',
                                },
                            ]);
                        }
                        // Handle initial metadata which may or may not have the map
                        if (data.evidence_map?.chunks && data.evidence_map?.citations) {
                            setEvidenceMap(data.evidence_map);
                            setEvidenceOpen(false);
                            if (typeof window !== 'undefined') {
                                localStorage.setItem(SUMMARY_EVIDENCE_STORAGE_KEY, JSON.stringify(data.evidence_map));
                            }
                        }
                    } catch {
                        // Ignore metadata parse failures
                    }
                    return;
                }

                if (ev.event === 'evidence_update') {
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.chunks && data.citations) {
                            setEvidenceMap(data);
                            setEvidenceOpen(true); // Automatically open the evidence section when it loads
                            if (typeof window !== 'undefined') {
                                localStorage.setItem(SUMMARY_EVIDENCE_STORAGE_KEY, JSON.stringify(data));
                            }
                        }
                    } catch {
                        // Ignore evidence parse failures
                    }
                    return;
                }

                if (ev.event === 'summary') {
                    try {
                        const data = JSON.parse(ev.data);
                        if (data.summary_html) {
                            setOutput(data.summary_html);
                            finalized = true;
                            if (typeof window !== 'undefined') {
                                localStorage.setItem(SUMMARY_OUTPUT_STORAGE_KEY, data.summary_html);
                            }
                        }
                    } catch {
                        // Ignore summary parse failures
                    }
                    return;
                }

                if (ev.event === 'actions') {
                    try {
                        const data = JSON.parse(ev.data);
                        if (Array.isArray(data)) {
                            setActions(data);
                            if (typeof window !== 'undefined') {
                                localStorage.setItem(SUMMARY_ACTIONS_STORAGE_KEY, JSON.stringify(data));
                            }
                        }
                    } catch {
                        // Ignore
                    }
                    return;
                }

                if (ev.event === 'status') {
                    summaryStatusActiveRef.current = false; // Stop fake rotation
                    setStatusMessage(ev.data);
                    return;
                }

                buffer += ev.data;
            },
            onclose() {
                consultAbortRef.current = null;
                summaryStreamingRef.current = false;
                summaryStatusActiveRef.current = false;
                setLoading(false);
                setStatusMessage('');
                if (typeof window !== 'undefined') {
                    if (hadError) {
                        localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
                    }
                }
                if (!hadError && !finalized && buffer) {
                    setOutput(buffer);
                    if (typeof window !== 'undefined') {
                        localStorage.setItem(SUMMARY_OUTPUT_STORAGE_KEY, buffer);
                    }
                }
            },
            onerror(err) {
                if (err instanceof AuthError) {
                    throw err; // Re-throw to be caught by the retry loop
                }
                console.error('SSE error:', err);
                hadError = true;
                controller.abort();
                consultAbortRef.current = null;
                summaryStreamingRef.current = false;
                summaryStatusActiveRef.current = false;
                setLoading(false);
                setStatusMessage('Unable to generate summary. Please try again.');
                setOutput('Unable to generate summary. Please try again.');
                if (typeof window !== 'undefined') {
                    localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
                }
            },
        });
    }, [
        patientName,
        visitDate,
        notes,
        templateId,
        attachmentFiles,
        imageFiles,
        audioFiles,
        patientEmail,
    ]);

    function clearForm() {
        setPatientName('');
        setNotes('');
        setTemplateId('generic');
        setPatientEmail('');
        setPatientEmailError(false);
        setDoctorName('');
        setDoctorPhone('');
        setClinicName('');
        setDoctorEmail('');
        setDoctorFieldErrors({
            name: false,
            phone: false,
            clinic: false,
            email: false,
        });
        setSelectedLanguage('English');
        setStatusMessage('');
        setEmailStatus('');
        setPrescriptions([]);
        setActions([]);
        setEvidenceMap(null);
        setEvidenceOpen(false);
        setOutput('');
        setLoading(false);
        setSendingEmail(false);
        if (typeof window !== 'undefined') {
            localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_OUTPUT_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_ACTIONS_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_EVIDENCE_STORAGE_KEY);
        }
        clearAttachment();
        clearImage();
        clearAudio();
    }

    const maxFileBytes = 5 * 1024 * 1024; // 5MB limit for uploaded files
    const maxImageBytes = 10 * 1024 * 1024; // 10MB limit for prescription images
    const maxAudioBytes = 25 * 1024 * 1024; // 25MB limit for uploaded audio
    const uploadsDisabled = !isPremium;
    const attachmentCount = attachmentFiles.length;
    const imageCount = imageFiles.length;
    const audioCount = audioFiles.length;

    useEffect(() => {
        if (!isPremium && templateId !== 'generic') {
            setTemplateId('generic');
        }
    }, [isPremium, templateId]);

    function readFileAsBase64(file: File): Promise<string> {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const result = (reader.result as string) || '';
                const base64 = result.split(',')[1];
                if (!base64) {
                    reject(new Error('Unable to read file.'));
                    return;
                }
                resolve(base64);
            };
            reader.onerror = () => reject(new Error('Unable to read file.'));
            reader.readAsDataURL(file);
        });
    }

    async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
        const files = Array.from(event.target.files ?? []);
        setAttachmentError('');
        setAttachmentFiles([]);
        setParsingFile(false);

        if (!files.length) return;

        const allowedExtensions = ['txt', 'md', 'markdown', 'pdf', 'doc', 'docx'];
        const mimeFallback: Record<string, string> = {
            pdf: 'application/pdf',
            doc: 'application/msword',
            docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            txt: 'text/plain',
            md: 'text/markdown',
            markdown: 'text/markdown',
        };

        const invalidFiles: string[] = [];
        const validFiles: File[] = [];

        for (const file of files) {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (file.size > maxFileBytes) {
                invalidFiles.push(`${file.name} (max 5MB)`);
                continue;
            }
            if (extension && !allowedExtensions.includes(extension)) {
                invalidFiles.push(`${file.name} (unsupported type)`);
                continue;
            }
            validFiles.push(file);
        }

        if (!validFiles.length) {
            if (invalidFiles.length) {
                setAttachmentError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
            return;
        }

        setParsingFile(true);
        try {
            const payloads = await Promise.all(
                validFiles.map(async (file) => {
                    const extension = file.name.split('.').pop()?.toLowerCase();
                    const base64 = await readFileAsBase64(file);
                    return {
                        filename: file.name,
                        file_b64: base64,
                        mime: file.type || mimeFallback[extension || ''] || 'application/octet-stream',
                    };
                })
            );
            setAttachmentFiles(payloads);
            if (invalidFiles.length) {
                setAttachmentError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
        } catch {
            setAttachmentError('Unable to read one of the uploaded files. Please try again.');
        } finally {
            setParsingFile(false);
        }
    }

    async function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
        const files = Array.from(event.target.files ?? []);
        setImageError('');
        setImageFiles([]);
        setParsingImage(false);

        if (!files.length) return;

        const allowedExtensions = ['png', 'jpg', 'jpeg', 'webp'];
        const mimeFallback: Record<string, string> = {
            png: 'image/png',
            jpg: 'image/jpeg',
            jpeg: 'image/jpeg',
            webp: 'image/webp',
        };

        const invalidFiles: string[] = [];
        const validFiles: File[] = [];

        for (const file of files) {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (file.size > maxImageBytes) {
                invalidFiles.push(`${file.name} (max 10MB)`);
                continue;
            }
            if (extension && !allowedExtensions.includes(extension)) {
                invalidFiles.push(`${file.name} (unsupported type)`);
                continue;
            }
            validFiles.push(file);
        }

        if (!validFiles.length) {
            if (invalidFiles.length) {
                setImageError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
            return;
        }

        setParsingImage(true);
        try {
            const payloads = await Promise.all(
                validFiles.map(async (file) => {
                    const extension = file.name.split('.').pop()?.toLowerCase();
                    const base64 = await readFileAsBase64(file);
                    return {
                        filename: file.name,
                        file_b64: base64,
                        mime: file.type || mimeFallback[extension || ''] || 'image/png',
                    };
                })
            );
            setImageFiles(payloads);
            if (invalidFiles.length) {
                setImageError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
        } catch {
            setImageError('Unable to read one of the images. Please try again.');
        } finally {
            setParsingImage(false);
        }
    }

    async function handleAudioChange(event: ChangeEvent<HTMLInputElement>) {
        const files = Array.from(event.target.files ?? []);
        setAudioError('');
        setAudioFiles([]);
        setParsingAudio(false);

        if (!files.length) return;

        const allowedExtensions = ['mp3', 'm4a', 'wav', 'webm', 'ogg', 'mp4', 'aac'];
        const mimeFallback: Record<string, string> = {
            mp3: 'audio/mpeg',
            m4a: 'audio/mp4',
            wav: 'audio/wav',
            webm: 'audio/webm',
            ogg: 'audio/ogg',
            mp4: 'audio/mp4',
            aac: 'audio/aac',
        };

        const invalidFiles: string[] = [];
        const validFiles: File[] = [];

        for (const file of files) {
            const extension = file.name.split('.').pop()?.toLowerCase();
            if (file.size > maxAudioBytes) {
                invalidFiles.push(`${file.name} (max 25MB)`);
                continue;
            }
            if (extension && !allowedExtensions.includes(extension)) {
                invalidFiles.push(`${file.name} (unsupported type)`);
                continue;
            }
            validFiles.push(file);
        }

        if (!validFiles.length) {
            if (invalidFiles.length) {
                setAudioError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
            return;
        }

        setParsingAudio(true);
        try {
            const payloads = await Promise.all(
                validFiles.map(async (file) => {
                    const extension = file.name.split('.').pop()?.toLowerCase();
                    const base64 = await readFileAsBase64(file);
                    return {
                        filename: file.name,
                        file_b64: base64,
                        mime: file.type || mimeFallback[extension || ''] || 'application/octet-stream',
                    };
                })
            );
            setAudioFiles(payloads);
            if (invalidFiles.length) {
                setAudioError(`Some files were skipped: ${invalidFiles.join(', ')}.`);
            }
        } catch {
            setAudioError('Unable to read one of the audio files. Please try again.');
        } finally {
            setParsingAudio(false);
        }
    }

    function clearAttachment() {
        setAttachmentFiles([]);
        setAttachmentError('');
        setParsingFile(false);
        if (attachmentInputRef.current) {
            attachmentInputRef.current.value = '';
        }
    }

    function clearImage() {
        setImageFiles([]);
        setImageError('');
        setParsingImage(false);
        setPrescriptions([]);
        if (imageInputRef.current) {
            imageInputRef.current.value = '';
        }
    }

    function clearAudio() {
        setAudioFiles([]);
        setAudioError('');
        setParsingAudio(false);
        if (audioInputRef.current) {
            audioInputRef.current.value = '';
        }
    }

    function buildUploadSignature(files: UploadPayload[]) {
        if (!files.length) return '';
        return `${files.length}|${files
            .map((f) => `${f.filename}::${(f.file_b64 || '').length}::${f.mime || ''}`)
            .join(',')}`;
    }

    async function findRegenMatch(): Promise<HistoryEntry | null> {
        if (!patientName.trim() || !visitDate || attachmentFiles.length === 0) return null;
        const visitIso = visitDate.toISOString().slice(0, 10);
        try {
            const res = await fetchWithAuthRetry(
                getToken,
                `/api/patient-history?patient=${encodeURIComponent(patientName.trim())}&start_date=${visitIso}&end_date=${visitIso}&include_deleted=true&order=desc&limit=25`,
                {},
                onSessionExpired
            );
            if (!res?.ok) return null;
            const data = await res.json();
            const items: HistoryEntry[] = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
            const uploadSig = buildUploadSignature(attachmentFiles);
            const match = items.find((item) => {
                const deleted = item.deleted || item.deleted_at || (item as any).is_deleted;
                if (deleted) return false;
                const itemDate = item.date;
                const itemTemplate = (item as any).template_id || (item as any).templateId || 'generic';
                if (itemDate !== visitIso) return false;
                if (itemTemplate !== templateId) return false;
                const itemUploadSig =
                    (item as any).upload_signature ||
                    buildUploadSignature(((item as any).uploaded_files as UploadPayload[]) || []);
                if (itemUploadSig) {
                    return itemUploadSig === uploadSig;
                }
                // If the API doesn’t return file signatures, fall back to treating any same-date/template
                // entry as a candidate match when uploads are present—better to prompt than regenerate silently.
                return Boolean(uploadSig);
            });
            return match || null;
        } catch (err) {
            console.error('regen check failed', err);
            return null;
        }
    }

    async function runGeneration() {
        setOutput('');
        setStatusMessage('');
        setEmailStatus('');
        setPrescriptions([]);
        setActions([]);
        setEvidenceMap(null);
        setEvidenceOpen(false);
        setLoading(true);
        summaryStatusActiveRef.current = false;
        summaryResumeRef.current = false;
        if (typeof window !== 'undefined') {
            localStorage.removeItem(SUMMARY_JOB_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_OUTPUT_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_ACTIONS_STORAGE_KEY);
            localStorage.removeItem(SUMMARY_EVIDENCE_STORAGE_KEY);
        }

        const jwt = await getFreshToken(getToken);
        if (!jwt) {
            setOutput('Authentication required');
            setLoading(false);
            return;
        }

        let buffer = '';
        const hasFile = attachmentFiles.length > 0;
        const hasImage = imageFiles.length > 0;
        const hasAudio = audioFiles.length > 0;
        const isPdf =
            hasFile &&
            attachmentFiles.some(
                (file) =>
                    (file.mime && file.mime.includes('pdf')) ||
                    file.filename.toLowerCase().endsWith('.pdf')
            );

        if (hasAudio) {
            setStatusMessage('Uploading and transcribing audio... this may take a few seconds.');
        } else if (hasImage) {
            setStatusMessage('Uploading and reading prescription image... this may take a few seconds.');
        } else if (isPdf) {
            setStatusMessage('Uploading and parsing PDF... this may take a few seconds.');
        } else if (hasFile) {
            setStatusMessage('Uploading and parsing document...');
        } else {
            setStatusMessage('Generating summary...');
        }

        try {
            let attempts = 0;
            let token = jwt;
            while (attempts <= AUTH_RETRY_COUNT) {
                try {
                    await streamSummary(token);
                    break;
                } catch (err) {
                    if (err instanceof AuthError) {
                        attempts += 1;
                        if (attempts > AUTH_RETRY_COUNT) {
                            consultAbortRef.current?.abort();
                            await onSessionExpired();
                            setLoading(false);
                            setStatusMessage('');
                            setOutput('Session expired. Please relogin.');
                            break;
                        }
                        const fresh = await getFreshToken(getToken);
                        if (!fresh) {
                            continue;
                        }
                        token = fresh;
                    } else {
                        throw err;
                    }
                }
            }
        } catch (err: any) {
            console.error('Request failed:', err);
            setOutput((prev) => prev || err?.message || 'Request failed. Please try again.');
            setLoading(false);
            setStatusMessage('');
        }
    }

    async function handleSubmit(e: FormEvent) {
        e.preventDefault();
        if (!notes.trim() && !attachmentFiles.length && !audioFiles.length && !imageFiles.length) {
            setOutput('Please add consultation notes or upload a file/audio/image before generating a summary.');
            return;
        }

        // Regeneration guard: only when uploaded notes + template + date match an existing non-deleted visit.
        const maybeMatch = await findRegenMatch();
        if (maybeMatch) {
            setRegenMatch(maybeMatch);
            setRegenPromptOpen(true);
            setLoading(false);
            setStatusMessage('');
            return;
        }

        await runGeneration();
    }

    useEffect(() => {
        if (summaryResumeRef.current || loading) {
            return;
        }
        if (typeof window === 'undefined') {
            return;
        }
        const jobId = localStorage.getItem(SUMMARY_JOB_STORAGE_KEY);
        if (!jobId) {
            return;
        }
        summaryResumeRef.current = true;
        setOutput('');
        setStatusMessage('Reconnecting to summary...');
        setEmailStatus('');
        setPrescriptions([]);
        setActions([]);
        setEvidenceMap(null);
        setEvidenceOpen(false);
        setLoading(true);

        const resume = async () => {
            const jwt = await getFreshToken(getToken);
            if (!jwt) {
                setLoading(false);
                setStatusMessage('Authentication required');
                return;
            }
            let attempts = 0;
            let token = jwt;
            while (attempts <= AUTH_RETRY_COUNT) {
                try {
                    await streamSummary(token, jobId);
                    break;
                } catch (err) {
                    if (err instanceof AuthError) {
                        attempts += 1;
                        if (attempts > AUTH_RETRY_COUNT) {
                            consultAbortRef.current?.abort();
                            await onSessionExpired();
                            setLoading(false);
                            setStatusMessage('');
                            setOutput('Session expired. Please relogin.');
                            break;
                        }
                        const fresh = await getFreshToken(getToken);
                        if (!fresh) {
                            continue;
                        }
                        token = fresh;
                    } else {
                        console.error('Resume failed:', err);
                        setLoading(false);
                        setStatusMessage('');
                        break;
                    }
                }
            }
        };

        void resume();
    }, [getToken, loading, onSessionExpired, streamSummary]);

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }
        const handleFocus = () => {
            if (summaryStreamingRef.current) {
                return;
            }
            const jobId = localStorage.getItem(SUMMARY_JOB_STORAGE_KEY);
            if (!jobId) {
                return;
            }
            const existing = localStorage.getItem(SUMMARY_OUTPUT_STORAGE_KEY);
            if (existing && existing.trim()) {
                return;
            }
            const reconnect = async () => {
                const jwt = await getFreshToken(getToken);
                if (!jwt) {
                    return;
                }
                let attempts = 0;
                let token = jwt;
                while (attempts <= AUTH_RETRY_COUNT) {
                    try {
                        await streamSummary(token, jobId);
                        break;
                    } catch (err) {
                        if (err instanceof AuthError) {
                            attempts += 1;
                            if (attempts > AUTH_RETRY_COUNT) {
                                consultAbortRef.current?.abort();
                                await onSessionExpired();
                                setLoading(false);
                                setStatusMessage('');
                                setOutput('Session expired. Please relogin.');
                                break;
                            }
                            const fresh = await getFreshToken(getToken);
                            if (!fresh) {
                                continue;
                            }
                            token = fresh;
                        } else {
                            console.error('Focus reconnect failed:', err);
                            break;
                        }
                    }
                }
            };
            void reconnect();
        };

        window.addEventListener('focus', handleFocus);
        document.addEventListener('visibilitychange', handleFocus);
        return () => {
            window.removeEventListener('focus', handleFocus);
            document.removeEventListener('visibilitychange', handleFocus);
        };
    }, [getToken, loading, onSessionExpired, streamSummary]);

    function extractDraftEmailHtml(html: string) {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');
            const section = doc.querySelector('section[data-section="patient_email"]');
            if (!section) return '';
            const clone = section.cloneNode(true) as HTMLElement;
            const heading = clone.querySelector('h3');
            if (heading) heading.remove();
            return clone.innerHTML.trim();
        } catch {
            return '';
        }
    }

    function extractDraftEmailText(markdown: string) {
        const heading = '### Draft Email for Patient';
        const startIndex = markdown.indexOf(heading);
        if (startIndex === -1) return markdown.trim();
        const sectionStart = startIndex + heading.length;
        return markdown.slice(sectionStart).trim();
    }

    function stripSignatureText(text: string) {
        const lines = text.split(/\r?\n/);
        const signoffIndex = lines.findIndex((line) =>
            /^(sincerely|best regards|regards|kind regards|yours truly|thank you|thanks)[,]?\s*$/i.test(
                line.trim()
            )
        );
        if (signoffIndex === -1) return text.trim();
        return lines.slice(0, signoffIndex).join('\n').trim();
    }

    function cleanDoctorName(name: string) {
        return name
            .replace(/^\s*(?:attending|treating)?\s*(?:physician|doctor|surgeon|provider|clinician)(?:\s+name)?\s*[:\-]\s*/i, '')
            .replace(/^\s*(?:physician|doctor|provider|surgeon|clinician)\s+name\s*[:\-]\s*/i, '')
            .trim();
    }

    function formatDoctorName(name: string) {
        const trimmed = cleanDoctorName(name);
        if (!trimmed) return trimmed;
        const lower = trimmed.toLowerCase();
        if (lower.startsWith('dr ') || lower.startsWith('dr.')) return trimmed;
        return `Dr ${trimmed}`;
    }


    function escapeHtml(input: string) {
        return input
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function isValidEmail(value: string) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
    }

    function isValidPhone(value: string) {
        const digits = value.replace(/\D/g, '');
        return digits.length >= 7 && digits.length <= 15;
    }

    function wrapEmailHtml(html: string) {
        return `
<div style="background:#f6fbfb;padding:24px;font-family:'Plus Jakarta Sans',Arial,sans-serif;">
  <div style="max-width:640px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:16px;padding:24px;">
    <h1 style="margin:0 0 12px;font-size:22px;line-height:1.3;color:#0f172a;">MediNotes Consultation</h1>
    <div style="font-size:14px;line-height:1.6;color:#334155;">${html}</div>
  </div>
</div>
        `.trim();
    }

    function toParagraphHtml(text: string) {
        const escaped = escapeHtml(text);
        return `<p>${escaped.replace(/\n/g, '<br />')}</p>`;
    }

    async function handleSendEmail() {
        if (!patientEmail.trim()) {
            setPatientEmailError(true);
            setEmailStatus('Add a patient email address before sending.');
            return;
        }
        if (!isValidEmail(patientEmail)) {
            setPatientEmailError(true);
            setEmailStatus('Enter a valid patient email address.');
            return;
        }
        if (!output.trim()) {
            setEmailStatus('Generate a summary before sending the email.');
            return;
        }

        const fieldErrors = {
            name: !doctorName.trim(),
            phone: !doctorPhone.trim() || !isValidPhone(doctorPhone),
            clinic: !clinicName.trim(),
            email: !doctorEmail.trim() || !isValidEmail(doctorEmail),
        };
        setDoctorFieldErrors(fieldErrors);
        if (Object.values(fieldErrors).some(Boolean)) {
            setEmailStatus('Enter valid doctor name, phone, clinic, and email before sending.');
            return;
        }

        setSendingEmail(true);
        setEmailStatus('');

        const draftHtml = extractDraftEmailHtml(output);
        const draftText = draftHtml ? '' : extractDraftEmailText(output);
        const safeDraftHtml = draftHtml || toParagraphHtml(stripSignatureText(draftText));
        const signatureHtml = `<p>Sincerely,</p><p>${escapeHtml(formatDoctorName(doctorName))}<br />${escapeHtml(
            clinicName.trim()
        )}<br />${escapeHtml(doctorPhone.trim())}</p>`;
        const html = wrapEmailHtml(`${safeDraftHtml}${signatureHtml}`);
        const subject = `Visit Summary for ${patientName || 'Patient'}`;

        try {
            const jwt = await getFreshToken(getToken);
            if (!jwt) {
                setEmailStatus('Authentication required.');
                setSendingEmail(false);
                return;
            }

            const response = await fetchWithAuthRetry(
                getToken,
                '/api/send-email',
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        to: patientEmail.trim(),
                        subject,
                        html,
                        reply_to: doctorEmail.trim(),
                        clinic_name: clinicName.trim(),
                        language: selectedLanguage,
                    }),
                },
                onSessionExpired
            );

            if (!response?.ok) {
                if (!response) {
                    setEmailStatus('Authentication required.');
                    setSendingEmail(false);
                    return;
                }
                let detail = 'Unable to send email.';
                try {
                    const data = await response.json();
                    detail = data?.detail || detail;
                } catch {
                    const text = await response.text();
                    if (text) detail = text;
                }
                setEmailStatus(detail);
                setSendingEmail(false);
                return;
            }

            setEmailStatus('Email sent successfully.');
        } catch (err) {
            setEmailStatus('Unable to send email. Please try again.');
        } finally {
            setSendingEmail(false);
        }
    }

    const hasSummary = output.trim().includes('data-section="summary"');
    
    // Prepare main summary display (excluding email section)
    let renderedOutput = output;
    if (output.trim().startsWith('<section')) {
        try {
            const parser = new DOMParser();
            const doc = parser.parseFromString(output, 'text/html');
            const emailSection = doc.querySelector('section[data-section="patient_email"]');
            if (emailSection) emailSection.remove();
            renderedOutput = doc.body.innerHTML;
        } catch {
            // fallback if DOMParser fails (SSR or other issues), keep original
        }
    } else {
        renderedOutput = `<pre style="white-space: pre-wrap; font-family: 'Plus Jakarta Sans', sans-serif;">${escapeHtml(output)}</pre>`;
    }

    // Prepare email preview
    const emailPreviewHtml = extractDraftEmailHtml(output) || (hasSummary ? '' : extractDraftEmailText(output));
    const evidenceChunks = evidenceMap?.chunks || [];
    const evidenceCitations = evidenceMap?.citations || [];
    const evidenceById = useMemo(() => {
        const map = new Map<string, EvidenceChunk>();
        for (const chunk of evidenceChunks) {
            if (chunk?.id) {
                map.set(chunk.id, chunk);
            }
        }
        return map;
    }, [evidenceChunks]);

    return (
        <div className="mx-auto max-w-5xl px-6 pb-16">
            <form
                onSubmit={handleSubmit}
                className="animate-fade-in rounded-2xl border border-emerald-100/80 bg-white/90 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.55)] backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.9)]"
            >
                <div className="border-b border-emerald-100/80 px-6 py-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="space-y-1">
                            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                                Clinical Intake
                            </p>
                            <div className="flex items-center gap-2">
                                <h2 className="font-display text-2xl text-slate-900 dark:text-slate-100">
                                    Consultation Documentation
                                </h2>
                                <HelpPill
                                    label="Help"
                                    tooltipId="consult-help-tip"
                                    tooltipContent={
                                    <div>
                                        <p className="mb-1 font-semibold text-slate-900 dark:text-slate-100">Current Visit guide</p>
                                        <p className="mb-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-2 py-1 text-[11px] font-semibold text-emerald-900 shadow-sm dark:border-emerald-700/70 dark:bg-emerald-900/50 dark:text-emerald-100">
                                            Purpose: capture today’s visit clearly. Objective: enter the visit details, attach supporting files, and generate a clean summary.
                                        </p>
                                        <ul className="list-disc space-y-1 pl-4">
                                                <li>Fill patient name, visit date, template, and consultation notes.</li>
                                                <li>Upload documents/images/audio (premium) to enrich the summary.</li>
                                                <li>Generate summary streams live; evidence and actions follow.</li>
                                                <li>If uploads + template + date match a prior visit, you’ll see a reuse vs regenerate prompt.</li>
                                                <li>Email tab uses extracted clinician/patient details—verify before sending.</li>
                                            </ul>
                                        </div>
                                    }
                                />
                            </div>
                            <p className="text-sm text-slate-500 dark:text-slate-300">
                                Enter visit details and upload relevant documents or audio recordings.
                            </p>
                        </div>
                        <button
                            type="button"
                            onClick={clearForm}
                            disabled={loading || sendingEmail}
                            className="rounded-xl border border-emerald-200 bg-white px-4 py-2 text-xs font-semibold text-emerald-700 shadow-sm transition hover:bg-emerald-50 disabled:opacity-60 dark:border-emerald-700/60 dark:bg-slate-900/70 dark:text-emerald-200 dark:hover:bg-slate-800"
                        >
                            Clear
                        </button>
                    </div>
                </div>
                <div className="space-y-6 px-6 py-6">
                    <div className="grid gap-6 md:grid-cols-2">
                        <div className="space-y-2">
                            <label htmlFor="patient" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                Patient Name
                            </label>
                            <input
                                id="patient"
                                type="text"
                                required
                                value={patientName}
                                onChange={(e) => setPatientName(e.target.value)}
                                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
                                placeholder="Enter patient's full name"
                            />
                        </div>
                        <div className="space-y-2">
                            <label htmlFor="date" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                Date of Visit
                            </label>
                            <DatePicker
                                id="date"
                                selected={visitDate}
                                onChange={(d: Date | null) => setVisitDate(d)}
                                dateFormat="yyyy-MM-dd"
                                placeholderText="Select date"
                                required
                                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
                            />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <label htmlFor="template" className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
                            Summary Template
                            {!isPremium && (
                                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-200">
                                    Premium only
                                </span>
                            )}
                        </label>
                        <select
                            id="template"
                            value={templateId}
                            onChange={(e) => setTemplateId(e.target.value)}
                            disabled={!isPremium}
                            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-slate-900 shadow-sm focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                        >
                            {SUMMARY_TEMPLATES.map((template) => (
                                <option
                                    key={template.id}
                                    value={template.id}
                                    disabled={!isPremium && template.premium}
                                >
                                    {template.label}
                                </option>
                            ))}
                        </select>
                        {!isPremium && (
                            <p className="text-xs text-amber-600 dark:text-amber-300">
                                Premium unlocks additional clinical summary templates.
                            </p>
                        )}
                    </div>

                    <div className="space-y-2">
                        <label htmlFor="notes" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                            Consultation Notes
                        </label>
                        <textarea
                            id="notes"
                            rows={8}
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500"
                            placeholder="Enter detailed consultation notes..."
                        />
                    </div>

                    <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4 dark:border-slate-700/60 dark:bg-slate-900/70">
                        <div>
                            <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Supporting Files</p>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                Upload documents or audio for secure transcription and summarization.
                            </p>
                            {uploadsDisabled && (
                                <p className="mt-2 text-xs font-semibold text-amber-600 dark:text-amber-300">
                                    Premium feature: document, prescription image, and audio uploads are available on the premium plan.
                                </p>
                            )}
                        </div>
                        <div className="mt-4 grid gap-4 md:grid-cols-3">
                            <div
                                className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950 ${
                                    uploadsDisabled ? 'opacity-60' : ''
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Consultation File</p>
                                    {attachmentFiles.length > 0 && isPremium && (
                                        <button
                                            type="button"
                                            onClick={clearAttachment}
                                            className="text-xs font-semibold uppercase tracking-wide text-rose-600 hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300"
                                        >
                                            Remove
                                        </button>
                                    )}
                                </div>
                                <div className="mt-3 grid gap-3">
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="file"
                                            multiple
                                            id="consultation-files"
                                            accept=".pdf,.doc,.docx,.txt,.md,.markdown,text/plain,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                                            onChange={handleFileChange}
                                            disabled={loading || uploadsDisabled}
                                            ref={attachmentInputRef}
                                            className="sr-only"
                                        />
                                        <label
                                            htmlFor="consultation-files"
                                            className={`inline-flex items-center rounded-lg px-4 py-2 text-sm font-semibold transition ${
                                                loading || uploadsDisabled
                                                    ? 'cursor-not-allowed bg-emerald-100 text-emerald-400 dark:bg-slate-800 dark:text-emerald-500'
                                                    : 'cursor-pointer bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-slate-800 dark:text-emerald-300 dark:hover:bg-slate-700'
                                            }`}
                                        >
                                            Choose Files
                                        </label>
                                        <span className="text-[11px] text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                            {attachmentCount === 0
                                                ? 'No File Chosen'
                                                : `${attachmentCount} file${attachmentCount === 1 ? '' : 's'}`}
                                        </span>
                                    </div>
                                    {attachmentCount > 0 && (
                                        <ul className="list-disc space-y-1 pl-4 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                                            {attachmentFiles.map((file) => (
                                                <li key={file.filename} className="break-all whitespace-normal">
                                                    {file.filename}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {parsingFile && (
                                        <p className="text-xs text-emerald-700 dark:text-emerald-300">
                                            Preparing file for upload...
                                        </p>
                                    )}
                                    {attachmentError && (
                                        <p className="text-xs text-rose-600 dark:text-rose-400">
                                            {attachmentError}
                                        </p>
                                    )}
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                        PDF, DOCX, TXT, or MD up to 5MB.
                                    </p>
                                </div>
                            </div>

                            <div
                                className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950 ${
                                    uploadsDisabled ? 'opacity-60' : ''
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
                                        Prescription Image
                                    </p>
                                    {imageFiles.length > 0 && isPremium && (
                                        <button
                                            type="button"
                                            onClick={clearImage}
                                            className="text-xs font-semibold uppercase tracking-wide text-rose-600 hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300"
                                        >
                                            Remove
                                        </button>
                                    )}
                                </div>
                                <div className="mt-3 grid gap-3">
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="file"
                                            multiple
                                            id="prescription-files"
                                            accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp"
                                            onChange={handleImageChange}
                                            disabled={loading || uploadsDisabled}
                                            ref={imageInputRef}
                                            className="sr-only"
                                        />
                                        <label
                                            htmlFor="prescription-files"
                                            className={`inline-flex items-center rounded-lg px-4 py-2 text-sm font-semibold transition ${
                                                loading || uploadsDisabled
                                                    ? 'cursor-not-allowed bg-emerald-100 text-emerald-400 dark:bg-slate-800 dark:text-emerald-500'
                                                    : 'cursor-pointer bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-slate-800 dark:text-emerald-300 dark:hover:bg-slate-700'
                                            }`}
                                        >
                                            Choose Files
                                        </label>
                                        <span className="text-[11px] text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                            {imageCount === 0
                                                ? 'No File Chosen'
                                                : `${imageCount} file${imageCount === 1 ? '' : 's'}`}
                                        </span>
                                    </div>
                                    {imageCount > 0 && (
                                        <ul className="list-disc space-y-1 pl-4 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                                            {imageFiles.map((file) => (
                                                <li key={file.filename} className="break-all whitespace-normal">
                                                    {file.filename}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {parsingImage && (
                                        <p className="text-xs text-emerald-700 dark:text-emerald-300">
                                            Preparing image for upload...
                                        </p>
                                    )}
                                    {imageError && (
                                        <p className="text-xs text-rose-600 dark:text-rose-400">
                                            {imageError}
                                        </p>
                                    )}
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                        PNG/JPG/WEBP up to 10MB.
                                    </p>
                                </div>
                            </div>

                            <div
                                className={`rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950 ${
                                    uploadsDisabled ? 'opacity-60' : ''
                                }`}
                            >
                                <div className="flex items-center justify-between">
                                    <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">Audio Upload</p>
                                    {audioFiles.length > 0 && isPremium && (
                                        <button
                                            type="button"
                                            onClick={clearAudio}
                                            className="text-xs font-semibold uppercase tracking-wide text-rose-600 hover:text-rose-700 dark:text-rose-400 dark:hover:text-rose-300"
                                        >
                                            Remove
                                        </button>
                                    )}
                                </div>
                                <div className="mt-3 grid gap-3">
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="file"
                                            multiple
                                            id="audio-files"
                                            accept=".mp3,.m4a,.wav,.webm,.ogg,.mp4,.aac,audio/mpeg,audio/mp3,audio/mp4,audio/wav,audio/webm,audio/ogg,audio/aac"
                                            onChange={handleAudioChange}
                                            disabled={loading || uploadsDisabled}
                                            ref={audioInputRef}
                                            className="sr-only"
                                        />
                                        <label
                                            htmlFor="audio-files"
                                            className={`inline-flex items-center rounded-lg px-4 py-2 text-sm font-semibold transition ${
                                                loading || uploadsDisabled
                                                    ? 'cursor-not-allowed bg-emerald-100 text-emerald-400 dark:bg-slate-800 dark:text-emerald-500'
                                                    : 'cursor-pointer bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-slate-800 dark:text-emerald-300 dark:hover:bg-slate-700'
                                            }`}
                                        >
                                            Choose Files
                                        </label>
                                        <span className="text-[11px] text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                            {audioCount === 0
                                                ? 'No File Chosen'
                                                : `${audioCount} file${audioCount === 1 ? '' : 's'}`}
                                        </span>
                                    </div>
                                    {audioCount > 0 && (
                                        <ul className="list-disc space-y-1 pl-4 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                                            {audioFiles.map((file) => (
                                                <li key={file.filename} className="break-all whitespace-normal">
                                                    {file.filename}
                                                </li>
                                            ))}
                                        </ul>
                                    )}
                                    {parsingAudio && (
                                        <p className="text-xs text-emerald-700 dark:text-emerald-300">
                                            Preparing audio for upload...
                                        </p>
                                    )}
                                    {audioError && (
                                        <p className="text-xs text-rose-600 dark:text-rose-400">
                                            {audioError}
                                        </p>
                                    )}
                                    <p className="text-[11px] text-slate-500 dark:text-slate-400">
                                        MP3, M4A, WAV, WEBM, OGG up to 25MB.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="border-t border-emerald-100/80 px-6 py-5 dark:border-slate-700/80">
                    <button
                        type="submit"
                        disabled={loading || parsingFile || parsingImage || parsingAudio}
                        className={`w-full rounded-xl bg-emerald-600 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700 disabled:bg-emerald-300 dark:shadow-emerald-900/40 ${
                            loading ? 'glow-loading' : ''
                        }`}
                    >
                        {loading ? 'Generating Summary...' : 'Generate Summary'}
                    </button>
                    {statusMessage && (
                        <p className="mt-3 text-sm text-emerald-700 text-center dark:text-emerald-300">
                            {statusMessage}
                        </p>
                    )}
                </div>
            </form>

            {output && (
                <section className="animate-fade-in mt-10 rounded-2xl border border-slate-200 bg-white/90 p-6 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-slate-700 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.8)]">
                    <div className="mb-4">
                        <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">Generated Summary</p>
                        <h3 className="font-display text-xl text-slate-900 dark:text-slate-100">Consultation Brief</h3>
                    </div>
                    <div
                        className="markdown-content prose prose-slate max-w-none prose-headings:font-display prose-headings:text-slate-900 dark:prose-invert dark:prose-headings:text-slate-100"
                        dangerouslySetInnerHTML={{ __html: renderedOutput }}
                    />

                    {evidenceCitations.length > 0 && (
                        <details
                            open={evidenceOpen}
                            onToggle={(event) => setEvidenceOpen(event.currentTarget.open)}
                            className="mt-6 rounded-xl border border-emerald-100 bg-emerald-50/60 p-5 dark:border-slate-700 dark:bg-slate-900/70"
                        >
                            <summary className="cursor-pointer list-none text-sm font-semibold text-emerald-700 dark:text-emerald-300">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                    <div>
                                        <span className="text-[11px] uppercase tracking-[0.25em] text-emerald-700 dark:text-emerald-300">
                                            Evidence Links
                                        </span>
                                        <span className="ml-2 text-base text-slate-900 dark:text-slate-100">
                                            Supporting sources
                                        </span>
                                    </div>
                                    <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                                        {evidenceOpen ? '[-] Hide' : '[+] Show'}
                                    </span>
                                </div>
                            </summary>
                            <div className="mt-4 space-y-4 text-sm text-slate-700 dark:text-slate-200">
                                {evidenceCitations.map((citation, index) => {
                                    const chunkIds = citation.chunk_ids || [];
                                    const sources = chunkIds
                                        .map((id) => evidenceById.get(id))
                                        .filter(Boolean) as EvidenceChunk[];
                                    
                                    const sentence = citation.sentence || 'Supported statement';
                                    return (
                                        <div key={`${index}-${sentence.slice(0, 24)}`} className="rounded-lg border border-emerald-100/80 bg-white/80 p-4 dark:border-slate-700/70 dark:bg-slate-950/70">
                                            <p className="font-medium text-slate-900 dark:text-slate-100">
                                                "{sentence}"
                                            </p>
                                            {sources.map((source) => (
                                                <div key={source.id} className="mt-3 rounded-md border border-emerald-100/70 bg-emerald-50/70 p-3 text-xs text-slate-600 dark:border-slate-700/70 dark:bg-slate-900/70 dark:text-slate-300">
                                                    <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-emerald-700 dark:text-emerald-300">
                                                        Source: {source.source}
                                                    </p>
                                                    <blockquote className="border-l-2 border-emerald-200 pl-2 italic dark:border-emerald-700">
                                                        {citation.snippets?.[source.id] || source.text || 'No snippet available.'}
                                                    </blockquote>
                                                    {Array.isArray(source.sources) && source.sources.length > 0 && (
                                                        <ul className="mt-2 list-disc space-y-1 pl-5">
                                                            {source.sources.map((link, linkIndex) => (
                                                                <li key={`${source.id}-${linkIndex}`}>
                                                                    <a
                                                                        href={link.url}
                                                                        target="_blank"
                                                                        rel="noreferrer"
                                                                        className="text-emerald-700 underline-offset-2 hover:underline dark:text-emerald-300"
                                                                    >
                                                                        {link.title || link.url}
                                                                    </a>
                                                                </li>
                                                            ))}
                                                        </ul>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    );
                                })}
                            </div>
                        </details>
                    )}
                    
                    {actions.length > 0 && (
                        <div className="mt-8 rounded-xl border border-blue-200 bg-blue-50/50 p-6 dark:border-blue-800/60 dark:bg-blue-900/20">
                            <h3 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">
                                Suggested Next Actions
                            </h3>
                            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                                {actions.map((action, idx) => (
                                    <div
                                        key={idx}
                                        className="flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-4 shadow-sm transition hover:shadow-md dark:border-slate-700 dark:bg-slate-900"
                                    >
                                        <div>
                                            <div className="flex items-center justify-between mb-2">
                                                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-700 dark:bg-blue-500/20 dark:text-blue-300">
                                                    {action.type}
                                                </span>
                                            </div>
                                            <p className="font-semibold text-slate-900 dark:text-slate-100">
                                                {action.label}
                                            </p>
                                            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                                                {action.details}
                                            </p>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {prescriptions.length > 0 && (
                        <div className="mt-6 rounded-xl border border-slate-200 bg-white/80 p-4 shadow-sm dark:border-slate-700 dark:bg-slate-950/80">
                            <div className="flex flex-col gap-1">
                                <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                                    Translated Prescription
                                </p>
                            </div>
                            <div className="mt-3 space-y-4">
                                {prescriptions.map((entry, index) => (
                                    <div key={`${entry.filename}-${index}`} className="space-y-2">
                                        {entry.filename && (
                                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                                Source: {entry.filename}
                                            </p>
                                        )}
                                        <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-200">
                                            {entry.text}
                                        </pre>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                    {hasSummary && (
                        <>
                            <div className="mt-8 rounded-xl border border-emerald-100 bg-emerald-50/50 p-6 dark:border-slate-700 dark:bg-slate-950/80">
                                <h2 className="text-lg font-semibold text-slate-900 mb-4 dark:text-slate-100">
                                    Send Email
                                </h2>
                                
                                {emailPreviewHtml && (
                                    <div className="mb-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700 dark:bg-slate-900">
                                        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                            Email Preview
                                        </p>
                                        <div 
                                            className="prose prose-sm prose-slate max-w-none dark:prose-invert"
                                            dangerouslySetInnerHTML={{ __html: emailPreviewHtml }} 
                                        />
                                    </div>
                                )}

                                <div className="space-y-4">
                                    <div className="space-y-2">
                                        <label htmlFor="patient-email" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                            Patient Email
                                        </label>
                                <input
                                    id="patient-email"
                                    type="email"
                                    value={patientEmail}
                                    onChange={(e) => {
                                        setPatientEmail(e.target.value);
                                        setPatientEmailError(false);
                                    }}
                                    onBlur={() => {
                                        if (patientEmail.trim()) {
                                            setPatientEmailError(!isValidEmail(patientEmail));
                                        }
                                    }}
                                    autoComplete="email"
                                    className={`w-full rounded-xl border bg-white px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:ring-2 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 ${
                                        patientEmailError
                                            ? 'border-rose-400 focus:border-rose-400 focus:ring-rose-400/30 dark:border-rose-400 dark:focus:border-rose-400 dark:focus:ring-rose-400/30'
                                            : 'border-slate-200 focus:border-emerald-400 focus:ring-emerald-400/30 dark:border-slate-700 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/30'
                                    }`}
                                    placeholder="patient@example.com"
                                />
                                {patientEmailError && (
                                    <p className="text-xs text-rose-600 dark:text-rose-400">
                                        Enter a valid email address.
                                    </p>
                                )}
                            </div>
                            <div className="space-y-2">
                                <label htmlFor="language" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                    Email Language
                                </label>
                                <select
                                    id="language"
                                    value={selectedLanguage}
                                    onChange={(e) => setSelectedLanguage(e.target.value)}
                                    className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm text-slate-900 shadow-sm focus:border-emerald-400 focus:ring-2 focus:ring-emerald-400/30 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
                                >
                                    {LANGUAGE_OPTIONS.map((language) => (
                                        <option key={language} value={language}>
                                            {language}
                                        </option>
                                    ))}
                                </select>
                            </div>
                                    <div className="grid gap-4 md:grid-cols-2">
                                        <div className="space-y-2">
                                            <label htmlFor="doctor-name" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                                Doctor Name
                                            </label>
                                            <input
                                                id="doctor-name"
                                                type="text"
                                                value={doctorName}
                                                onChange={(e) => {
                                                    setDoctorName(e.target.value);
                                                    setDoctorFieldErrors((prev) => ({ ...prev, name: false }));
                                                }}
                                                className={`w-full rounded-xl border px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:ring-2 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 ${
                                                    doctorFieldErrors.name
                                                        ? 'border-rose-400 focus:border-rose-400 focus:ring-rose-400/30 dark:border-rose-400 dark:focus:border-rose-400 dark:focus:ring-rose-400/30'
                                                        : 'border-slate-200 focus:border-emerald-400 focus:ring-emerald-400/30 dark:border-slate-700 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/30'
                                                }`}
                                                placeholder="Dr Jane Smith"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <label htmlFor="doctor-phone" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                                Doctor Phone
                                            </label>
                                    <input
                                        id="doctor-phone"
                                        type="tel"
                                        value={doctorPhone}
                                        onChange={(e) => {
                                            setDoctorPhone(e.target.value);
                                            setDoctorFieldErrors((prev) => ({ ...prev, phone: false }));
                                        }}
                                        onBlur={() => {
                                            if (doctorPhone.trim()) {
                                                setDoctorFieldErrors((prev) => ({
                                                    ...prev,
                                                    phone: !isValidPhone(doctorPhone),
                                                }));
                                            }
                                        }}
                                        inputMode="tel"
                                        autoComplete="tel"
                                        className={`w-full rounded-xl border px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:ring-2 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 ${
                                            doctorFieldErrors.phone
                                                ? 'border-rose-400 focus:border-rose-400 focus:ring-rose-400/30 dark:border-rose-400 dark:focus:border-rose-400 dark:focus:ring-rose-400/30'
                                                : 'border-slate-200 focus:border-emerald-400 focus:ring-emerald-400/30 dark:border-slate-700 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/30'
                                        }`}
                                        placeholder="(555) 123-4567"
                                    />
                                    {doctorFieldErrors.phone && doctorPhone.trim() && (
                                        <p className="text-xs text-rose-600 dark:text-rose-400">
                                            Enter a valid phone number.
                                        </p>
                                    )}
                                </div>
                                        <div className="space-y-2">
                                            <label htmlFor="clinic-name" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                                Clinic Name
                                            </label>
                                            <input
                                                id="clinic-name"
                                                type="text"
                                                value={clinicName}
                                                onChange={(e) => {
                                                    setClinicName(e.target.value);
                                                    setDoctorFieldErrors((prev) => ({ ...prev, clinic: false }));
                                                }}
                                                className={`w-full rounded-xl border px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:ring-2 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 ${
                                                    doctorFieldErrors.clinic
                                                        ? 'border-rose-400 focus:border-rose-400 focus:ring-rose-400/30 dark:border-rose-400 dark:focus:border-rose-400 dark:focus:ring-rose-400/30'
                                                        : 'border-slate-200 focus:border-emerald-400 focus:ring-emerald-400/30 dark:border-slate-700 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/30'
                                                }`}
                                                placeholder="Clinic Name"
                                            />
                                        </div>
                                        <div className="space-y-2">
                                            <label htmlFor="doctor-email" className="block text-sm font-semibold text-slate-700 dark:text-slate-200">
                                                Doctor Email (reply-to)
                                            </label>
                                    <input
                                        id="doctor-email"
                                        type="email"
                                        value={doctorEmail}
                                        onChange={(e) => {
                                            setDoctorEmail(e.target.value);
                                            setDoctorFieldErrors((prev) => ({ ...prev, email: false }));
                                        }}
                                        onBlur={() => {
                                            if (doctorEmail.trim()) {
                                                setDoctorFieldErrors((prev) => ({
                                                    ...prev,
                                                    email: !isValidEmail(doctorEmail),
                                                }));
                                            }
                                        }}
                                        autoComplete="email"
                                        className={`w-full rounded-xl border px-4 py-2.5 text-slate-900 shadow-sm placeholder:text-slate-400 focus:ring-2 dark:bg-slate-900 dark:text-slate-100 dark:placeholder:text-slate-500 ${
                                            doctorFieldErrors.email
                                                ? 'border-rose-400 focus:border-rose-400 focus:ring-rose-400/30 dark:border-rose-400 dark:focus:border-rose-400 dark:focus:ring-rose-400/30'
                                                : 'border-slate-200 focus:border-emerald-400 focus:ring-emerald-400/30 dark:border-slate-700 dark:focus:border-emerald-400 dark:focus:ring-emerald-400/30'
                                        }`}
                                        placeholder="doctor@agentairg.site"
                                    />
                                    {doctorFieldErrors.email && doctorEmail.trim() && (
                                        <p className="text-xs text-rose-600 dark:text-rose-400">
                                            Enter a valid email address.
                                        </p>
                                    )}
                                </div>
                                    </div>
                                    {(doctorFieldErrors.name ||
                                        doctorFieldErrors.phone ||
                                        doctorFieldErrors.clinic ||
                                        doctorFieldErrors.email) && (
                                        <p className="text-sm text-rose-600 dark:text-rose-400">
                                            Doctor name, phone, clinic, and email are required to send the email.
                                        </p>
                                    )}
                                </div>
                            </div>
                            <div className="mt-6 flex flex-col gap-3">
                                <button
                                    type="button"
                                    onClick={handleSendEmail}
                                    disabled={sendingEmail}
                                    className={`w-full rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-200/60 transition hover:bg-slate-800 disabled:bg-slate-400 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400 dark:shadow-emerald-500/20 dark:disabled:bg-emerald-300 ${
                                        sendingEmail ? 'glow-loading' : ''
                                    }`}
                                >
                                    {sendingEmail ? 'Sending Email...' : 'Send Email to Patient'}
                                </button>
                                {emailStatus && (
                                    <p className="text-sm text-center text-slate-700 dark:text-slate-300">
                                        {emailStatus}
                                    </p>
                                )}
                            </div>
                        </>
                    )}
                </section>
            )}

            {regenPromptOpen && regenMatch && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 px-4">
                    <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-5 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                        <div className="space-y-2">
                            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-300">
                                Reuse prior output?
                            </p>
                            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                                A matching visit was already generated
                            </h3>
                            <p className="text-sm text-slate-600 dark:text-slate-300">
                                We found a visit on {regenMatch.date || 'this date'} with the same template and uploaded notes.
                                You can reuse that summary or regenerate a fresh one.
                            </p>
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200">
                                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
                                    Previous summary preview
                                </p>
                                <div className="mt-1 max-h-32 overflow-y-auto text-sm leading-relaxed break-words [overflow-wrap:anywhere]">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm, remarkBreaks]}
                                        components={{
                                            a: ({ className, ...props }) => (
                                                <a
                                                    {...props}
                                                    className={`${className || ''} break-all`.trim()}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                />
                                            ),
                                            p: ({ children, ...props }) => (
                                                <p {...props} className="mb-2 break-words [overflow-wrap:anywhere] last:mb-0">
                                                    {children}
                                                </p>
                                            ),
                                            li: ({ children, ...props }) => (
                                                <li {...props} className="break-words [overflow-wrap:anywhere]">
                                                    {children}
                                                </li>
                                            ),
                                        }}
                                    >
                                        {normalizeChatMarkdown(regenMatch.summary || 'No summary stored.')}
                                    </ReactMarkdown>
                                </div>
                            </div>
                        </div>
                        <div className="mt-4 flex flex-wrap justify-end gap-2">
                            <button
                                type="button"
                                onClick={() => {
                                    setRegenPromptOpen(false);
                                    setRegenMatch(null);
                                }}
                                className="rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:text-slate-300 dark:hover:border-slate-500"
                            >
                                Cancel
                            </button>
                            <button
                                type="button"
                                onClick={() => {
                                    setRegenPromptOpen(false);
                                    if (regenMatch.summary) {
                                        setOutput(regenMatch.summary);
                                        if (typeof window !== 'undefined') {
                                            localStorage.setItem(SUMMARY_OUTPUT_STORAGE_KEY, regenMatch.summary);
                                        }
                                    }
                                    if (regenMatch.evidence) {
                                        setEvidenceMap({
                                            chunks: regenMatch.evidence.chunks || [],
                                            citations: (regenMatch.evidence as any).citations || [],
                                        });
                                        setEvidenceOpen(true);
                                    } else {
                                        setEvidenceMap(null);
                                        setEvidenceOpen(false);
                                    }
                                    setStatusMessage('Reused previous output.');
                                    setLoading(false);
                                    setRegenMatch(null);
                                }}
                                className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700 shadow-sm transition hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200 dark:hover:bg-emerald-900/70"
                            >
                                Reuse it
                            </button>
                            <button
                                type="button"
                                onClick={async () => {
                                    setRegenPromptOpen(false);
                                    setRegenMatch(null);
                                    await runGeneration();
                                }}
                                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 dark:bg-emerald-600 dark:hover:bg-emerald-500"
                            >
                                Regenerate anyway
                            </button>
                        </div>
                    </div>
                </div>
            )}

            <ChatInterface
                patientName={patientName}
                currentSummary={output}
                onSessionExpired={onSessionExpired}
            />
        </div>
    );
}

export default function Product() {
    const { getToken } = useAuth();
    const { signOut } = useClerk();
    const [sessionExpiredOpen, setSessionExpiredOpen] = useState(false);
    const [activeTab, setActiveTab] = useState<WorkspaceTab>('current');
    const selectedPatientNameForChat = '';
    
    const handleSessionExpired = useCallback(async () => {
        // Immediately show the modal. No need for throttling here.
        setSessionExpiredOpen(true);
    }, []);

    const handleRelogin = async () => {
        try {
            await signOut({ redirectUrl: '/' });
        } catch {
            window.location.href = '/';
        }
    };
    const [subscription, setSubscription] = useState<Record<string, any> | null>(null);
    const planRaw = String(subscription?.plan || subscription?.pla || '').toLowerCase();
    const isPremiumPlan = planRaw === 'u:premium_subscription' || planRaw.includes('premium');
    const planLabel = planRaw ? (isPremiumPlan ? 'Premium' : 'Free') : 'Free';
    const workspaceTabs: { id: WorkspaceTab; label: string }[] = [
        { id: 'current', label: 'Current Visit' },
        { id: 'history', label: 'Patient History' },
    ];

    useEffect(() => {
        let mounted = true;
        async function loadSubscription() {
            try {
                const res = await fetchWithAuthRetry(
                    getToken,
                    '/api/subscription',
                    {},
                    noopAuthFailure
                );
                if (!res?.ok) {
                    return;
                }
                const data = await res.json();
                if (mounted) {
                    setSubscription(data);
                }
            } catch {
                // Ignore subscription errors.
            }
        }
        loadSubscription();
        return () => {
            mounted = false;
        };
    }, [getToken, handleSessionExpired]);

    return (
        <>
        <main className="relative min-h-screen overflow-hidden bg-[#f6fbfb] text-slate-900 dark:bg-[#0b1217] dark:text-slate-100">
            {sessionExpiredOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-6 backdrop-blur-sm">
                    <div className="w-full max-w-sm rounded-2xl border border-emerald-100/80 bg-white/95 p-6 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.6)] dark:border-slate-700/80 dark:bg-slate-900/95">
                        <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                            Session Expired
                        </p>
                        <h2 className="mt-2 font-display text-xl text-slate-900 dark:text-slate-100">
                            Please relogin
                        </h2>
                        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                            Your session has expired. Sign in again to continue your consultation.
                        </p>
                        <button
                            type="button"
                            onClick={handleRelogin}
                            className="mt-5 w-full rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700"
                        >
                            Relogin
                        </button>
                    </div>
                </div>
            )}
            <div className="pointer-events-none absolute inset-0">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,#d7eef0_1px,transparent_0)] bg-[size:28px_28px] opacity-60 dark:hidden" />
                <div className="absolute inset-0 hidden bg-[radial-gradient(circle_at_1px_1px,#1f2a35_1px,transparent_0)] bg-[size:28px_28px] opacity-70 dark:block" />
                <div className="absolute -top-32 right-[-10%] h-80 w-80 rounded-full bg-gradient-to-br from-emerald-200/70 to-cyan-200/40 blur-3xl dark:from-emerald-900/40 dark:to-cyan-900/20" />
                <div className="absolute top-48 left-[-5%] h-72 w-72 rounded-full bg-gradient-to-br from-sky-200/50 to-teal-200/30 blur-3xl dark:from-sky-900/40 dark:to-teal-900/20" />
            </div>

            <div className="relative">
                <header className="mx-auto max-w-5xl px-6 pt-16 pb-6">
                    <div className="mb-4">
                        <Link
                            href="/"
                            className="inline-flex min-h-11 items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-3 py-2 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200 dark:hover:border-emerald-500 dark:hover:text-emerald-200"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12l7.5-7.5M3 12h18" />
                            </svg>
                            Back to main
                        </Link>
                    </div>
                    <div className="flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
                        <div>
                            <h1 className="font-display text-4xl text-slate-900 md:text-5xl dark:text-slate-100">
                                Consultation Intelligence
                            </h1>
                            <p className="mt-3 max-w-2xl text-base text-slate-600 dark:text-slate-300">
                                Turn structured notes, documents, or audio into clear visit summaries, next steps,
                                and patient-ready communication in minutes — plus review prior visits with a searchable
                                Patient History tab, last-visit context, and date filters.
                            </p>
                            <div className="mt-4 flex flex-wrap gap-2">
                                <span className="rounded-full border border-emerald-200 bg-white/80 px-3 py-1 text-xs font-semibold text-emerald-700 dark:border-emerald-700/60 dark:bg-slate-900/70 dark:text-emerald-300">
                                    HIPAA-ready workflows
                                </span>
                                <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
                                    Secure transcription
                                </span>
                                <span className="rounded-full border border-slate-200 bg-white/80 px-3 py-1 text-xs font-semibold text-slate-600 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-300">
                                    Patient-friendly summaries
                                </span>
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center gap-3 md:pt-2">
                            {subscription && (
                                <span
                                    className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${
                                        isPremiumPlan
                                            ? 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/60 dark:bg-emerald-900/30 dark:text-emerald-200'
                                            : 'border-slate-200 bg-white/80 text-slate-700 dark:border-slate-700 dark:bg-slate-900/70 dark:text-slate-200'
                                    }`}
                                >
                                    {planLabel}
                                </span>
                            )}
                            <UserButton showName={true} />
                        </div>
                    </div>
                </header>

                <div className="safe-fixed-top-right fixed z-50">
                    <ThemeToggle />
                </div>

                <div className="mx-auto max-w-5xl px-6 pb-4">
                    <div className="flex w-full flex-wrap items-center gap-1 rounded-full border border-slate-200 bg-white/80 p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
                        {workspaceTabs.map((tab) => {
                            const active = tab.id === activeTab;
                            return (
                                <button
                                    key={tab.id}
                                    type="button"
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`min-h-11 flex-1 rounded-full px-4 py-2 text-sm font-semibold transition sm:flex-none ${
                                        active
                                            ? 'bg-emerald-600 text-white shadow-sm shadow-emerald-200/60 dark:bg-emerald-500 dark:text-slate-900'
                                            : 'text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white'
                                    }`}
                                >
                                    {tab.label}
                                </button>
                            );
                        })}
                    </div>
                    <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
                        Switch between documenting the current visit and browsing prior histories.
                    </p>
                </div>

                {activeTab === 'current' ? (
                    <Protect
                    plan="premium_subscription"
                    fallback={
                        <>
                            <ConsultationForm 
                                isPremium={false} 
                                onSessionExpired={handleSessionExpired} 
                            />
                            <div className="mx-auto max-w-5xl px-6 pb-16">
                                <div className="rounded-2xl border border-emerald-100/80 bg-white/90 p-8 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.8)]">
                                    <div className="mb-6">
                                        <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                                            Subscription Required
                                        </p>
                                        <h2 className="font-display text-3xl text-slate-900 dark:text-slate-100">
                                            Healthcare Professional Plan
                                        </h2>
                                        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                                            Unlock file uploads, audio transcription, and email automation with premium.
                                        </p>
                                    </div>
                                    <PricingTable />
                                </div>
                            </div>
                        </>
                    }
                >
                    <ConsultationForm onSessionExpired={handleSessionExpired} />
                    </Protect>
                ) : (
                    <Protect
                        plan="premium_subscription"
                        fallback={
                            <div className="mx-auto max-w-5xl px-6 pb-16">
                                <div className="rounded-2xl border border-emerald-100/80 bg-white/90 p-8 text-center shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.8)]">
                                    <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                                        Premium feature
                                    </p>
                                    <h2 className="mt-2 font-display text-3xl text-slate-900 dark:text-slate-100">
                                        Patient History
                                    </h2>
                                    <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                                        Upgrade to browse longitudinal notes and evidence for your patients.
                                    </p>
                                    <div className="mt-6">
                                        <PricingTable />
                                    </div>
                                </div>
                            </div>
                        }
                    >
                        <PatientHistoryPanel onAuthFailure={() => setSessionExpiredOpen(true)} />
                    </Protect>
                )}
            </div>
        </main>
        </>
    );
}
