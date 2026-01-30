"use client"

import { useState, FormEvent, ChangeEvent, useEffect, useRef, useMemo, useCallback } from 'react';
import { useAuth, useClerk } from '@clerk/nextjs';
import DatePicker from 'react-datepicker';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Protect, PricingTable, UserButton } from '@clerk/nextjs';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import ThemeToggle from '../components/ThemeToggle';

const GENERAL_CHIPS = [
    'How does this app work?',
    'What file formats are supported?',
    'Explain Premium features',
];

const CLINICAL_CHIPS = [
    'Summarize patient history',
    'Draft a referral letter',
    'Check for drug interactions',
    'Explain the treatment plan',
];

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
    const chatAbortRef = useRef<AbortController | null>(null);

    // Sync chat's patient context from the main form
    useEffect(() => {
        // Only sync if the chat is not actively focused on another patient
        if (!showPatientList) {
            setChatPatientName(patientName);
        }
    }, [patientName]);
    
    const activeChips = chatPatientName || currentSummary ? CLINICAL_CHIPS : GENERAL_CHIPS;

    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
        }
    }, [messages]);

    // This is the primary auto-briefing trigger.
    // It runs when the chat's patient context changes.
    useEffect(() => {
        if (chatPatientName && chatPatientName !== lastCheckedPatientRef.current) {
            lastCheckedPatientRef.current = chatPatientName;
            setMessages([]); // Clear chat for new patient context
            
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
        setShowPatientList(false);
    }

    async function handleSend(textOverride?: string) {
        const text = textOverride || input;
        if (!text.trim() || loading) return;

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
                className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg shadow-emerald-600/30 transition hover:scale-105 hover:bg-emerald-700 focus:outline-none focus:ring-4 focus:ring-emerald-400/30 dark:bg-emerald-500 dark:hover:bg-emerald-400"
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
                <div className="fixed bottom-24 right-6 z-50 flex h-[600px] w-96 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white/95 shadow-2xl backdrop-blur dark:border-slate-700 dark:bg-slate-900/95">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-slate-100 bg-white/50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900/50">
                        <div>
                            <h3 className="font-semibold text-slate-900 dark:text-slate-100">MediNotes Assistant</h3>
                            <p className="text-xs text-slate-500 dark:text-slate-400">
                                {chatPatientName ? `Patient: ${chatPatientName}` : 'No patient selected'}
                            </p>
                        </div>
                        <button onClick={handleSwitchPatientClick} className="rounded-md px-2 py-1 text-xs font-semibold text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300 dark:hover:bg-slate-800">
                            {showPatientList ? 'Close' : 'Patient List'}
                        </button>
                    </div>

                    {/* Patient Selector */}
                    {showPatientList && (
                        <div className="absolute top-14 left-0 w-full h-full bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm z-10 p-4">
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
                    <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-slate-50/50 dark:bg-slate-950/30">
                        {messages.length === 0 && (
                            <div className="mt-4 text-center">
                                <p className="text-sm text-slate-500 mb-6 dark:text-slate-400">
                                    {chatPatientName 
                                        ? "I'm ready to assist with this consultation." 
                                        : "I can guide you through the app features."}
                                </p>
                                <div className="flex flex-col gap-2">
                                    {activeChips.map((chip) => (
                                        <button
                                            key={chip}
                                            onClick={() => handleSend(chip)}
                                            className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:border-emerald-500 dark:hover:text-emerald-400"
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
                    <div className="border-t border-slate-100 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
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
                                className="w-full rounded-full border border-slate-200 bg-slate-50 py-2.5 pl-4 pr-12 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100 dark:placeholder:text-slate-500"
                            />
                            <button
                                type="submit"
                                disabled={!input.trim() || loading}
                                className="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-600 text-white transition hover:bg-emerald-700 disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-400"
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
    type?: string;
    summary: string;
    evidence?: EvidenceMap | null;
    has_evidence?: boolean;
};

type WorkspaceTab = 'current' | 'history';

type ConsultationFormProps = {
    isPremium?: boolean;
    onSessionExpired: () => Promise<void>;
};

function PatientHistoryPanel() {
    const { getToken } = useAuth();
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
    const [historyError, setHistoryError] = useState('');
    const [selectedVisit, setSelectedVisit] = useState<HistoryEntry | null>(null);
    const [historyStartDate, setHistoryStartDate] = useState('');
    const [historyEndDate, setHistoryEndDate] = useState('');
    const historyStartRef = useRef<HTMLInputElement | null>(null);
    const historyEndRef = useRef<HTMLInputElement | null>(null);
    const [copyStatus, setCopyStatus] = useState('');
    const [historyQuery, setHistoryQuery] = useState('');
    const timelineRef = useRef<HTMLDivElement | null>(null);
    const [isPanning, setIsPanning] = useState(false);
    const panStartX = useRef(0);
    const panScrollLeft = useRef(0);

    const filteredPatients = patientOptions; // server-side filtering handles search
    const timelineItems = useMemo(() => {
        return historyItems.map((item) => ({
            date: item.date,
            type: item.type || 'Visit',
            hasEvidence: !!item.has_evidence,
        }));
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
                noopAuthFailure
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

    async function loadHistory(patientName: string, startDate?: string, endDate?: string, keyword?: string) {
        if (!patientName) return;
        setHistoryLoading(true);
        setHistoryError('');
        setHistoryItems([]);
        setSelectedVisit(null);
        try {
            const dateParams = [
                startDate ? `start_date=${encodeURIComponent(startDate)}` : null,
                endDate ? `end_date=${encodeURIComponent(endDate)}` : null,
                keyword ? `q=${encodeURIComponent(keyword)}` : null,
            ].filter(Boolean).join('&');
            const dateQuery = dateParams ? `&${dateParams}` : '';
            const res = await fetchWithAuthRetry(
                getToken,
                `/api/patient-history?patient=${encodeURIComponent(patientName)}&limit=10${dateQuery}`,
                {},
                noopAuthFailure
            );
            if (!res?.ok) {
                setHistoryError('Unable to load history.');
                return;
            }
            const data = await res.json();
            setHistoryItems(data?.items || []);
        } catch (err) {
            console.error(err);
            setHistoryError('Unable to load history.');
        } finally {
            setHistoryLoading(false);
        }
    }

    const handleSelect = (patient: HistoryPatient) => {
        setSelectedPatient(patient);
        setSearchTerm(''); // clear search so full list shows next time
        setDropdownOpen(false);
        loadHistory(patient.name, historyStartDate, historyEndDate, historyQuery);
        setSelectedVisit(null);
    };

    const handleLoadMorePatients = () => {
        const now = Date.now();
        if (now - loadMoreCooldownRef.current < 350) return;
        loadMoreCooldownRef.current = now;
        if (optionsLoading || !optionsHasMore) return;
        loadPatients(optionsOffset, optionsQuery, false);
    };

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

    return (
        <div className="mx-auto max-w-5xl px-6 pb-16">
            <section className="animate-fade-in rounded-2xl border border-emerald-100/80 bg-white/90 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.55)] backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.9)]">
                <div className="border-b border-emerald-100/80 px-6 py-5 dark:border-slate-700/80">
                    <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                        Patient History
                    </p>
                    <h2 className="font-display text-2xl text-slate-900 dark:text-slate-100">Longitudinal View</h2>
                    <p className="text-sm text-slate-500 dark:text-slate-300">
                        Select a patient to review prior visits; the layout is ready and will pull from Memory once connected.
                    </p>
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
                                    className="rounded-lg p-1 text-slate-400 transition hover:text-emerald-600 focus:outline-none focus:ring-2 focus:ring-emerald-400/40 dark:text-slate-300 dark:hover:text-emerald-300"
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
                            Type to filter; the dropdown will query the patient index once wired to live data.
                        </p>
                    </div>

                    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-700 dark:bg-slate-950">
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
                                    <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                        {selectedPatient.lastVisit ? `Last visit ${selectedPatient.lastVisit}` : 'Recent visit'}
                                    </span>
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
                                            className={`mt-3 flex items-center gap-3 overflow-x-auto pb-2 ${isPanning ? 'cursor-grabbing' : 'cursor-grab'} select-none`}
                                            ref={timelineRef}
                                            onDragStart={(e) => e.preventDefault()}
                                        >
                                            {historyItems.map((item, idx) => {
                                                const isSelected = selectedVisit?.date === item.date && selectedVisit?.type === item.type;
                                                const isEvidence = (item.type || '').toLowerCase() === 'visit_evidence';
                                                return (
                                                    <div key={`${item.date}-${idx}`} className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={() => setSelectedVisit(item)}
                                                            className={`flex h-16 min-w-[120px] flex-col items-center justify-center rounded-full border px-4 py-2 text-center shadow-sm transition ${
                                                                isSelected
                                                                    ? 'border-emerald-400 bg-emerald-600 text-white'
                                                                    : 'border-slate-200 bg-white text-emerald-700 hover:border-emerald-200 hover:bg-emerald-50 dark:border-slate-700 dark:bg-slate-900 dark:text-emerald-200 dark:hover:border-emerald-500 dark:hover:bg-slate-800'
                                                            }`}
                                                        >
                                                            <span className="text-[11px] font-semibold uppercase tracking-wide leading-tight">
                                                                {item.type || 'Visit'}
                                                            </span>
                                                            <span className={`${isSelected ? 'text-white/90' : 'text-slate-600 dark:text-slate-300'} text-xs font-semibold leading-tight`}>
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
                                    <div className="flex flex-wrap items-center justify-between gap-3">
                                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Visit history</p>
                                        <div className="flex flex-wrap items-center gap-2 text-xs">
                                            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800/80">
                                                <span className="text-slate-500 text-xs font-semibold uppercase tracking-wide dark:text-slate-400">From</span>
                                                <div className="relative flex items-center">
                                                    <button
                                                        type="button"
                                                        onClick={() => historyStartRef.current?.showPicker ? historyStartRef.current.showPicker() : historyStartRef.current?.focus()}
                                                        className="absolute left-1.5 rounded-md p-1 text-emerald-600 transition hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-300 dark:hover:bg-slate-800/80"
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
                                                        className="appearance-none rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm font-semibold text-slate-800 shadow-inner focus:border-emerald-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
                                                    />
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm dark:border-slate-700 dark:bg-slate-800/80">
                                                <span className="text-slate-500 text-xs font-semibold uppercase tracking-wide dark:text-slate-400">To</span>
                                                <div className="relative flex items-center">
                                                    <button
                                                        type="button"
                                                        onClick={() => historyEndRef.current?.showPicker ? historyEndRef.current.showPicker() : historyEndRef.current?.focus()}
                                                        className="absolute left-1.5 rounded-md p-1 text-emerald-600 transition hover:bg-emerald-50 hover:text-emerald-700 dark:text-emerald-300 dark:hover:bg-slate-800/80"
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
                                                        className="appearance-none rounded-lg border border-slate-200 bg-white pl-9 pr-3 py-2 text-sm font-semibold text-slate-800 shadow-inner focus:border-emerald-400 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50"
                                                    />
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <input
                                                    type="text"
                                                    value={historyQuery}
                                                    onChange={(e) => setHistoryQuery(e.target.value)}
                                                    placeholder="Filter by keyword"
                                                    className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm focus:border-emerald-400 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                                                />
                                                <button
                                                    type="button"
                                                    disabled={!selectedPatient}
                                                    onClick={() => selectedPatient && loadHistory(selectedPatient.name, historyStartDate, historyEndDate, historyQuery)}
                                                    className="rounded-lg border border-slate-200 px-3 py-1 font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
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
                                                    if (selectedPatient) {
                                                        loadHistory(selectedPatient.name, '', '', '');
                                                    }
                                                }}
                                                className="rounded-lg border border-slate-200 px-3 py-1 font-semibold text-slate-500 transition hover:border-slate-300 hover:text-slate-700 dark:border-slate-700 dark:text-slate-300 dark:hover:border-emerald-400 dark:hover:text-emerald-200"
                                            >
                                                Clear
                                            </button>
                                            {selectedVisit && (
                                                <button
                                                    type="button"
                                                    onClick={() => setSelectedVisit(null)}
                                                    className="rounded-full border border-slate-200 px-3 py-1 font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                                >
                                                    Return to list
                                                </button>
                                            )}
                                        </div>
                                    </div>
                                    {historyLoading && <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">Loading history...</p>}
                                    {historyError && <p className="mt-2 text-sm text-rose-600 dark:text-rose-400">{historyError}</p>}
                                    {!historyLoading && !historyError && historyItems.length === 0 && (
        <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No stored visits yet.</p>
                                    )}

                                    {!selectedVisit && (
                                        <div className="mt-3 max-h-[48rem] space-y-3 overflow-y-auto pr-1">
                                            {historyItems.map((item, idx) => {
                                                const isEvidence = (item.type || '').toLowerCase() === 'visit_evidence';
                                                return (
                                                <button
                                                    key={idx}
                                                    type="button"
                                                    onClick={() => setSelectedVisit(item)}
                                                    className="w-full text-left"
                                                >
                                                    <div className={`rounded-lg border p-3 shadow-sm transition hover:-translate-y-px hover:border-emerald-200 hover:shadow-md dark:border-slate-800 dark:bg-slate-900/70 dark:hover:border-emerald-400/50 ${
                                                        isEvidence ? 'border-emerald-200 bg-emerald-50/70 dark:bg-emerald-950/40' : 'border-slate-200 bg-white/90'
                                                    }`}>
                                                        <div className="flex items-center justify-between">
                                                            <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                                                                <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                                    {item.type || 'Visit'}
                                                                </span>
                                                                <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                                                                    {item.date || 'Unknown date'}
                                                                </span>
                                                            </div>
                                                            <div className="flex items-center gap-2">
                                                                {item.has_evidence && (
                                                                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                                        Evidence
                                                                    </span>
                                                                )}
                                                                <span className="text-[11px] font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-300">
                                                                    View details
                                                                </span>
                                                            </div>
                                                        </div>
                                                        <div className="mt-2 rounded-lg bg-slate-50/60 p-3 text-sm text-slate-700 shadow-inner whitespace-pre-line dark:bg-slate-900/40 dark:text-slate-200 line-clamp-6">
                                                            <ReactMarkdown
                                                                remarkPlugins={[remarkGfm, remarkBreaks]}
                                                                components={{
                                                                    a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                                                                    p: ({ children, ...props }) => <p {...props} className="mb-2 last:mb-0" children={children} />,
                                                                }}
                                                            >
                                                                {normalizeChatMarkdown(item.summary || 'No summary stored.')}
                                                            </ReactMarkdown>
                                                        </div>
                                                    </div>
                                                </button>
                                                );
                                            })}
                                        </div>
                                    )}

                                    {selectedVisit && (
                                        <div className="mt-3 space-y-3">
                                            <div className={`rounded-lg border p-4 shadow-md ${
                                                (selectedVisit.type || '').toLowerCase() === 'visit_evidence'
                                                    ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/50'
                                                    : 'border-slate-200 bg-white/95 dark:border-slate-800 dark:bg-slate-900/85'
                                            }`}>
                                                <div className="flex flex-wrap items-center justify-between gap-3">
                                                    <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-200">
                                                            {selectedVisit.type || 'Visit'}
                                                        </span>
                                                        <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                                                            {selectedVisit.date || 'Unknown date'}
                                                        </span>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <button
                                                            type="button"
                                                            onClick={() => setSelectedVisit(null)}
                                                            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-700 transition hover:border-emerald-400 hover:text-emerald-700 dark:border-slate-700 dark:text-slate-200 dark:hover:border-emerald-400 dark:hover:text-emerald-300"
                                                        >
                                                            Return to list
                                                        </button>
                                                        <button
                                                            type="button"
                                                            onClick={() => selectedVisit.summary && handleCopySummary(selectedVisit.summary)}
                                                            className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-200 dark:hover:bg-emerald-900/70"
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
                                                <div className="mt-3 rounded-lg bg-slate-50/80 p-4 text-sm leading-relaxed text-slate-800 shadow-inner whitespace-pre-line dark:bg-slate-900/60 dark:text-slate-200">
                                                    <ReactMarkdown
                                                        remarkPlugins={[remarkGfm, remarkBreaks]}
                                                        components={{
                                                            a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
                                                            p: ({ children, ...props }) => (
                                                                <p {...props} className="mb-3 last:mb-0">
                                                                    {typeof children === 'string'
                                                                        ? renderHistoryHighlighted(children)
                                                                        : children}
                                                                </p>
                                                            ),
                                                            li: ({ children, ...props }) => (
                                                                <li {...props} className="mb-1 last:mb-0">
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
                                                        <div className="flex items-center justify-between">
                                                            <div>
                                                                <p className="text-[11px] uppercase tracking-[0.25em] text-emerald-700 dark:text-emerald-300">
                                                                    Evidence
                                                                </p>
                                                                <p className="text-sm text-slate-700 dark:text-slate-200">
                                                                    Source snippets supporting this visit
                                                                </p>
                                                            </div>
                                                            <span className="rounded-full bg-white px-3 py-1 text-[11px] font-semibold text-emerald-700 shadow-sm dark:bg-slate-900 dark:text-emerald-200">
                                                                {selectedVisit.evidence.chunks.length} sources
                                                            </span>
                                                        </div>
                                                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                                                            {selectedVisit.evidence.chunks.map((chunk, idx) => (
                                                                <div key={chunk.id || idx} className="rounded-lg border border-emerald-100 bg-white/95 p-3 shadow-[0_10px_30px_-22px_rgba(16,185,129,0.6)] dark:border-emerald-800/50 dark:bg-slate-900/80 dark:shadow-[0_10px_30px_-22px_rgba(16,185,129,0.35)]">
                                                                    <div className="flex items-center justify-between text-xs">
                                                                        <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-semibold uppercase tracking-wide text-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-200">
                                                                            {chunk.source || 'Source'}
                                                                        </span>
                                                                        {chunk.label && (
                                                                            <span className="text-[11px] font-semibold text-slate-500 dark:text-slate-300">
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
                                                                                className={`mt-2 rounded-lg p-3 text-sm text-slate-700 break-words whitespace-pre-wrap dark:text-slate-200 ${bg}`}
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
                                                                                <span className="align-middle">
                                                                                    {(isHistory && `History: ${rest}`) ||
                                                                                        (isUpload && `Upload: ${rest}`) ||
                                                                                        raw}
                                                                                </span>
                                                                            </div>
                                                                        );
                                                                    })()}
                                                                    {chunk.sources && chunk.sources.length > 0 && (
                                                                        <div className="mt-3 space-y-1 text-[11px] text-emerald-700 dark:text-emerald-300">
                                                                            {chunk.sources.map((s, i) => (
                                                                                <a
                                                                                    key={i}
                                                                                    href={s.url || '#'}
                                                                                    target="_blank"
                                                                                    rel="noopener noreferrer"
                                                                                    className="flex items-center gap-1 underline decoration-emerald-400 underline-offset-2 hover:text-emerald-800 dark:hover:text-emerald-100"
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

    async function handleSubmit(e: FormEvent) {
        e.preventDefault();
        if (!notes.trim() && !attachmentFiles.length && !audioFiles.length && !imageFiles.length) {
            setOutput('Please add consultation notes or upload a file/audio/image before generating a summary.');
            return;
        }

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
                        <div>
                            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                                Clinical Intake
                            </p>
                            <h2 className="font-display text-2xl text-slate-900 dark:text-slate-100">Consultation Documentation</h2>
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
                        <div className="flex items-center gap-3 md:pt-2">
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

                <div className="fixed right-4 top-4 z-50 sm:right-6 sm:top-6">
                    <ThemeToggle />
                </div>

                <div className="mx-auto max-w-5xl px-6 pb-4">
                    <div className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white/80 p-1 shadow-sm dark:border-slate-700 dark:bg-slate-900/80">
                        {workspaceTabs.map((tab) => {
                            const active = tab.id === activeTab;
                            return (
                                <button
                                    key={tab.id}
                                    type="button"
                                    onClick={() => setActiveTab(tab.id)}
                                    className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
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
                        <PatientHistoryPanel />
                    </Protect>
                )}
            </div>
        </main>
        {/* Global MediNotes Assistant (available on all tabs) */}
        <ChatInterface
            patientName={selectedPatientNameForChat}
            currentSummary=""
            onSessionExpired={handleSessionExpired}
        />
        </>
    );
}
