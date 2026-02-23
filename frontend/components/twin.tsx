'use client';
/* eslint-disable @next/next/no-img-element */

import { useState, useRef, useEffect, useMemo, useCallback, isValidElement, type ChangeEvent } from 'react';
import { Send, Bot, History, X, RefreshCw, Maximize2, Paperclip, MessageSquarePlus, Brain, Terminal, LifeBuoy, Mail, FileDown, Plus, Minus, Search } from 'lucide-react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
}

interface SessionSummary {
    session_id: string;
    title: string;
    updated_at: string;
    message_count: number;
}

interface ApiConversationMessage {
    role?: 'user' | 'assistant';
    content?: string;
    timestamp?: string;
}

interface MemoryCandidate {
    id: string;
    text: string;
    category: string;
    ttl_days: number;
    created_at?: string;
    source?: { excerpt?: string };
}

interface ApprovedMemory {
    id: string;
    text: string;
    category: string;
    expires_at?: string;
}

interface QuotaStatus {
    enabled: boolean;
    day: string;
    reset_at: string;
    limits: {
        tokens: number;
        pdf: number;
        email: number;
    };
    usage: {
        tokens: number;
        pdf: number;
        email: number;
    };
    remaining: {
        tokens: number;
        pdf: number;
        email: number;
    };
}

export default function Twin() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [asyncStatus, setAsyncStatus] = useState<string | null>(null);
    const [activeJobId, setActiveJobId] = useState<string | null>(null);
    const [sessionId, setSessionId] = useState<string>('');
    const [sessions, setSessions] = useState<SessionSummary[]>([]);
    const [isHistoryOpen, setIsHistoryOpen] = useState(false);
    const [expandStep, setExpandStep] = useState(0);
    const [userId, setUserId] = useState('');
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);
    const [historyTab, setHistoryTab] = useState<'history' | 'memory'>('history');
    const [memoryCandidates, setMemoryCandidates] = useState<MemoryCandidate[]>([]);
    const [memoryApproved, setMemoryApproved] = useState<ApprovedMemory[]>([]);
    const [isLoadingMemory, setIsLoadingMemory] = useState(false);
    const [memoryError, setMemoryError] = useState<string | null>(null);
    const [memoryAction, setMemoryAction] = useState<{ id: string; action: 'approve' | 'reject' | 'remove' } | null>(null);
    const [isClearingMemory, setIsClearingMemory] = useState(false);
    const [isMemoryInfoOpen, setIsMemoryInfoOpen] = useState(false);
    const [isApprovedMemoryOpen, setIsApprovedMemoryOpen] = useState(true);
    const [quota, setQuota] = useState<QuotaStatus | null>(null);
    const [isLoadingQuota, setIsLoadingQuota] = useState(false);
    const [isBootstrapping, setIsBootstrapping] = useState(true);
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'uploaded' | 'error'>('idle');
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadedFileId, setUploadedFileId] = useState<string | null>(null);
    const [viewport, setViewport] = useState({ width: 0, height: 0 });
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const cancelRequestedRef = useRef(false);
    const abortControllerRef = useRef<AbortController | null>(null);
    const bootstrapDoneRef = useRef(false);
    const inputScrollbarRaf = useRef<number | null>(null);
    const [inputScrollbar, setInputScrollbar] = useState({ visible: false, top: 0, height: 0 });
    const fileInputRef = useRef<HTMLInputElement>(null);
    const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
    const API_URL = configuredApiUrl
        ? configuredApiUrl.replace(/\/+$/, '')
        : (process.env.NODE_ENV === 'development' ? 'http://localhost:8000' : '');
    const normalizeExternalUrl = useCallback((value?: string | Blob): string => {
        if (!value || typeof value !== 'string') return '';
        let next = value.trim();
        next = next.replace(/^<|>$/g, '');
        next = next.replace(/&amp;/g, '&');
        if (next.startsWith('/')) return `${API_URL}${next}`;
        if (/^(https?:)?\/\//i.test(next)) return next;
        return `https://${next}`;
    }, [API_URL]);
    const markdownComponents = useMemo<Components>(() => ({
        p: ({ children, node }) => {
            const parts = Array.isArray(children) ? children : [children];
            const meaningful = parts.filter((c) => c !== null && c !== undefined && c !== false);
            const first = meaningful[0];
            const childTags = Array.isArray((node as { children?: Array<{ tagName?: string }> } | undefined)?.children)
                ? ((node as { children?: Array<{ tagName?: string }> }).children || []).map((child) =>
                    String(child?.tagName || '').toLowerCase()
                )
                : [];
            const isLinkOnly =
                (childTags.length === 1 && childTags[0] === 'a') ||
                (meaningful.length === 1 &&
                    isValidElement(first) &&
                    first.type === 'a');
            const hasBlockLikeChild =
                childTags.some((tag) => ['img', 'figure', 'table', 'pre', 'blockquote', 'ul', 'ol', 'div'].includes(tag)) ||
                meaningful.some((c) => {
                    if (!isValidElement(c)) return false;
                    const elType = typeof c.type === 'string' ? c.type.toLowerCase() : '';
                    if (elType === 'img' || elType === 'figure' || elType === 'figcaption') return true;
                    const tagFromNode = String((c.props as { node?: { tagName?: string } } | undefined)?.node?.tagName || '').toLowerCase();
                    return tagFromNode === 'img' || tagFromNode === 'figure' || tagFromNode === 'figcaption';
                });
            const wrapperClass = `last:mb-0 ${
                isLinkOnly ? 'mb-1' : 'mb-2'
            }`;
            if (hasBlockLikeChild) {
                return (
                    <div className={wrapperClass} style={{ whiteSpace: 'normal' }}>
                        {children}
                    </div>
                );
            }
            return (
                <p
                    className={wrapperClass}
                    style={{ whiteSpace: 'normal' }}
                >
                    {children}
                </p>
            );
        },
        h1: ({ children }) => (
            <h1 className="mb-3 mt-4 text-[21px] font-semibold text-slate-900">
                {children}
            </h1>
        ),
        h2: ({ children }) => (
            <h2 className="mb-3 mt-4 text-[19px] font-semibold text-slate-900">
                {children}
            </h2>
        ),
        h3: ({ children }) => (
            <h3 className="mb-2 mt-3 text-[17px] font-semibold text-slate-900">
                {children}
            </h3>
        ),
        h4: ({ children }) => (
            <h4 className="mb-2 mt-3 text-[15px] font-semibold text-slate-900">
                {children}
            </h4>
        ),
        ul: ({ children }) => (
            <ul className="mb-3 list-disc pl-5">
                {children}
            </ul>
        ),
        ol: ({ children }) => (
            <ol className="mb-3 list-decimal pl-5">
                {children}
            </ol>
        ),
        table: ({ children }) => (
            <div className="mb-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
                <table className="w-full text-left text-xs">{children}</table>
            </div>
        ),
        thead: ({ children }) => (
            <thead className="bg-slate-50 text-slate-700">{children}</thead>
        ),
        tbody: ({ children }) => (
            <tbody className="text-slate-700">{children}</tbody>
        ),
        tr: ({ children }) => (
            <tr className="border-t border-slate-100">{children}</tr>
        ),
        th: ({ children }) => (
            <th className="px-3 py-2 font-semibold">{children}</th>
        ),
        td: ({ children }) => (
            <td className="px-3 py-2 align-top">{children}</td>
        ),
        li: ({ children }) => (
            <li className="leading-snug">
                {children}
            </li>
        ),
        a: ({ href, children }) => {
            const safeHref = normalizeExternalUrl(href);
            return (
            <a
                href={safeHref || '#'}
                target="_blank"
                rel="noreferrer"
                className="break-all text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
            >
                {children}
            </a>
            );
        },
        img: ({ src, alt }) => {
            const safeSrc = normalizeExternalUrl(src);
            if (!safeSrc) {
                return (
                    <span className="text-xs text-slate-500">
                        Image URL is missing.
                    </span>
                );
            }
            const isPdf = /\.pdf(\?|#|$)/i.test(safeSrc);
            const isImage = /\.(png|jpe?g|gif|webp|svg)(\?|#|$)/i.test(safeSrc);
            if (isPdf || !isImage) {
                const label = isPdf ? "Open PDF" : "Open file";
                return (
                    <a
                        href={safeSrc}
                        target="_blank"
                        rel="noreferrer"
                        className="break-all text-[11px] text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
                    >
                        {label}
                    </a>
                );
            }
            return (
                <figure className="my-1.5">
                    <img
                        src={safeSrc}
                        alt={alt || 'Generated chart'}
                        loading="eager"
                        decoding="async"
                        referrerPolicy="no-referrer"
                        className="max-w-full rounded-lg border border-slate-200 bg-white shadow-sm"
                        data-loaded="false"
                        onLoad={(e) => {
                            e.currentTarget.dataset.loaded = 'true';
                        }}
                        onError={(e) => {
                            const img = e.currentTarget;
                            img.style.display = 'none';
                            const fallback = img.nextElementSibling as HTMLElement | null;
                            if (fallback) fallback.style.display = 'inline';
                        }}
                    />
                    <a
                        href={safeSrc}
                        target="_blank"
                        rel="noreferrer"
                        className="hidden break-all text-[11px] text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
                    >
                        Open image
                    </a>
                    {alt && <figcaption className="mt-0.5 text-[10px] text-slate-500">{alt}</figcaption>}
                </figure>
            );
        },
        code: ({ children }) => (
            <code className="rounded bg-slate-100 px-1 py-0.5 text-[0.85em]">
                {children}
            </code>
        ),
        blockquote: ({ children }) => (
            <blockquote className="mb-3 border-l-2 border-slate-200 pl-3 text-slate-600">
                {children}
            </blockquote>
        ),
        pre: ({ children }) => (
            <pre className="mb-3 overflow-x-auto rounded-lg bg-slate-100 p-3 text-xs leading-relaxed">
                {children}
            </pre>
        ),
    }), [normalizeExternalUrl]);

    const isValidSyncCode = (code: string) => /^[a-zA-Z0-9_-]{8,64}$/.test(code);

    const generateSyncCode = () => {
        const bytes = new Uint8Array(8);
        crypto.getRandomValues(bytes);
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    };

    const lastSessionKey = useCallback((uid: string) => `last_session_id:${uid}`, []);
    const displayStatusLabel = asyncStatus;
    const showInitialLoader = isBootstrapping && messages.length === 0;
    const formatCount = (value: number) => {
        if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
        if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
        return `${value}`;
    };
    const quotaItems = [
        { key: 'tokens', label: 'Tokens', tone: 'text-rose-100 border-rose-200/25 bg-rose-300/10' },
        { key: 'pdf', label: 'PDF', tone: 'text-indigo-100 border-indigo-200/25 bg-indigo-300/10' },
        { key: 'email', label: 'Email', tone: 'text-emerald-100 border-emerald-200/25 bg-emerald-300/10' },
    ] as const;

    const pollJob = async (jobId: string, uid: string, initialDelayMs = 2000) => {
        let delay = initialDelayMs;
        const maxAttempts = 120;
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            await new Promise(resolve => setTimeout(resolve, delay));
            if (cancelRequestedRef.current) {
                throw new Error('canceled');
            }
            const res = await fetch(
                `${API_URL}/jobs/${jobId}?user_id=${encodeURIComponent(uid)}`
            );
            if (!res.ok) {
                throw new Error('Failed to fetch job status');
            }
            const job = await res.json();
            if (job.status === 'queued') {
                setAsyncStatus('Queued… (5%)');
            } else if (job.status === 'running') {
                const progress = Number.isFinite(job.status_progress) ? Math.max(0, Math.min(100, job.status_progress)) : null;
                const label = job.status_message || 'Working…';
                setAsyncStatus(progress !== null ? `${label} (${progress}%)` : label);
            } else {
                setAsyncStatus(null);
            }
            if (job.status === 'completed') {
                return job;
            }
            if (job.status === 'canceled') {
                setAsyncStatus(null);
                return job;
            }
            if (job.status === 'failed') {
                setAsyncStatus(null);
                throw new Error(job.error || 'Job failed');
            }
            delay = Math.min(Math.round(delay * 1.4), 8000);
        }
        throw new Error('Job polling timed out');
    };

    const [hasAvatar, setHasAvatar] = useState(false);
    useEffect(() => {
        fetch('/avatar.jpg', { method: 'HEAD' })
            .then(res => setHasAvatar(res.ok))
            .catch(() => setHasAvatar(false));
    }, []);

    const renderPremiumAvatar = useCallback((sizeClass: string, iconClass: string, glow = true) => (
        <div className={`relative ${sizeClass}`}>
            {glow ? (
                <>
                    <div className="absolute -inset-1 rounded-full bg-gradient-to-br from-amber-200/50 via-slate-200/30 to-sky-300/40 blur-[8px]" />
                    <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-white/40 via-transparent to-white/10 opacity-70" />
                </>
            ) : null}
            <div className="relative w-full h-full rounded-full bg-slate-900/60 p-[2px] shadow-[0_8px_18px_rgba(15,23,42,0.45)]">
                <div className="relative w-full h-full rounded-full bg-slate-900/60 border border-white/25 overflow-hidden flex items-center justify-center">
                    <span className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/20 via-transparent to-transparent" />
                    <span className="pointer-events-none absolute -right-3 -top-3 h-8 w-8 rounded-full bg-white/10" />
                    {hasAvatar ? (
                        <img
                            src="/avatar.jpg"
                            alt="Digital Assistant Avatar"
                            className="w-full h-full object-cover"
                        />
                    ) : (
                        <Bot className={`${iconClass} text-white`} />
                    )}
                </div>
            </div>
        </div>
    ), [hasAvatar]);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const triggerFileSelect = () => {
        fileInputRef.current?.click();
    };

    const cancelActiveJob = async () => {
        cancelRequestedRef.current = true;
        if (abortControllerRef.current) {
            abortControllerRef.current.abort();
        }
        if (!activeJobId || !userId) {
            setAsyncStatus(null);
            setIsLoading(false);
            setActiveJobId(null);
            abortControllerRef.current = null;
            return;
        }
        try {
            await fetch(
                `${API_URL}/jobs/${activeJobId}/cancel?user_id=${encodeURIComponent(userId)}`,
                { method: 'POST' }
            );
        } catch (err) {
            console.error('Cancel error:', err);
        } finally {
            setAsyncStatus(null);
            setIsLoading(false);
            setActiveJobId(null);
            abortControllerRef.current = null;
        }
    };

    const renderedMessages = useMemo(() => (
        messages.map((message) => (
            <div
                key={message.id}
                className={`flex gap-3 ${
                    message.role === 'user' ? 'justify-end' : 'justify-start'
                }`}
            >
                {message.role === 'assistant' && (
                    <div className="flex-shrink-0">
                        {renderPremiumAvatar('w-9 h-9', 'w-5 h-5', false)}
                    </div>
                )}

                <div
                    className={`max-w-[82%] rounded-2xl px-2.5 py-2 text-[13px] leading-relaxed shadow-sm sm:max-w-[74%] lg:max-w-[64%] ${
                        message.role === 'user'
                            ? 'bg-gradient-to-br from-slate-800 to-slate-900 text-white whitespace-pre-wrap'
                            : 'bg-white/90 border border-white/60 text-slate-800'
                    }`}
                >
                    {message.role === 'assistant' ? (
                        <div className="text-sm leading-relaxed chat-markdown">
                            <ReactMarkdown
                                remarkPlugins={[remarkGfm]}
                                components={markdownComponents}
                            >
                                {message.content}
                            </ReactMarkdown>
                        </div>
                    ) : (
                        <p className="whitespace-pre-wrap">{message.content}</p>
                    )}
                    <p
                        className={`text-[9px] mt-1 ${
                            message.role === 'user' ? 'text-slate-300' : 'text-slate-500'
                        }`}
                    >
                        {message.timestamp.toLocaleTimeString()}
                    </p>
                </div>

                {message.role === 'user' && (
                    <div className="flex-shrink-0">
                        <div className="relative w-9 h-9">
                            <div className="absolute -inset-[1px] rounded-full bg-gradient-to-br from-white/60 via-slate-200/40 to-slate-400/40" />
                            <div className="relative w-full h-full rounded-full bg-slate-900/40 p-[1px] shadow-[0_5px_12px_rgba(15,23,42,0.3)]">
                                <img
                                    src="/user.png"
                                    alt="User Avatar"
                                    className="w-full h-full rounded-full border border-white/40 object-cover"
                                />
                            </div>
                        </div>
                    </div>
                )}
            </div>
        ))
    ), [messages, markdownComponents, renderPremiumAvatar]);

    const resetUpload = () => {
        setSelectedFile(null);
        setUploadStatus('idle');
        setUploadError(null);
        setUploadedFileId(null);
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0] || null;
        if (!file) return;
        setSelectedFile(file);
        setUploadStatus('uploading');
        setUploadError(null);
        setUploadedFileId(null);

        const maxBytes = 50 * 1024 * 1024;
        if (file.size > maxBytes) {
            setUploadStatus('error');
            setUploadError('File exceeds 50MB limit.');
            return;
        }

        try {
            // Prefer direct-to-S3 upload when running against a deployed API.
            // This avoids API Gateway/Lambda binary transforms that can corrupt PDFs.
            const presignResp = await fetch(`${API_URL}/uploads/presign`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    filename: file.name,
                    size_bytes: file.size,
                    content_type: file.type || undefined,
                }),
            });

            if (presignResp.ok) {
                const presign = await presignResp.json();
                const putResp = await fetch(presign.upload_url, {
                    method: 'PUT',
                    headers: presign.headers || {},
                    body: file,
                });
                if (!putResp.ok) throw new Error('Failed to upload file to S3');
                setUploadedFileId(presign.file_id);
                setUploadStatus('uploaded');
                return;
            }

            // Fallback to legacy multipart upload (useful for local/dev without S3).
            const formData = new FormData();
            formData.append('file', file);
            const response = await fetch(`${API_URL}/uploads`, { method: 'POST', body: formData });
            if (!response.ok) throw new Error('Failed to upload file');
            const data = await response.json();
            setUploadedFileId(data.file_id);
            setUploadStatus('uploaded');
        } catch (err) {
            console.error('Upload failed:', err);
            setUploadStatus('error');
            setUploadError('Upload failed. Please try again.');
        }
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    const loadConversation = useCallback(async (uid: string, sid: string) => {
        try {
            const response = await fetch(`${API_URL}/conversation/${sid}?user_id=${encodeURIComponent(uid)}`);
            if (!response.ok) throw new Error('Failed to load conversation');
            const data = await response.json();
            const restored: Message[] = (data.messages || []).map((msg: ApiConversationMessage, index: number) => {
                const role: Message['role'] = msg.role === 'assistant' ? 'assistant' : 'user';
                const content = typeof msg.content === 'string' ? msg.content : '';
                return {
                    id: `${sid}-${index}`,
                    role,
                    content,
                    timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
                };
            });
            setMessages(restored);
            setSessionId(sid);
            localStorage.setItem(lastSessionKey(uid), sid);
        } catch (error) {
            console.error('Error loading conversation:', error);
        }
    }, [API_URL, lastSessionKey]);

    const loadHistory = useCallback(async (uid: string, autoRestore = true) => {
        setIsLoadingHistory(true);
        try {
            const response = await fetch(
                `${API_URL}/conversations?user_id=${encodeURIComponent(uid)}&limit=5`
            );
            if (!response.ok) throw new Error('Failed to load history');
            const data = await response.json();
            const fetched: SessionSummary[] = data.sessions || [];
            setSessions(fetched);

            if (autoRestore) {
                const lastId = localStorage.getItem(lastSessionKey(uid));
                const match = fetched.find(s => s.session_id === lastId);
                const targetId = match ? match.session_id : fetched[0]?.session_id;
                if (targetId) {
                    await loadConversation(uid, targetId);
                } else {
                    setMessages([]);
                    setSessionId('');
                }
            }
        } catch (error) {
            console.error('Error loading history:', error);
            setSessions([]);
        } finally {
            setIsLoadingHistory(false);
        }
    }, [API_URL, lastSessionKey, loadConversation]);

    const loadMemory = useCallback(async (uid: string, opts: { silent?: boolean } = {}) => {
        const { silent = false } = opts;
        if (!silent) {
            setIsLoadingMemory(true);
            setMemoryError(null);
        }
        try {
            const [candidatesRes, approvedRes] = await Promise.all([
                fetch(`${API_URL}/memory/candidates?user_id=${encodeURIComponent(uid)}`),
                fetch(`${API_URL}/memory?user_id=${encodeURIComponent(uid)}`),
            ]);
            if (!candidatesRes.ok || !approvedRes.ok) {
                throw new Error('Failed to load memory');
            }
            const candidatesData = await candidatesRes.json();
            const approvedData = await approvedRes.json();
            const nextCandidates = candidatesData.candidates || [];
            const nextApproved = approvedData.memory || [];
            setMemoryCandidates(nextCandidates);
            setMemoryApproved(nextApproved);
        } catch (error) {
            console.error('Error loading memory:', error);
            if (!silent) {
                setMemoryError('Unable to load memory. Please try again.');
            }
        } finally {
            if (!silent) {
                setIsLoadingMemory(false);
            }
        }
    }, [API_URL]);

    const loadQuota = useCallback(async (uid: string, opts: { silent?: boolean } = {}) => {
        const { silent = false } = opts;
        if (!silent) {
            setIsLoadingQuota(true);
        }
        try {
            const response = await fetch(`${API_URL}/quota?user_id=${encodeURIComponent(uid)}`);
            if (!response.ok) throw new Error('Failed to load quota');
            const data = await response.json();
            setQuota(data as QuotaStatus);
        } catch (error) {
            console.error('Error loading quota:', error);
            if (!silent) {
                setQuota(null);
            }
        } finally {
            if (!silent) {
                setIsLoadingQuota(false);
            }
        }
    }, [API_URL]);

    const sendMessage = async () => {
        const hasAttachment = !!(selectedFile && uploadedFileId && uploadStatus === 'uploaded');
        if ((!input.trim() && !hasAttachment) || isLoading) return;
        if (!userId) return;
        if (uploadStatus === 'uploading') return;

        const messageText = input.trim() || 'Please summarize the attached file.';
        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content: messageText,
            timestamp: new Date(),
        };

        if (hasAttachment) {
            const attachmentMessage: Message = {
                id: `${Date.now()}-file`,
                role: 'user',
                content: `📎 Attached file: ${selectedFile?.name}`,
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, attachmentMessage, userMessage]);
            resetUpload();
        } else {
            setMessages(prev => [...prev, userMessage]);
        }
        setInput('');
        setIsLoading(true);
        cancelRequestedRef.current = false;
        abortControllerRef.current = new AbortController();

        try {
            const response = await fetch(`${API_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                signal: abortControllerRef.current.signal,
                body: JSON.stringify({
                    message: messageText,
                    session_id: sessionId || undefined,
                    user_id: userId,
                    file_id: hasAttachment ? uploadedFileId : undefined,
                }),
            });

            if (!response.ok) {
                throw new Error('Failed to send message');
            }

            if (response.status === 202) {
                const queued = await response.json();
                setAsyncStatus('Queued… (5%)');
                setActiveJobId(queued.job_id);
                if (!sessionId) {
                    setSessionId(queued.session_id);
                }
                localStorage.setItem(lastSessionKey(userId), queued.session_id);
                const job = await pollJob(queued.job_id, userId, (queued.retry_after || 2) * 1000);
                setActiveJobId(null);
                if (job.status === 'canceled') {
                    setAsyncStatus(null);
                    return;
                }
                const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: job.response || 'No response returned.',
                    timestamp: new Date(),
                };
                setMessages(prev => [...prev, assistantMessage]);
                setAsyncStatus(null);
            } else {
                const payload = await response.json();
                if (!sessionId) {
                    setSessionId(payload.session_id);
                }
                localStorage.setItem(lastSessionKey(userId), payload.session_id);
                const assistantMessage: Message = {
                    id: (Date.now() + 1).toString(),
                    role: 'assistant',
                    content: payload.response,
                    timestamp: new Date(),
                };
                setMessages(prev => [...prev, assistantMessage]);
            }
            loadHistory(userId, false);
            loadQuota(userId, { silent: true });
            // Memory extraction is async; do silent refreshes to catch it without UI lag.
            loadMemory(userId, { silent: true });
            setTimeout(() => {
                loadMemory(userId, { silent: true });
            }, 2500);
            setTimeout(() => {
                loadMemory(userId, { silent: true });
            }, 6000);
        } catch (error) {
            if (error instanceof DOMException && error.name === 'AbortError') {
                setAsyncStatus(null);
                return;
            }
            if (error instanceof Error && error.message === 'canceled') {
                setAsyncStatus(null);
                return;
            }
            console.error('Error:', error);
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: 'Sorry, I encountered an error. Please try again.',
                timestamp: new Date(),
            };
            setMessages(prev => [...prev, errorMessage]);
        } finally {
            setAsyncStatus(null);
            setIsLoading(false);
            abortControllerRef.current = null;
            // Refocus the input after message is sent
            setTimeout(() => {
                inputRef.current?.focus();
            }, 100);
        }
    };

    const handleKeyPress = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };

    const updateInputScrollbar = useCallback(() => {
        const el = inputRef.current;
        if (!el) return;
        const scrollHeight = el.scrollHeight;
        const clientHeight = el.clientHeight;
        const maxHeight = 160;
        const trackPadding = 6;
        const trackHeight = Math.max(0, clientHeight - trackPadding * 2);
        if (scrollHeight <= maxHeight + 1) {
            setInputScrollbar({ visible: false, top: 0, height: 0 });
            return;
        }
        const thumbHeight = Math.max(24, trackHeight * (clientHeight / scrollHeight));
        const maxThumbTop = Math.max(0, trackHeight - thumbHeight);
        const maxScrollTop = Math.max(1, scrollHeight - clientHeight);
        const thumbTop = trackPadding + (el.scrollTop / maxScrollTop) * maxThumbTop;
        setInputScrollbar({ visible: true, top: thumbTop, height: thumbHeight });
    }, []);

    const scheduleInputScrollbarUpdate = useCallback(() => {
        if (inputScrollbarRaf.current) {
            cancelAnimationFrame(inputScrollbarRaf.current);
        }
        inputScrollbarRaf.current = requestAnimationFrame(updateInputScrollbar);
    }, [updateInputScrollbar]);

    const adjustInputHeight = useCallback(() => {
        const el = inputRef.current;
        if (!el) return;
        const start = el.selectionStart ?? 0;
        const end = el.selectionEnd ?? start;
        el.style.height = 'auto';
        const maxHeight = 160;
        const nextHeight = Math.min(el.scrollHeight, maxHeight);
        el.style.height = `${nextHeight}px`;
        el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
        scheduleInputScrollbarUpdate();
        try {
            el.setSelectionRange(start, end);
        } catch {
            // no-op for unsupported cases
        }
    }, [scheduleInputScrollbarUpdate]);

    useEffect(() => {
        adjustInputHeight();
    }, [input, adjustInputHeight]);

    const handleNewChat = () => {
        setMessages([]);
        setSessionId('');
        if (userId) {
            localStorage.removeItem(lastSessionKey(userId));
        }
        setIsHistoryOpen(false);
    };

    const handleRefreshHistory = () => {
        if (!userId) return;
        loadHistory(userId, false);
        loadMemory(userId);
    };

    const approveCandidate = async (candidateId: string) => {
        if (!userId) return;
        setMemoryError(null);
        setMemoryAction({ id: candidateId, action: 'approve' });
        try {
            const res = await fetch(
                `${API_URL}/memory/candidates/${candidateId}/approve?user_id=${encodeURIComponent(userId)}`,
                { method: 'POST' }
            );
            if (!res.ok) {
                let detail = 'Unable to approve memory.';
                try {
                    const data = await res.json();
                    if (data?.detail?.message) {
                        detail = data.detail.message;
                        if (data.detail.reason) {
                            detail += ` (${data.detail.reason})`;
                        }
                    } else if (data?.detail) {
                        detail = typeof data.detail === 'string' ? data.detail : detail;
                    }
                } catch {
                    // ignore parsing error
                }
                setMemoryError(detail);
                return;
            }
            loadMemory(userId);
        } catch (error) {
            console.error('Error approving memory:', error);
            setMemoryError('Unable to approve memory. Please try again.');
        } finally {
            setMemoryAction(null);
        }
    };

    const rejectCandidate = async (candidateId: string) => {
        if (!userId) return;
        setMemoryError(null);
        setMemoryAction({ id: candidateId, action: 'reject' });
        try {
            await fetch(
                `${API_URL}/memory/candidates/${candidateId}/reject?user_id=${encodeURIComponent(userId)}`,
                { method: 'POST' }
            );
            loadMemory(userId);
        } catch (error) {
            console.error('Error rejecting memory:', error);
        } finally {
            setMemoryAction(null);
        }
    };

    const deleteApprovedMemory = async (memoryId: string) => {
        if (!userId) return;
        setMemoryError(null);
        setMemoryAction({ id: memoryId, action: 'remove' });
        try {
            await fetch(
                `${API_URL}/memory/approved/${memoryId}/delete?user_id=${encodeURIComponent(userId)}`,
                { method: 'POST' }
            );
            loadMemory(userId);
        } catch (error) {
            console.error('Error deleting approved memory:', error);
            setMemoryError('Unable to remove approved memory. Please try again.');
        } finally {
            setMemoryAction(null);
        }
    };

    const clearMemoryCandidates = async () => {
        if (!userId || isClearingMemory) return;
        setMemoryError(null);
        setIsClearingMemory(true);
        try {
            const res = await fetch(
                `${API_URL}/memory/candidates/clear?user_id=${encodeURIComponent(userId)}`,
                { method: 'POST' }
            );
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Unable to clear memory candidates.');
            }
            loadMemory(userId);
        } catch (error) {
            console.error('Error clearing memory candidates:', error);
            setMemoryError('Unable to clear memory candidates. Please try again.');
        } finally {
            setIsClearingMemory(false);
        }
    };

    useEffect(() => {
        const stored = localStorage.getItem('sync_code');
        let code = stored;
        if (!code || !isValidSyncCode(code)) {
            code = generateSyncCode();
            localStorage.setItem('sync_code', code);
        }
        setUserId(code);
    }, []);

    useEffect(() => {
        if (!userId || bootstrapDoneRef.current) return;
        bootstrapDoneRef.current = true;
        const bootstrap = async () => {
            setIsBootstrapping(true);
            await Promise.allSettled([
                loadHistory(userId, true),
                loadMemory(userId),
                loadQuota(userId),
            ]);
            setIsBootstrapping(false);
        };
        void bootstrap();
    }, [userId, loadHistory, loadMemory, loadQuota]);

    useEffect(() => {
        if (!isHistoryOpen || !userId) return;
        loadHistory(userId, false);
        loadMemory(userId);
    }, [isHistoryOpen, userId, loadHistory, loadMemory]);

    useEffect(() => {
        if (!userId) return;
        const timer = window.setInterval(() => {
            loadQuota(userId, { silent: true });
        }, 30000);
        return () => window.clearInterval(timer);
    }, [userId, loadQuota]);

    useEffect(() => {
        const updateViewport = () => {
            const width = window.innerWidth;
            const height = Math.round(window.visualViewport?.height ?? window.innerHeight);
            setViewport({ width, height });
        };
        updateViewport();
        window.addEventListener('resize', updateViewport);
        window.visualViewport?.addEventListener('resize', updateViewport);
        return () => {
            window.removeEventListener('resize', updateViewport);
            window.visualViewport?.removeEventListener('resize', updateViewport);
        };
    }, []);

    const isMobileViewport = viewport.width > 0 && viewport.width < 640;
    const isTabletViewport = viewport.width >= 640 && viewport.width < 1024;
    const COLLAPSED_HEIGHT = isMobileViewport ? 560 : isTabletViewport ? 620 : 640;
    const MAX_HEIGHT = 9999;
    const MAX_EXPAND_STEPS = 1;
    const panelHeight = Math.round(
        COLLAPSED_HEIGHT + ((MAX_HEIGHT - COLLAPSED_HEIGHT) * expandStep) / MAX_EXPAND_STEPS
    );
    const viewportCap = viewport.height > 0
        ? Math.max(360, viewport.height - (isMobileViewport ? 24 : 48))
        : 0;
    const resolvedMaxHeight = viewportCap > 0 ? Math.min(MAX_HEIGHT, viewportCap) : MAX_HEIGHT;
    const resolvedPanelHeight = Math.min(panelHeight, resolvedMaxHeight);
    return (
        <div
            className="absolute left-0 right-0 rounded-[22px] bg-gradient-to-br from-white/70 via-white/30 to-slate-200/50 p-[1px] shadow-[0_18px_45px_-30px_rgba(15,23,42,0.55)] transition-[height] duration-300 ease-out sm:rounded-[28px]"
            style={{
                bottom: 'max(0.5rem, env(safe-area-inset-bottom))',
                height: viewport.height > 0 ? `${resolvedPanelHeight}px` : `min(${panelHeight}px, calc(100vh - 64px))`,
                maxHeight: viewport.height > 0 ? `${resolvedMaxHeight}px` : `min(${MAX_HEIGHT}px, calc(100vh - 64px))`,
            }}
        >
            <div className="flex h-full flex-col overflow-visible rounded-[20px] border border-white/50 bg-white/80 backdrop-blur sm:rounded-[26px]">
            {/* Header */}
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-x-3 gap-y-1 rounded-t-[20px] bg-gradient-to-r from-[#0f3b3e] via-[#1b4a66] to-[#1f2a44] p-3 text-white sm:gap-x-4 sm:gap-y-2 sm:rounded-t-[26px] sm:p-5 lg:flex lg:items-start lg:justify-between">
                <div className="min-w-0 flex items-start gap-[clamp(0.35rem,1.8vw,1rem)]">
                    <div className="relative">
                        <div className="absolute -inset-1 rounded-full bg-gradient-to-br from-amber-200/50 via-slate-200/30 to-sky-300/40 blur-[8px]" />
                        <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-white/40 via-transparent to-white/10 opacity-70" />
                        <div className="relative h-[clamp(2rem,8vw,2.5rem)] w-[clamp(2rem,8vw,2.5rem)] rounded-full bg-slate-900/60 p-[2px] shadow-[0_10px_22px_rgba(15,23,42,0.45)] sm:h-12 sm:w-12">
                            <div className="relative w-full h-full rounded-full bg-slate-900/60 border border-white/25 overflow-hidden flex items-center justify-center">
                                <span className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/20 via-transparent to-transparent" />
                                <span className="pointer-events-none absolute -right-3 -top-3 h-8 w-8 rounded-full bg-white/10" />
                                {hasAvatar ? (
                                    <img
                                        src="/avatar.jpg"
                                        alt="Digital Assistant Avatar"
                                        className="w-full h-full object-cover"
                                    />
                                ) : (
                                    <Bot className="h-[clamp(0.9rem,3.8vw,1.25rem)] w-[clamp(0.9rem,3.8vw,1.25rem)] text-white sm:h-6 sm:w-6" />
                                )}
                            </div>
                        </div>
                        <span className="absolute -right-1 -bottom-1 h-3 w-3 rounded-full bg-emerald-400 border-2 border-[#123243] shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
                    </div>
                    <div className="min-w-0">
                        <p className="text-xs uppercase tracking-[0.3em] text-white/70">Agent</p>
                        <div className="flex items-center gap-2 lg:flex-wrap">
                            <h2 className="font-display whitespace-nowrap font-semibold leading-tight text-[clamp(1rem,4.5vw,1.35rem)] sm:text-2xl">
                                Digital Assistant
                            </h2>
                            <span className="group relative hidden items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] text-white/85 lg:inline-flex">
                                <Terminal className="h-3 w-3 text-sky-200" />
                                Deployment Mentor
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Hands-on guidance for deploying LLM systems, infra, and tooling.
                                </span>
                            </span>
                            <span className="group relative hidden items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] text-white/85 lg:inline-flex">
                                <LifeBuoy className="h-3 w-3 text-amber-200" />
                                Live Troubleshooting
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Real-time troubleshooting, root-cause analysis, and incident response.
                                </span>
                            </span>
                            <span className="group relative hidden items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] text-white/85 lg:inline-flex">
                                <Search className="h-3 w-3 text-cyan-200" />
                                Researcher
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Investigates sources, synthesizes evidence, and validates claims.
                                </span>
                            </span>
                        </div>
                        <div className="mt-2 hidden min-w-0 flex-wrap items-center gap-1 overflow-visible lg:flex">
                            <span className="shrink-0 text-[9px] uppercase tracking-[0.18em] text-white/60">
                                Tools
                            </span>
                            <span className="group relative inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] leading-none text-white/85">
                                <Brain className="h-3 w-3 text-emerald-200" />
                                Memory
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Remembers approved preferences and project context to personalize future replies.
                                </span>
                            </span>
                            <span className="group relative inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] leading-none text-white/85">
                                <FileDown className="h-3 w-3 text-indigo-200" />
                                PDF
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Export chat outputs or summaries as downloadable PDFs.
                                </span>
                            </span>
                            <span className="group relative inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] leading-none text-white/85">
                                <Paperclip className="h-3 w-3 text-slate-200" />
                                Upload
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Upload PDFs, DOCX, or text files for summarization and analysis.
                                </span>
                            </span>
                            <span className="group relative inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] leading-none text-white/85">
                                <Mail className="h-3 w-3 text-rose-200" />
                                Email
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Send PDFs or summaries to your email on request.
                                </span>
                            </span>
                            <span className="group relative inline-flex shrink-0 items-center gap-1 rounded-full border border-white/15 bg-white/10 px-1.5 py-0.5 text-[9px] leading-none text-white/85">
                                <Search className="h-3 w-3 text-cyan-200" />
                                Search
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-30 w-[240px] whitespace-normal -translate-x-1/2 rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                    <span className="absolute left-1/2 top-0 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Uses Brave to fetch current information with citations when needed.
                                </span>
                            </span>
                        </div>
                    </div>
                </div>
                <div className="contents lg:mt-1 lg:flex lg:w-auto lg:flex-col lg:items-end lg:gap-1">
                    <div className="flex flex-nowrap items-center justify-center gap-[clamp(0.2rem,1vw,0.45rem)] overflow-visible rounded-2xl border border-white/10 bg-white/5 px-[clamp(0.3rem,1.2vw,0.45rem)] py-[clamp(0.2rem,0.8vw,0.32rem)] shadow-[0_6px_18px_-12px_rgba(15,23,42,0.5)] justify-self-center sm:justify-self-end sm:gap-2 sm:px-2 sm:py-1 lg:justify-self-auto lg:justify-end">
                        {memoryCandidates.length > 0 && (
                            <div className="group relative">
                                <button
                                    onClick={() => {
                                        setIsHistoryOpen(true);
                                        setHistoryTab('memory');
                                        if (userId) {
                                            loadHistory(userId, false);
                                            loadMemory(userId);
                                        }
                                    }}
                                    className="inline-flex h-[clamp(1.7rem,8vw,2.2rem)] items-center gap-1 rounded-xl border border-rose-300/40 bg-rose-500/90 px-[clamp(0.35rem,1.4vw,0.45rem)] py-[clamp(0.25rem,0.9vw,0.4rem)] text-[clamp(0.6rem,2.2vw,0.66rem)] text-white shadow-[0_4px_14px_rgba(244,63,94,0.4)] transition-all duration-200 ease-out hover:bg-rose-500 active:scale-95 sm:min-h-10 sm:p-2 sm:text-[11px]"
                                    aria-label="Review memory"
                                >
                                    <Brain className="h-[clamp(0.8rem,3vw,0.95rem)] w-[clamp(0.8rem,3vw,0.95rem)] drop-shadow-sm sm:h-4 sm:w-4" />
                                    {memoryCandidates.length}
                                </button>
                                <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-max max-w-[180px] whitespace-nowrap rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2 text-[10px] leading-none text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
                                    <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                    Review memory
                                </span>
                            </div>
                        )}
                        <div className="group relative">
                            <button
                                onClick={handleNewChat}
                                className="inline-flex h-[clamp(1.7rem,8vw,2.2rem)] w-[clamp(1.7rem,8vw,2.2rem)] items-center justify-center rounded-xl border border-white/15 bg-white/10 p-[clamp(0.28rem,1.3vw,0.45rem)] shadow-[0_3px_10px_rgba(15,23,42,0.25)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:bg-white/20 active:scale-95 sm:min-h-10 sm:min-w-10 sm:p-2"
                                aria-label="New chat"
                            >
                                <MessageSquarePlus className="h-[clamp(0.82rem,3.4vw,1.1rem)] w-[clamp(0.82rem,3.4vw,1.1rem)] drop-shadow-sm sm:h-5 sm:w-5" />
                            </button>
                            <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-max max-w-[160px] whitespace-nowrap rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2 text-[10px] leading-none text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
                                <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                New chat
                            </span>
                        </div>
                        <div className="group relative">
                            <button
                                onClick={() => {
                                    setExpandStep(prev => (prev < MAX_EXPAND_STEPS ? prev + 1 : 0));
                                }}
                                className="inline-flex h-[clamp(1.7rem,8vw,2.2rem)] w-[clamp(1.7rem,8vw,2.2rem)] items-center justify-center rounded-xl border border-white/15 bg-white/10 p-[clamp(0.28rem,1.3vw,0.45rem)] shadow-[0_3px_10px_rgba(15,23,42,0.25)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:bg-white/20 active:scale-95 sm:min-h-10 sm:min-w-10 sm:p-2"
                                aria-label={expandStep >= MAX_EXPAND_STEPS ? 'Collapse' : 'Expand'}
                            >
                                <Maximize2 className="h-[clamp(0.82rem,3.4vw,1.1rem)] w-[clamp(0.82rem,3.4vw,1.1rem)] drop-shadow-sm sm:h-5 sm:w-5" />
                            </button>
                            <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-max max-w-[160px] whitespace-nowrap rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2 text-[10px] leading-none text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
                                <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                {expandStep >= MAX_EXPAND_STEPS ? 'Collapse' : 'Expand'}
                            </span>
                        </div>
                        <div className="group relative">
                            <button
                                onClick={() => {
                                    setIsHistoryOpen(true);
                                    setHistoryTab('history');
                                    if (userId) {
                                        loadHistory(userId, false);
                                    }
                                }}
                                className="inline-flex h-[clamp(1.7rem,8vw,2.2rem)] w-[clamp(1.7rem,8vw,2.2rem)] items-center justify-center rounded-xl border border-white/15 bg-white/10 p-[clamp(0.28rem,1.3vw,0.45rem)] shadow-[0_3px_10px_rgba(15,23,42,0.25)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:bg-white/20 active:scale-95 sm:min-h-10 sm:min-w-10 sm:p-2"
                                aria-label="History"
                            >
                                <History className="h-[clamp(0.82rem,3.4vw,1.1rem)] w-[clamp(0.82rem,3.4vw,1.1rem)] drop-shadow-sm sm:h-5 sm:w-5" />
                            </button>
                            <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-max max-w-[160px] whitespace-nowrap rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2 text-[10px] leading-none text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100 group-focus-within:opacity-100">
                                <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                Chat history
                            </span>
                        </div>
                    </div>
                    <div className="col-span-2 mt-1 flex flex-wrap items-center gap-1.5 pr-1 lg:hidden">
                        <span className="group relative inline-flex items-center text-[9px] uppercase tracking-[0.18em] text-white/60">
                            Daily Quota
                            <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-[220px] whitespace-normal rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] normal-case tracking-normal leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                {isLoadingQuota
                                    ? 'Refreshing quota...'
                                    : quota?.reset_at
                                        ? `Resets at ${new Date(quota.reset_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`
                                        : 'Quota reset info unavailable'}
                            </span>
                        </span>
                        {quotaItems.map((item) => {
                            const usage = quota?.usage?.[item.key] ?? 0;
                            const limit = quota?.limits?.[item.key] ?? 0;
                            return (
                                <span
                                    key={item.key}
                                    className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] leading-none ${item.tone}`}
                                >
                                    <span>{item.label}</span>
                                    <span className="text-white/90">
                                        {formatCount(usage)}/{formatCount(limit)}
                                    </span>
                                </span>
                            );
                        })}
                    </div>
                    <div className="mt-1 hidden flex-wrap items-center gap-1.5 pr-1 lg:flex lg:justify-end">
                        <span className="group relative inline-flex items-center text-[9px] uppercase tracking-[0.18em] text-white/60">
                            Daily Quota
                            <span className="pointer-events-none absolute right-0 top-[calc(100%+8px)] z-30 w-[220px] whitespace-normal rounded-xl border border-white/20 bg-gradient-to-br from-slate-900/98 to-slate-800/98 px-3 py-2.5 text-[10px] normal-case tracking-normal leading-relaxed text-white/90 opacity-0 shadow-[0_12px_30px_-18px_rgba(2,8,23,0.95)] transition-opacity duration-200 group-hover:opacity-100">
                                <span className="absolute right-3 top-0 h-2.5 w-2.5 -translate-y-1/2 rotate-45 border-l border-t border-white/20 bg-slate-900" />
                                {isLoadingQuota
                                    ? 'Refreshing quota...'
                                    : quota?.reset_at
                                        ? `Resets at ${new Date(quota.reset_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`
                                        : 'Quota reset info unavailable'}
                            </span>
                        </span>
                        {quotaItems.map((item) => {
                            const usage = quota?.usage?.[item.key] ?? 0;
                            const limit = quota?.limits?.[item.key] ?? 0;
                            return (
                                <span
                                    key={`desktop-${item.key}`}
                                    className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[9px] leading-none ${item.tone}`}
                                >
                                    <span>{item.label}</span>
                                    <span className="text-white/90">
                                        {formatCount(usage)}/{formatCount(limit)}
                                    </span>
                                </span>
                            );
                        })}
                    </div>
                </div>
            </div>

            <div
                className={`absolute inset-0 z-10 transition-opacity duration-200 ${
                    isHistoryOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
                }`}
                aria-hidden={!isHistoryOpen}
            >
                <div
                    className="absolute inset-0 bg-transparent"
                    onClick={() => setIsHistoryOpen(false)}
                />
                <div
                    className={`absolute left-0 top-0 h-full w-[min(20rem,92vw)] bg-gradient-to-br from-[#0f3b3e]/96 via-[#1b4a66]/96 to-[#1f2a44]/96 border border-white/10 shadow-[0_20px_45px_-28px_rgba(2,8,23,0.7)] p-4 flex flex-col transform transition-transform duration-200 text-white sm:w-80 ${
                        isHistoryOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
                >
                        <div className="flex items-center justify-between mb-2">
                            <p className="text-[11px] text-white/65 uppercase tracking-[0.2em]">Workspace</p>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleRefreshHistory}
                                    className="min-h-10 min-w-10 rounded p-2 transition-all duration-200 ease-out hover:bg-white/15 active:scale-95"
                                    title="Refresh"
                                    disabled={isLoadingHistory || isLoadingMemory}
                                >
                                    <RefreshCw className={`w-4 h-4 text-white/80 ${(isLoadingHistory || isLoadingMemory) ? 'animate-spin' : ''}`} />
                                </button>
                                <button
                                    onClick={() => setIsHistoryOpen(false)}
                                    className="min-h-10 min-w-10 rounded p-2 transition-all duration-200 ease-out hover:bg-white/15 active:scale-95"
                                    title="Close"
                                >
                                    <X className="w-5 h-5 text-white/80" />
                                </button>
                            </div>
                        </div>
                        <div className="flex items-center gap-2 mb-3">
                            <button
                                onClick={() => setHistoryTab('history')}
                                className={`flex-1 inline-flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-200 ease-out h-9 ${
                                    historyTab === 'history'
                                        ? 'bg-white/20 text-white shadow-[0_6px_18px_-12px_rgba(15,23,42,0.6)]'
                                        : 'bg-white/10 text-white/70 hover:bg-white/20'
                                }`}
                            >
                                <span className="inline-flex items-center gap-2">
                                    <History className="h-3.5 w-3.5" />
                                    Chat History
                                </span>
                                {/* <span className="text-[10px] text-white/50">0 recent</span> */}
                            </button>
                            <button
                                onClick={() => setHistoryTab('memory')}
                                className={`flex-1 inline-flex items-center justify-between px-3 py-2 rounded-xl text-xs font-semibold transition-all duration-200 ease-out h-9 ${
                                    historyTab === 'memory'
                                        ? 'bg-white/20 text-white shadow-[0_6px_18px_-12px_rgba(15,23,42,0.6)]'
                                        : 'bg-white/10 text-white/70 hover:bg-white/20'
                                }`}
                            >
                                <span className="inline-flex items-center gap-2">
                                    <Brain className="h-3.5 w-3.5 text-emerald-200" />
                                    Memory
                                </span>
                                {memoryCandidates.length > 0 ? (
                                    <span className="inline-flex items-center justify-center rounded-full bg-rose-400/90 text-white text-[10px] px-1.5">
                                        {memoryCandidates.length}
                                    </span>
                                ) : (
                                    <span className="text-[10px] text-white/50">None</span>
                                )}
                            </button>
                        </div>
                        <p className="text-[11px] text-white/60 mb-4">
                            {historyTab === 'history'
                                ? 'History shows your 5 most recent conversations.'
                                : 'Review memory candidates before approval.'}
                        </p>

                        <div className="memory-panel-scroll flex-1 overflow-y-auto space-y-3 transition-opacity duration-300 ease-out">
                            {historyTab === 'history' && (
                                <>
                                    {isLoadingHistory && (
                                        <p className="text-sm text-white/70">Loading history…</p>
                                    )}
                                    {!isLoadingHistory && sessions.length === 0 && (
                                        <p className="text-sm text-white/70">No conversations yet.</p>
                                    )}
                                    {sessions.map((session) => (
                                        <button
                                            key={session.session_id}
                                            onClick={() => {
                                                loadConversation(userId, session.session_id);
                                                setIsHistoryOpen(false);
                                            }}
                                            className={`w-full text-left p-3 rounded-xl border transition-all duration-300 ease-out active:scale-[0.99] hover:-translate-y-0.5 hover:shadow-md ${
                                                session.session_id === sessionId
                                                    ? 'border-white/40 bg-white/20 shadow-[0_6px_18px_-12px_rgba(15,23,42,0.6)]'
                                                    : 'border-white/15 bg-white/10 hover:bg-white/20'
                                            }`}
                                        >
                                            <p className="text-[13px] font-semibold text-white truncate">
                                                {session.title}
                                            </p>
                                            <p className="text-[10px] text-white/60 mt-1">
                                                {new Date(session.updated_at).toLocaleString()}
                                            </p>
                                        </button>
                                    ))}
                                </>
                            )}

                            {historyTab === 'memory' && (
                                <>
                                    <div className="rounded-xl border border-white/15 bg-white/10 px-3 py-2 text-[10px] text-white/75 leading-relaxed">
                                        <button
                                            type="button"
                                            onClick={() => setIsMemoryInfoOpen(prev => !prev)}
                                            className="relative w-full h-9 pr-10 flex items-center text-left leading-none"
                                        >
                                            <span className="font-semibold text-white/90 text-[11px]">What Memory Does</span>
                                            <span className="absolute right-0 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full bg-white/10 text-white/70 grid place-items-center">
                                                {isMemoryInfoOpen ? (
                                                    <Minus className="h-3 w-3" />
                                                ) : (
                                                    <Plus className="h-3 w-3" />
                                                )}
                                            </span>
                                        </button>
                                        {isMemoryInfoOpen && (
                                            <ul className="list-disc pl-4 space-y-1 mt-2">
                                                <li>Stores long‑term preferences (format, tone, defaults) you approve.</li>
                                                <li>Feeds approved items into the assistant’s system prompt for future replies.</li>
                                                <li>Pending items are suggestions only — nothing is stored until you approve.</li>
                                                <li>Items expire by TTL, so temporary context won’t stick forever.</li>
                                                <li className="pt-1 text-white/70">
                                                    Example phrases:
                                                    <span className="block mt-1 text-white/75">
                                                        “From now on, always include a download link when you email a PDF.”
                                                    </span>
                                                    <span className="block text-white/75">
                                                        “Always answer in strict JSON.”
                                                    </span>
                                                    <span className="block text-white/75">
                                                        “Remember my preferred tools and defaults for this project.”
                                                    </span>
                                                </li>
                                            </ul>
                                        )}
                                    </div>
                                    {memoryError && (
                                        <div className="rounded-lg border border-rose-300/40 bg-rose-500/15 px-3 py-2 text-xs text-rose-100">
                                            {memoryError}
                                        </div>
                                    )}
                                    {memoryCandidates.length > 0 && (
                                        <button
                                            type="button"
                                            onClick={clearMemoryCandidates}
                                            disabled={isClearingMemory}
                                            className="w-full px-3 py-2 text-xs font-semibold rounded-full border border-rose-300/50 bg-rose-500/25 text-rose-100 hover:bg-rose-500/35 disabled:opacity-60 disabled:cursor-not-allowed"
                                        >
                                            {isClearingMemory ? 'Clearing…' : 'Clear All Pending'}
                                        </button>
                                    )}
                                    {isLoadingMemory && (
                                        <p className="text-sm text-white/70">Loading memory…</p>
                                    )}
                                    <div className="pt-2 border-t border-white/10">
                                        <button
                                            type="button"
                                            onClick={() => setIsApprovedMemoryOpen(prev => !prev)}
                                            className="relative w-full h-9 pr-10 flex items-center text-left text-xs font-semibold text-white/85 mb-2 leading-none"
                                        >
                                            <span className="inline-flex items-center gap-2">
                                                Approved Memory
                                                <span className="rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-semibold text-white/70">
                                                    {memoryApproved.length}
                                                </span>
                                            </span>
                                            <span className="absolute right-3 top-1/2 -translate-y-1/2 h-5 w-5 rounded-full bg-white/10 text-white/70 grid place-items-center">
                                                {isApprovedMemoryOpen ? (
                                                    <Minus className="h-3 w-3" />
                                                ) : (
                                                    <Plus className="h-3 w-3" />
                                                )}
                                            </span>
                                        </button>
                                        {isApprovedMemoryOpen && (
                                            <>
                                                {memoryApproved.length === 0 && (
                                                    <p className="text-[11px] text-white/60">No approved memory yet.</p>
                                                )}
                                                {memoryApproved.map((mem) => (
                                                    <div
                                                        key={mem.id}
                                                        className="rounded-lg border border-white/12 bg-white/10 px-2 py-1.5 mb-2 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-sm"
                                                    >
                                                        <p className="text-xs text-white/90">{mem.text}</p>
                                                        <p className="text-[10px] text-white/60 mt-0.5">
                                                            {mem.category}
                                                            {mem.expires_at
                                                                ? ` • Expires ${new Date(mem.expires_at).toLocaleDateString()}`
                                                                : ''}
                                                        </p>
                                                        <div className="mt-1">
                                                            <button
                                                                onClick={() => deleteApprovedMemory(mem.id)}
                                                                disabled={memoryAction?.id === mem.id && memoryAction.action === 'remove'}
                                                                className="px-2 py-0.5 text-[11px] rounded-full bg-white/15 text-white/80 hover:bg-white/25 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
                                                            >
                                                                {memoryAction?.id === mem.id && memoryAction.action === 'remove' ? (
                                                                    <span className="inline-flex h-2.5 w-2.5 animate-spin rounded-full border-2 border-white/50 border-t-white" />
                                                                ) : null}
                                                                Remove
                                                            </button>
                                                        </div>
                                                    </div>
                                                ))}
                                            </>
                                        )}
                                    </div>

                                    {!isLoadingMemory && memoryCandidates.length === 0 && (
                                        <p className="text-[11px] text-white/60 mt-2">No pending memories.</p>
                                    )}
                                    {memoryCandidates.map((cand) => (
                                        <div
                                            key={cand.id}
                                            className="rounded-lg border border-white/15 bg-white/10 px-2 py-1.5 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-sm"
                                        >
                                            <p className="text-xs font-medium text-white/90">{cand.text}</p>
                                            <p className="text-[10px] text-white/60 mt-0.5">
                                                {cand.category} • TTL {cand.ttl_days}d
                                            </p>
                                            <div className="mt-1 flex gap-2">
                                                <button
                                                    onClick={() => approveCandidate(cand.id)}
                                                    disabled={memoryAction?.id === cand.id && memoryAction.action === 'approve'}
                                                    className="px-2 py-0.5 text-[11px] rounded-full bg-emerald-500/90 text-white hover:bg-emerald-500 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
                                                >
                                                    {memoryAction?.id === cand.id && memoryAction.action === 'approve' ? (
                                                        <span className="inline-flex h-2.5 w-2.5 animate-spin rounded-full border-2 border-white/60 border-t-white" />
                                                    ) : null}
                                                    Approve
                                                </button>
                                                <button
                                                    onClick={() => rejectCandidate(cand.id)}
                                                    disabled={memoryAction?.id === cand.id && memoryAction.action === 'reject'}
                                                    className="px-2 py-0.5 text-[11px] rounded-full bg-white/15 text-white/80 hover:bg-white/25 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
                                                >
                                                    {memoryAction?.id === cand.id && memoryAction.action === 'reject' ? (
                                                        <span className="inline-flex h-2.5 w-2.5 animate-spin rounded-full border-2 border-white/50 border-t-white" />
                                                    ) : null}
                                                    Reject
                                                </button>
                                            </div>
                                        </div>
                                    ))}
                                </>
                            )}
                        </div>
                    </div>
            </div>

            <div className="flex-1 flex flex-col overflow-hidden rounded-b-[20px] sm:rounded-b-[26px]">
            {/* Messages */}
            <div className="flex-1 space-y-3 overflow-y-auto bg-[radial-gradient(circle_at_top,_#ffffff,_#f1f5f9_55%,_#e7edf6_100%)] p-3 sm:space-y-5 sm:p-5">
                {showInitialLoader ? (
                    <div className="mx-auto mt-4 w-full max-w-2xl rounded-[24px] bg-gradient-to-r from-[#0f3b3e] via-[#1b4a66] to-[#1f2a44] p-[1px] shadow-[0_16px_36px_-20px_rgba(15,23,42,0.65)] sm:mt-8">
                        <div className="startup-loader-shimmer rounded-[23px] border border-white/10 bg-gradient-to-r from-[#0f3b3e]/95 via-[#1b4a66]/95 to-[#1f2a44]/95 p-3 text-white sm:p-5">
                            <div className="mb-3 flex items-center gap-3">
                                <div className="h-8 w-8 flex-shrink-0 sm:h-10 sm:w-10">
                                    {renderPremiumAvatar('w-10 h-10', 'w-5 h-5', false)}
                                </div>
                                <div className="min-w-0 flex-1">
                                    <p className="text-[13px] font-semibold sm:text-sm">Loading your workspace…</p>
                                    <p className="text-[11px] text-white/75 sm:text-xs">Warming up serverless runtime (usually 1-5 seconds).</p>
                                </div>
                                <div className="h-6 w-6 animate-spin rounded-full border-2 border-white/25 border-t-white sm:h-7 sm:w-7" />
                            </div>

                            <div className="mb-3 flex flex-wrap items-center gap-1.5">
                                <span className="text-[10px] uppercase tracking-[0.18em] text-white/65">Tools</span>
                                <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">Memory</span>
                                <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">PDF</span>
                                <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">Upload</span>
                                <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">Email</span>
                                <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] text-white/85">Search</span>
                            </div>

                            <div className="space-y-2.5">
                                <div className="h-2.5 w-full animate-pulse rounded bg-white/20" />
                                <div className="h-2.5 w-5/6 animate-pulse rounded bg-white/20" />
                                <div className="h-2.5 w-2/3 animate-pulse rounded bg-white/20" />
                            </div>
                        </div>
                    </div>
                ) : messages.length === 0 && (
                    <div className="text-center text-slate-500 mt-12">
                        <div className="mx-auto mb-4 w-20 h-20">
                            {renderPremiumAvatar('w-20 h-20', 'w-10 h-10', false)}
                        </div>
                        <p className="text-lg text-slate-700 font-medium">Hello! I&apos;m your Digital Assistant.</p>
                        <p className="text-sm mt-2">
                            Ask for research, PDF export, email delivery, or deployment troubleshooting.
                        </p>
                    </div>
                )}

                {renderedMessages}

                {isLoading && !cancelRequestedRef.current && (
                    <div className="flex gap-3 justify-start">
                        <div className="flex-shrink-0">
                            {renderPremiumAvatar('w-9 h-9', 'w-5 h-5', false)}
                        </div>
                        <div className="bg-white/90 border border-white/60 rounded-2xl p-3 shadow-sm">
                            <div className="flex space-x-2">
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
                            </div>
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div
                className="rounded-b-[20px] border-t border-white/60 bg-white/90 p-3 sm:rounded-b-[26px] sm:p-4"
                style={{ paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' }}
            >
                {(displayStatusLabel || showInitialLoader) && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                        <span className="inline-flex h-2 w-2 rounded-full bg-slate-400 animate-pulse" />
                        <span className="flex items-center gap-1">
                            {showInitialLoader ? 'Initializing app state…' : displayStatusLabel}
                        </span>
                    </div>
                )}
                <div className="flex items-end gap-2 sm:gap-3">
                    <div className="relative flex-1">
                        <textarea
                            ref={inputRef}
                            rows={1}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyPress}
                            onScroll={scheduleInputScrollbarUpdate}
                            placeholder={showInitialLoader ? 'Loading…' : 'Ask about deployment, infrastructure, or troubleshooting...'}
                            className="chat-input-scroll min-h-[44px] w-full resize-none overflow-y-auto rounded-2xl border border-slate-200 bg-white py-2.5 pl-3 pr-6 text-sm leading-relaxed text-slate-800 shadow-sm focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-600/40 sm:min-h-[48px] sm:py-3 sm:pl-4 sm:text-base"
                            disabled={isLoading || showInitialLoader}
                            autoFocus
                        />
                        <div className="pointer-events-none absolute right-1 top-2 bottom-2 w-2">
                            <div className="absolute inset-0 rounded-full bg-transparent" />
                            {inputScrollbar.visible && (
                                <div
                                    className="absolute left-0 w-2 rounded-full bg-gradient-to-b from-slate-300 to-slate-500 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.6)]"
                                    style={{ top: inputScrollbar.top, height: inputScrollbar.height }}
                                />
                            )}
                        </div>
                    </div>
                    <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        onChange={handleFileChange}
                        accept=".pdf,.docx,.txt,.md"
                    />
                    <button
                        type="button"
                        onClick={triggerFileSelect}
                        disabled={showInitialLoader}
                        className="group relative self-end rounded-2xl border border-slate-200 bg-white px-3 py-2.5 text-slate-700 shadow-[0_8px_18px_-12px_rgba(15,23,42,0.35)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-600/40 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 min-h-11 min-w-11 sm:px-3.5 sm:py-3"
                        aria-label="Upload file"
                    >
                        <span className="absolute inset-0 rounded-2xl bg-gradient-to-br from-slate-50 via-white to-slate-100 opacity-80" />
                        <span className="absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.35),_transparent_60%)]" />
                        <span className="relative flex items-center justify-center">
                            <Paperclip className="w-5 h-5 drop-shadow-sm" />
                        </span>
                    </button>
                    {isLoading ? (
                        <button
                            onClick={cancelActiveJob}
                            className="group relative self-end rounded-2xl bg-gradient-to-br from-rose-500 via-rose-600 to-rose-500 px-3.5 py-2.5 text-white shadow-[0_10px_24px_-14px_rgba(15,23,42,0.5)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:from-rose-500 hover:via-rose-500 hover:to-rose-600 focus:outline-none focus:ring-2 focus:ring-rose-500/40 active:scale-95 min-h-11 min-w-11 sm:px-4 sm:py-3"
                            aria-label="Cancel request"
                        >
                            <span className="absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_top,_rgba(251,113,133,0.35),_transparent_65%)]" />
                            <span className="relative flex items-center justify-center gap-2">
                                <X className="w-5 h-5 drop-shadow-sm" />
                            </span>
                        </button>
                    ) : (
                        <button
                            onClick={sendMessage}
                            disabled={
                                (!input.trim() && !(selectedFile && uploadedFileId && uploadStatus === 'uploaded')) ||
                                isLoading ||
                                showInitialLoader ||
                                uploadStatus === 'uploading' ||
                                uploadStatus === 'error'
                            }
                            className="group relative self-end rounded-2xl bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 px-3.5 py-2.5 text-white shadow-[0_10px_24px_-14px_rgba(15,23,42,0.5)] transition-all duration-200 ease-out hover:-translate-y-0.5 hover:from-slate-800 hover:via-slate-900 hover:to-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-600/40 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 min-h-11 min-w-11 sm:px-4 sm:py-3"
                        >
                            <span className="absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.35),_transparent_65%)]" />
                            <span className="relative flex items-center justify-center gap-2">
                                <Send className="w-5 h-5 drop-shadow-sm" />
                            </span>
                        </button>
                    )}
                </div>
                {(selectedFile || uploadError) && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                        {selectedFile && (
                            <span className="group relative inline-flex max-w-full items-center gap-2 rounded-full border border-slate-200 bg-slate-100 px-3 py-1">
                                <span className="pointer-events-none absolute left-1/2 -top-2 z-30 hidden w-[260px] -translate-x-1/2 -translate-y-full whitespace-normal rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px] text-slate-700 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 sm:block">
                                    {selectedFile.name}
                                </span>
                                <span className="max-w-[150px] truncate font-medium text-slate-700 sm:max-w-[260px]">{selectedFile.name}</span>
                                {uploadStatus === 'uploading' && <span className="text-slate-500">Uploading…</span>}
                                {uploadStatus === 'uploaded' && <span className="text-emerald-600">Uploaded</span>}
                                {uploadStatus === 'error' && <span className="text-rose-600">Failed</span>}
                                <button
                                    type="button"
                                    onClick={resetUpload}
                                    className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-500 hover:bg-slate-200 hover:text-slate-700"
                                    aria-label="Remove file"
                                >
                                    <X className="h-3.5 w-3.5" />
                                </button>
                            </span>
                        )}
                        {uploadError && <span className="text-rose-600">{uploadError}</span>}
                    </div>
                )}
            </div>
            </div>
            </div>
        </div>
    );
}
