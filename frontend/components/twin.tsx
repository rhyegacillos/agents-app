'use client';

import { useState, useRef, useEffect, type ChangeEvent } from 'react';
import { Send, Bot, User, History, X, RefreshCw, Maximize2, Minimize2, Paperclip, MessageSquarePlus, Brain, Terminal, LifeBuoy, Mail, FileDown, Plus, Minus, Search } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
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

export default function Twin() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [asyncStatus, setAsyncStatus] = useState<string | null>(null);
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
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'uploaded' | 'error'>('idle');
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadedFileId, setUploadedFileId] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLTextAreaElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const isValidSyncCode = (code: string) => /^[a-zA-Z0-9_-]{8,64}$/.test(code);

    const generateSyncCode = () => {
        const bytes = new Uint8Array(8);
        crypto.getRandomValues(bytes);
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    };

    const lastSessionKey = (uid: string) => `last_session_id:${uid}`;
    const displayStatusLabel = asyncStatus;

    const pollJob = async (jobId: string, uid: string, initialDelayMs = 2000) => {
        let delay = initialDelayMs;
        const maxAttempts = 120;
        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            await new Promise(resolve => setTimeout(resolve, delay));
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
            if (job.status === 'failed') {
                setAsyncStatus(null);
                throw new Error(job.error || 'Job failed');
            }
            delay = Math.min(Math.round(delay * 1.4), 8000);
        }
        throw new Error('Job polling timed out');
    };

    const renderPremiumAvatar = (sizeClass: string, iconClass: string, glow = true) => (
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
    );

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    const triggerFileSelect = () => {
        fileInputRef.current?.click();
    };

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
            const formData = new FormData();
            formData.append('file', file);
            const response = await fetch(`${API_URL}/uploads`, {
                method: 'POST',
                body: formData,
            });
            if (!response.ok) {
                throw new Error('Failed to upload file');
            }
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

    const loadConversation = async (uid: string, sid: string) => {
        try {
            const response = await fetch(`${API_URL}/conversation/${sid}?user_id=${encodeURIComponent(uid)}`);
            if (!response.ok) throw new Error('Failed to load conversation');
            const data = await response.json();
            const restored: Message[] = (data.messages || []).map((msg: any, index: number) => ({
                id: `${sid}-${index}`,
                role: msg.role,
                content: msg.content,
                timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date(),
            }));
            setMessages(restored);
            setSessionId(sid);
            localStorage.setItem(lastSessionKey(uid), sid);
        } catch (error) {
            console.error('Error loading conversation:', error);
        }
    };

    const loadHistory = async (uid: string, autoRestore = true) => {
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
    };

    const loadMemory = async (uid: string, opts: { silent?: boolean } = {}) => {
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
    };

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

        try {
            const response = await fetch(`${API_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
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
                if (!sessionId) {
                    setSessionId(queued.session_id);
                }
                localStorage.setItem(lastSessionKey(userId), queued.session_id);
                const job = await pollJob(queued.job_id, userId, (queued.retry_after || 2) * 1000);
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
            // Memory extraction is async; do silent refreshes to catch it without UI lag.
            loadMemory(userId, { silent: true });
            setTimeout(() => {
                loadMemory(userId, { silent: true });
            }, 2500);
            setTimeout(() => {
                loadMemory(userId, { silent: true });
            }, 6000);
        } catch (error) {
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

    const adjustInputHeight = () => {
        const el = inputRef.current;
        if (!el) return;
        const start = el.selectionStart ?? 0;
        const end = el.selectionEnd ?? start;
        el.style.height = 'auto';
        const maxHeight = 160;
        const nextHeight = Math.min(el.scrollHeight, maxHeight);
        el.style.height = `${nextHeight}px`;
        el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden';
        try {
            el.setSelectionRange(start, end);
        } catch {
            // no-op for unsupported cases
        }
    };

    useEffect(() => {
        adjustInputHeight();
    }, [input]);

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

    // Check if avatar exists
    const [hasAvatar, setHasAvatar] = useState(false);
    useEffect(() => {
        // Check if avatar.png exists
        fetch('/avatar.jpg', { method: 'HEAD' })
            .then(res => setHasAvatar(res.ok))
            .catch(() => setHasAvatar(false));
    }, []);

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
        if (!userId) return;
        loadHistory(userId, true);
        loadMemory(userId);
    }, [userId]);

    useEffect(() => {
        if (!isHistoryOpen || !userId) return;
        loadHistory(userId, false);
        loadMemory(userId);
    }, [isHistoryOpen, userId]);

    const COLLAPSED_HEIGHT = 640;
    const MAX_HEIGHT = 9999;
    const MAX_EXPAND_STEPS = 1;
    const panelHeight = Math.round(
        COLLAPSED_HEIGHT + ((MAX_HEIGHT - COLLAPSED_HEIGHT) * expandStep) / MAX_EXPAND_STEPS
    );
    return (
        <div
            className="absolute bottom-0 left-0 right-0 rounded-[28px] bg-gradient-to-br from-white/70 via-white/30 to-slate-200/50 p-[1px] shadow-[0_18px_45px_-30px_rgba(15,23,42,0.55)] transition-[height] duration-300 ease-out"
            style={{
                height: `min(${panelHeight}px, calc(100vh - 64px))`,
                maxHeight: `min(${MAX_HEIGHT}px, calc(100vh - 64px))`,
            }}
        >
            <div className="flex h-full flex-col rounded-[26px] bg-white/80 border border-white/50 backdrop-blur overflow-visible">
            {/* Header */}
            <div className="bg-gradient-to-r from-[#0f3b3e] via-[#1b4a66] to-[#1f2a44] text-white p-5 rounded-t-[26px] flex items-start justify-between">
                <div className="flex items-start gap-4">
                    <div className="relative">
                        <div className="absolute -inset-1 rounded-full bg-gradient-to-br from-amber-200/50 via-slate-200/30 to-sky-300/40 blur-[8px]" />
                        <div className="absolute -inset-0.5 rounded-full bg-gradient-to-br from-white/40 via-transparent to-white/10 opacity-70" />
                        <div className="relative w-12 h-12 rounded-full bg-slate-900/60 p-[2px] shadow-[0_10px_22px_rgba(15,23,42,0.45)]">
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
                                    <Bot className="w-6 h-6 text-white" />
                                )}
                            </div>
                        </div>
                        <span className="absolute -right-1 -bottom-1 h-3 w-3 rounded-full bg-emerald-400 border-2 border-[#123243] shadow-[0_0_8px_rgba(52,211,153,0.7)]" />
                    </div>
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-white/70">Agent</p>
                        <div className="flex flex-wrap items-center gap-2">
                            <h2 className="text-2xl font-semibold font-display">Digital Assistant</h2>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Terminal className="h-3 w-3 text-sky-200" />
                                Deployment Mentor
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Hands-on guidance for deploying LLM systems, infra, and tooling.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <LifeBuoy className="h-3 w-3 text-amber-200" />
                                Live Troubleshooting
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Real-time troubleshooting, root-cause analysis, and incident response.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Search className="h-3 w-3 text-cyan-200" />
                                Researcher
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Investigates sources, synthesizes evidence, and validates claims.
                                </span>
                            </span>
                        </div>
                        <div className="mt-2 flex items-center gap-2 overflow-visible whitespace-nowrap">
                            <span className="text-[10px] uppercase tracking-[0.2em] text-white/60">
                                Tools
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Brain className="h-3 w-3 text-emerald-200" />
                                Memory
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Remembers approved preferences and project context to personalize future replies.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <FileDown className="h-3 w-3 text-indigo-200" />
                                PDF Export
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Export chat outputs or summaries as downloadable PDFs.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Paperclip className="h-3 w-3 text-slate-200" />
                                File Upload
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Upload PDFs, DOCX, or text files for summarization and analysis.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Mail className="h-3 w-3 text-rose-200" />
                                Email Delivery
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Send PDFs or summaries to your email on request.
                                </span>
                            </span>
                            <span className="group relative inline-flex items-center gap-1 px-2 py-0.5 rounded-full border border-white/15 bg-white/10 text-[10px] text-white/85">
                                <Search className="h-3 w-3 text-cyan-200" />
                                Web Search
                                <span className="pointer-events-none absolute left-1/2 top-[calc(100%+8px)] z-20 w-[260px] whitespace-normal -translate-x-1/2 rounded-lg border border-white/10 bg-slate-900/95 px-2.5 py-2 text-[10px] text-white/90 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100">
                                    Uses Brave to fetch current information with citations when needed.
                                </span>
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 mt-1 rounded-2xl border border-white/10 bg-white/5 px-2 py-1 shadow-[0_6px_18px_-12px_rgba(15,23,42,0.5)]">
                    {memoryCandidates.length > 0 && (
                        <button
                            onClick={() => {
                                setIsHistoryOpen(true);
                                setHistoryTab('memory');
                                if (userId) {
                                    loadHistory(userId, false);
                                    loadMemory(userId);
                                }
                            }}
                            className="inline-flex items-center gap-1 rounded-xl border border-rose-300/40 bg-rose-500/90 p-2 text-[11px] text-white shadow-[0_4px_14px_rgba(244,63,94,0.4)] hover:bg-rose-500 transition-all duration-200 ease-out active:scale-95"
                            title="Review memory"
                        >
                            <Brain className="h-4 w-4 drop-shadow-sm" />
                            {memoryCandidates.length}
                        </button>
                    )}
                    <button
                        onClick={handleNewChat}
                        className="p-2 rounded-xl border border-white/15 bg-white/10 shadow-[0_3px_10px_rgba(15,23,42,0.25)] hover:bg-white/20 hover:-translate-y-0.5 transition-all duration-200 ease-out active:scale-95"
                        title="New Chat"
                    >
                        <MessageSquarePlus className="w-5 h-5 drop-shadow-sm" />
                    </button>
                    <button
                        onClick={() => {
                            setExpandStep(prev => (prev < MAX_EXPAND_STEPS ? prev + 1 : 0));
                        }}
                        className="p-2 rounded-xl border border-white/15 bg-white/10 shadow-[0_3px_10px_rgba(15,23,42,0.25)] hover:bg-white/20 hover:-translate-y-0.5 transition-all duration-200 ease-out active:scale-95"
                        title={expandStep >= MAX_EXPAND_STEPS ? 'Collapse' : 'Expand'}
                    >
                        <Maximize2 className="w-5 h-5 drop-shadow-sm" />
                    </button>
                        <button
                            onClick={() => {
                                setIsHistoryOpen(true);
                                setHistoryTab('history');
                                if (userId) {
                                    loadHistory(userId, false);
                                }
                            }}
                            className="p-2 rounded-xl border border-white/15 bg-white/10 shadow-[0_3px_10px_rgba(15,23,42,0.25)] hover:bg-white/20 hover:-translate-y-0.5 transition-all duration-200 ease-out active:scale-95"
                            title="History"
                        >
                            <History className="w-5 h-5 drop-shadow-sm" />
                        </button>
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
                    className={`absolute left-0 top-0 h-full w-80 bg-gradient-to-br from-[#0f3b3e]/96 via-[#1b4a66]/96 to-[#1f2a44]/96 border border-white/10 shadow-[0_20px_45px_-28px_rgba(2,8,23,0.7)] p-4 flex flex-col transform transition-transform duration-200 text-white ${
                        isHistoryOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
                >
                        <div className="flex items-center justify-between mb-2">
                            <p className="text-[11px] text-white/65 uppercase tracking-[0.2em]">Workspace</p>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleRefreshHistory}
                                    className="p-1 rounded hover:bg-white/15 transition-all duration-200 ease-out active:scale-95"
                                    title="Refresh"
                                    disabled={isLoadingHistory || isLoadingMemory}
                                >
                                    <RefreshCw className={`w-4 h-4 text-white/80 ${(isLoadingHistory || isLoadingMemory) ? 'animate-spin' : ''}`} />
                                </button>
                                <button
                                    onClick={() => setIsHistoryOpen(false)}
                                    className="p-1 rounded hover:bg-white/15 transition-all duration-200 ease-out active:scale-95"
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
                                <span className="text-[10px] text-white/50">5 recent</span>
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

            <div className="flex-1 flex flex-col overflow-hidden rounded-b-[26px]">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 bg-[radial-gradient(circle_at_top,_#ffffff,_#f1f5f9_55%,_#e7edf6_100%)]">
                {messages.length === 0 && (
                    <div className="text-center text-slate-500 mt-12">
                        <div className="mx-auto mb-4 w-20 h-20">
                            {renderPremiumAvatar('w-20 h-20', 'w-10 h-10', false)}
                        </div>
                        <p className="text-lg text-slate-700 font-medium">Hello! I&apos;m your Digital Assistant.</p>
                        <p className="text-sm mt-2">
                            Ask me about deployment strategy, tooling, or production incidents.
                        </p>
                    </div>
                )}

                {messages.map((message) => (
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
                            className={`max-w-[64%] rounded-2xl px-2.5 py-2 shadow-sm text-[13px] leading-relaxed ${
                                message.role === 'user'
                                    ? 'bg-gradient-to-br from-slate-800 to-slate-900 text-white whitespace-pre-wrap'
                                    : 'bg-white/90 border border-white/60 text-slate-800'
                            }`}
                        >
                            {message.role === 'assistant' ? (
                                <div className="text-sm leading-relaxed chat-markdown">
                                    <ReactMarkdown
                                        remarkPlugins={[remarkGfm]}
                                        components={{
                                            p: ({ children }) => {
                                                const isLinkOnly = Array.isArray(children)
                                                    ? children.length === 1 &&
                                                      typeof children[0] === 'object' &&
                                                      (children[0] as any)?.type === 'a'
                                                    : typeof children === 'object' &&
                                                      (children as any)?.type === 'a';
                                                return (
                                                    <p
                                                        className={`last:mb-0 ${
                                                            isLinkOnly ? 'mb-1' : 'mb-2'
                                                        }`}
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
                                            ul: ({ children }) => <ul>{children}</ul>,
                                            ol: ({ children }) => <ol>{children}</ol>,
                                            table: ({ children }) => (
                                                <div className="mb-3 overflow-x-auto rounded-lg border border-slate-200 bg-white">
                                                    <table className="w-full text-left text-xs">{children}</table>
                                                </div>
                                            ),
                                            thead: ({ children }) => (
                                                <thead className="bg-slate-50 text-slate-700">{children}</thead>
                                            ),
                                            tbody: ({ children }) => <tbody className="text-slate-700">{children}</tbody>,
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
                                                <li className="leading-snug">{children}</li>
                                            ),
                                            a: ({ href, children }) => {
                                                const safeHref = href
                                                    ? /^(https?:)?\/\//i.test(href)
                                                        ? href
                                                        : `https://${href}`
                                                    : '#';
                                                return (
                                                <a
                                                    href={safeHref}
                                                    target="_blank"
                                                    rel="noreferrer"
                                                    className="break-all text-slate-700 underline decoration-slate-300 underline-offset-2 hover:text-slate-900"
                                                >
                                                    {children}
                                                </a>
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
                                        }}
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
                ))}

                {isLoading && (
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
            <div className="border-t border-white/60 p-4 bg-white/90 rounded-b-[26px]">
                {displayStatusLabel && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                        <span className="inline-flex h-2 w-2 rounded-full bg-slate-400 animate-pulse" />
                        <span className="flex items-center gap-1">
                            {displayStatusLabel}
                        </span>
                    </div>
                )}
                <div className="flex gap-3">
                    <textarea
                        ref={inputRef}
                        rows={1}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="Ask about deployment, infrastructure, or troubleshooting..."
                        className="flex-1 px-4 py-3 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-slate-600/40 focus:border-transparent text-slate-800 bg-white shadow-sm resize-none leading-relaxed min-h-[48px] scrollbar-gutter-stable"
                        disabled={isLoading}
                        autoFocus
                    />
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
                        className="group relative px-3.5 py-3 bg-white text-slate-700 rounded-2xl border border-slate-200 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-slate-600/40 transition-all duration-200 ease-out hover:-translate-y-0.5 active:scale-95 shadow-[0_8px_18px_-12px_rgba(15,23,42,0.35)]"
                        aria-label="Upload file"
                    >
                        <span className="absolute inset-0 rounded-2xl bg-gradient-to-br from-slate-50 via-white to-slate-100 opacity-80" />
                        <span className="absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.35),_transparent_60%)]" />
                        <span className="relative flex items-center justify-center">
                            <Paperclip className="w-5 h-5 drop-shadow-sm" />
                        </span>
                    </button>
                    <button
                        onClick={sendMessage}
                        disabled={
                            (!input.trim() && !(selectedFile && uploadedFileId && uploadStatus === 'uploaded')) ||
                            isLoading ||
                            uploadStatus === 'uploading' ||
                            uploadStatus === 'error'
                        }
                        className="group relative px-4 py-3 rounded-2xl text-white focus:outline-none focus:ring-2 focus:ring-slate-600/40 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 ease-out hover:-translate-y-0.5 active:scale-95 shadow-[0_10px_24px_-14px_rgba(15,23,42,0.5)] bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 hover:from-slate-800 hover:via-slate-900 hover:to-slate-800"
                    >
                        <span className="absolute inset-0 rounded-2xl opacity-0 transition-opacity duration-200 group-hover:opacity-100 bg-[radial-gradient(circle_at_top,_rgba(148,163,184,0.35),_transparent_65%)]" />
                        <span className="relative flex items-center justify-center gap-2">
                            <Send className="w-5 h-5 drop-shadow-sm" />
                        </span>
                    </button>
                </div>
                {(selectedFile || uploadError) && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                        {selectedFile && (
                            <span className="group relative inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 border border-slate-200">
                                <span className="pointer-events-none absolute left-1/2 -top-2 z-30 w-[260px] -translate-x-1/2 -translate-y-full rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-[11px] text-slate-700 opacity-0 shadow-lg transition-opacity duration-200 group-hover:opacity-100 whitespace-normal">
                                    {selectedFile.name}
                                </span>
                                <span className="font-medium text-slate-700">{selectedFile.name}</span>
                                {uploadStatus === 'uploading' && <span className="text-slate-500">Uploading…</span>}
                                {uploadStatus === 'uploaded' && <span className="text-emerald-600">Uploaded</span>}
                                {uploadStatus === 'error' && <span className="text-rose-600">Failed</span>}
                                <button
                                    type="button"
                                    onClick={resetUpload}
                                    className="text-slate-500 hover:text-slate-700"
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
