'use client';

import { useState, useRef, useEffect, type ChangeEvent } from 'react';
import { Send, Bot, User, History, X, RefreshCw, Maximize2, Minimize2, Paperclip, MessageSquarePlus, Brain } from 'lucide-react';
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
    const [streamStatus, setStreamStatus] = useState<string | null>(null);
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
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'uploaded' | 'error'>('idle');
    const [uploadError, setUploadError] = useState<string | null>(null);
    const [uploadedFileId, setUploadedFileId] = useState<string | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);
    const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const statusHoldUntilRef = useRef<number>(0);
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

    const isValidSyncCode = (code: string) => /^[a-zA-Z0-9_-]{8,64}$/.test(code);

    const generateSyncCode = () => {
        const bytes = new Uint8Array(8);
        crypto.getRandomValues(bytes);
        return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
    };

    const lastSessionKey = (uid: string) => `last_session_id:${uid}`;
    const statusLabel =
        streamStatus === 'searching_web'
            ? 'Searching the web…'
            : streamStatus === 'generating_response'
                ? 'Generating response…'
                : null;

    const setStatusWithHold = (status: string) => {
        if (statusTimeoutRef.current) {
            clearTimeout(statusTimeoutRef.current);
            statusTimeoutRef.current = null;
        }
        if (status === 'searching_web') {
            statusHoldUntilRef.current = Date.now() + 800;
            setStreamStatus(status);
            return;
        }
        if (status === 'generating_response' && Date.now() < statusHoldUntilRef.current) {
            const delay = statusHoldUntilRef.current - Date.now();
            statusTimeoutRef.current = setTimeout(() => {
                setStreamStatus('generating_response');
                statusHoldUntilRef.current = 0;
            }, delay);
            return;
        }
        statusHoldUntilRef.current = 0;
        setStreamStatus(status);
    };

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

    const loadMemory = async (uid: string) => {
        setIsLoadingMemory(true);
        setMemoryError(null);
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
            setMemoryCandidates(candidatesData.candidates || []);
            setMemoryApproved(approvedData.memory || []);
        } catch (error) {
            console.error('Error loading memory:', error);
        } finally {
            setIsLoadingMemory(false);
        }
    };

    const parseSseStream = async (
        response: Response,
        onEvent: (event: string, data: string) => void
    ) => {
        if (!response.body) {
            throw new Error('No response body for stream');
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';
            for (const part of parts) {
                const lines = part.split('\n');
                let event = 'message';
                const dataLines: string[] = [];
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        event = line.slice(6).trim();
                    } else if (line.startsWith('data:')) {
                        dataLines.push(line.slice(5).trim());
                    }
                }
                const data = dataLines.join('\n');
                if (data) {
                    onEvent(event, data);
                }
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
            setStreamStatus('generating_response');
            const response = await fetch(`${API_URL}/chat/stream`, {
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

            await parseSseStream(response, (event, data) => {
                if (event === 'status') {
                    setStatusWithHold(data);
                    return;
                }
                if (event === 'done') {
                    try {
                        const payload = JSON.parse(data);
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
                        loadHistory(userId, false);
                    } catch (err) {
                        console.error('Failed to parse done payload:', err);
                    }
                    setStreamStatus(null);
                    return;
                }
                if (event === 'error') {
                    try {
                        const payload = JSON.parse(data);
                        console.error('Stream error:', payload?.detail);
                    } catch {
                        console.error('Stream error:', data);
                    }
                    setStreamStatus(null);
                }
            });
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
            setStreamStatus(null);
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

    useEffect(() => {
        return () => {
            if (statusTimeoutRef.current) {
                clearTimeout(statusTimeoutRef.current);
            }
        };
    }, []);

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
            className="absolute bottom-0 left-0 right-0 flex flex-col rounded-3xl bg-white/80 border border-white/60 backdrop-blur overflow-hidden transition-[height] duration-300 ease-out"
            style={{
                height: `min(${panelHeight}px, calc(100vh - 64px))`,
                maxHeight: `min(${MAX_HEIGHT}px, calc(100vh - 64px))`,
            }}
        >
            {/* Header */}
            <div className="bg-gradient-to-r from-[#0f3b3e] via-[#1b4a66] to-[#1f2a44] text-white p-5 rounded-t-3xl flex items-start justify-between">
                <div className="flex items-start gap-4">
                    <div className="relative">
                        {hasAvatar ? (
                            <img
                                src="/avatar.jpg"
                                alt="Digital Assistant Avatar"
                                className="w-12 h-12 rounded-2xl border border-white/30 object-cover shadow-sm"
                            />
                        ) : (
                            <div className="w-12 h-12 rounded-2xl bg-white/10 flex items-center justify-center">
                                <Bot className="w-6 h-6 text-white" />
                            </div>
                        )}
                        <span className="absolute -right-1 -bottom-1 h-3 w-3 rounded-full bg-emerald-400 border-2 border-[#123243]" />
                    </div>
                    <div>
                        <p className="text-xs uppercase tracking-[0.3em] text-white/70">Agent</p>
                        <h2 className="text-2xl font-semibold font-display">Digital Assistant</h2>
                        <div className="flex flex-wrap gap-2 mt-2">
                            <span className="px-2.5 py-1 rounded-full bg-white/10 text-xs text-white/80">
                                Memory on
                            </span>
                            <span className="px-2.5 py-1 rounded-full bg-white/10 text-xs text-white/80">
                                Deployment mentor
                            </span>
                            <span className="px-2.5 py-1 rounded-full bg-white/10 text-xs text-white/80">
                                Live troubleshooting
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2 mt-1">
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
                                className="inline-flex items-center gap-1 rounded-xl bg-rose-500/90 p-2 text-[11px] text-white hover:bg-rose-500 transition-all duration-200 ease-out active:scale-95"
                                title="Review memory"
                            >
                                <Brain className="h-4 w-4" />
                                {memoryCandidates.length}
                            </button>
                        )}
                        <button
                            onClick={() => {
                                setExpandStep(prev => (prev < MAX_EXPAND_STEPS ? prev + 1 : 0));
                            }}
                            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-all duration-200 ease-out active:scale-95"
                            title={expandStep >= MAX_EXPAND_STEPS ? 'Collapse' : 'Expand'}
                        >
                            <Maximize2 className="w-5 h-5" />
                        </button>
                        <button
                            onClick={() => {
                                setIsHistoryOpen(true);
                                if (userId) {
                                    loadHistory(userId, false);
                                }
                            }}
                            className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-all duration-200 ease-out active:scale-95"
                            title="History"
                        >
                            <History className="w-5 h-5" />
                        </button>
                    <button
                        onClick={handleNewChat}
                        className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-all duration-200 ease-out active:scale-95"
                        title="New Chat"
                    >
                        <MessageSquarePlus className="w-5 h-5" />
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
                    className={`absolute left-0 top-0 h-full w-80 bg-white/98 border border-white/60 shadow-[0_18px_40px_-30px_rgba(15,23,42,0.45)] p-4 flex flex-col transform transition-transform duration-200 ${
                        isHistoryOpen ? 'translate-x-0' : '-translate-x-full'
                    }`}
                >
                        <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setHistoryTab('history')}
                                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ease-out ${
                                        historyTab === 'history'
                                            ? 'bg-slate-900 text-white'
                                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                    }`}
                                >
                                    Chat History
                                </button>
                                <button
                                    onClick={() => setHistoryTab('memory')}
                                    className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-200 ease-out ${
                                        historyTab === 'memory'
                                            ? 'bg-slate-900 text-white'
                                            : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                    }`}
                                >
                                    Memory
                                    {memoryCandidates.length > 0 && (
                                        <span className="ml-2 inline-flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] px-1.5">
                                            {memoryCandidates.length}
                                        </span>
                                    )}
                                </button>
                            </div>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handleRefreshHistory}
                                    className="p-1 rounded hover:bg-gray-100 transition-all duration-200 ease-out active:scale-95"
                                    title="Refresh"
                                    disabled={isLoadingHistory || isLoadingMemory}
                                >
                                    <RefreshCw className={`w-4 h-4 text-gray-600 ${(isLoadingHistory || isLoadingMemory) ? 'animate-spin' : ''}`} />
                                </button>
                                <button
                                    onClick={() => setIsHistoryOpen(false)}
                                    className="p-1 rounded hover:bg-gray-100 transition-all duration-200 ease-out active:scale-95"
                                    title="Close"
                                >
                                    <X className="w-5 h-5 text-gray-600" />
                                </button>
                            </div>
                        </div>
                        <p className="text-xs text-gray-500 mb-4">
                            {historyTab === 'history'
                                ? 'History shows your 5 most recent conversations.'
                                : 'Review memory candidates before approval.'}
                        </p>

                        <div className="flex-1 overflow-y-auto space-y-3 transition-opacity duration-300 ease-out">
                            {historyTab === 'history' && (
                                <>
                                    {isLoadingHistory && (
                                        <p className="text-sm text-gray-500">Loading history…</p>
                                    )}
                                    {!isLoadingHistory && sessions.length === 0 && (
                                        <p className="text-sm text-gray-500">No conversations yet.</p>
                                    )}
                                    {sessions.map((session) => (
                                        <button
                                            key={session.session_id}
                                            onClick={() => {
                                                loadConversation(userId, session.session_id);
                                                setIsHistoryOpen(false);
                                            }}
                                            className={`w-full text-left p-2 rounded border transition-all duration-300 ease-out active:scale-[0.99] hover:-translate-y-0.5 hover:shadow-sm ${
                                                session.session_id === sessionId
                                                    ? 'border-slate-600 bg-slate-50'
                                                    : 'border-gray-200 hover:bg-gray-50'
                                            }`}
                                        >
                                            <p className="text-sm font-medium text-gray-800 truncate">
                                                {session.title}
                                            </p>
                                            <p className="text-xs text-gray-500">
                                                {new Date(session.updated_at).toLocaleString()}
                                            </p>
                                        </button>
                                    ))}
                                </>
                            )}

                            {historyTab === 'memory' && (
                                <>
                                    {memoryError && (
                                        <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                                            {memoryError}
                                        </div>
                                    )}
                                    {isLoadingMemory && (
                                        <p className="text-sm text-gray-500">Loading memory…</p>
                                    )}
                                    {!isLoadingMemory && memoryCandidates.length === 0 && (
                                        <p className="text-sm text-gray-500">No pending memories.</p>
                                    )}
                                    {memoryCandidates.map((cand) => (
                                        <div
                                            key={cand.id}
                                            className="rounded-xl border border-slate-200 bg-white px-3 py-2 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-sm"
                                        >
                                            <p className="text-sm font-medium text-slate-800">{cand.text}</p>
                                            <p className="text-[11px] text-slate-500 mt-1">
                                                {cand.category} • TTL {cand.ttl_days}d
                                            </p>
                                            <div className="mt-2 flex gap-2">
                                                <button
                                                    onClick={() => approveCandidate(cand.id)}
                                                    disabled={memoryAction?.id === cand.id && memoryAction.action === 'approve'}
                                                    className="px-2 py-1 text-xs rounded-full bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
                                                >
                                                    {memoryAction?.id === cand.id && memoryAction.action === 'approve' ? (
                                                        <span className="inline-flex h-3 w-3 animate-spin rounded-full border-2 border-white/60 border-t-white" />
                                                    ) : null}
                                                    Approve
                                                </button>
                                                <button
                                                    onClick={() => rejectCandidate(cand.id)}
                                                    disabled={memoryAction?.id === cand.id && memoryAction.action === 'reject'}
                                                    className="px-2 py-1 text-xs rounded-full bg-slate-200 text-slate-700 hover:bg-slate-300 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
                                                >
                                                    {memoryAction?.id === cand.id && memoryAction.action === 'reject' ? (
                                                        <span className="inline-flex h-3 w-3 animate-spin rounded-full border-2 border-slate-400/60 border-t-slate-600" />
                                                    ) : null}
                                                    Reject
                                                </button>
                                            </div>
                                        </div>
                                    ))}

                                    <div className="pt-2 border-t border-slate-200">
                                        <p className="text-xs font-semibold text-slate-700 mb-2">Approved Memory</p>
                                        {memoryApproved.length === 0 && (
                                            <p className="text-sm text-gray-500">No approved memory yet.</p>
                                        )}
                                        {memoryApproved.map((mem) => (
                                            <div
                                                key={mem.id}
                                                className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 mb-2 transition-all duration-300 ease-out hover:-translate-y-0.5 hover:shadow-sm"
                                            >
                                                <p className="text-sm text-slate-700">{mem.text}</p>
                                                <p className="text-[11px] text-slate-500 mt-1">
                                                    {mem.category}
                                                    {mem.expires_at
                                                        ? ` • Expires ${new Date(mem.expires_at).toLocaleDateString()}`
                                                        : ''}
                                                </p>
                                                <div className="mt-2">
                                                    <button
                                                        onClick={() => deleteApprovedMemory(mem.id)}
                                                        disabled={memoryAction?.id === mem.id && memoryAction.action === 'remove'}
                                                        className="px-2 py-1 text-xs rounded-full bg-slate-200 text-slate-700 hover:bg-slate-300 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
                                                    >
                                                        {memoryAction?.id === mem.id && memoryAction.action === 'remove' ? (
                                                            <span className="inline-flex h-3 w-3 animate-spin rounded-full border-2 border-slate-400/60 border-t-slate-600" />
                                                        ) : null}
                                                        Remove
                                                    </button>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-5 space-y-5 bg-[radial-gradient(circle_at_top,_#ffffff,_#f1f5f9_55%,_#e7edf6_100%)]">
                {messages.length === 0 && (
                    <div className="text-center text-slate-500 mt-12">
                        {hasAvatar ? (
                            <img
                                src="/avatar.jpg"
                                alt="Digital Assitant Avatar"
                                className="w-20 h-20 rounded-2xl mx-auto mb-4 border-2 border-white shadow-md"
                            />
                        ) : (
                            <Bot className="w-12 h-12 mx-auto mb-4 text-slate-400" />
                        )}
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
                                {hasAvatar ? (
                                    <img 
                                        src="/avatar.jpg" 
                                        alt="Digital Assistant Avatar" 
                                        className="w-8 h-8 rounded-full border border-slate-300"
                                    />
                                ) : (
                                    <div className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center">
                                        <Bot className="w-5 h-5 text-white" />
                                    </div>
                                )}
                            </div>
                        )}

                        <div
                            className={`max-w-[72%] rounded-2xl px-4 py-3 shadow-sm ${
                                message.role === 'user'
                                    ? 'bg-gradient-to-br from-slate-800 to-slate-900 text-white'
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
                                className={`text-xs mt-1 ${
                                    message.role === 'user' ? 'text-slate-300' : 'text-slate-500'
                                }`}
                            >
                                {message.timestamp.toLocaleTimeString()}
                            </p>
                        </div>

                        {message.role === 'user' && (
                            <div className="flex-shrink-0">
                                <div className="w-8 h-8 bg-gray-600 rounded-full flex items-center justify-center">
                                    <User className="w-5 h-5 text-white" />
                                </div>
                            </div>
                        )}
                    </div>
                ))}

                {isLoading && (
                    <div className="flex gap-3 justify-start">
                        <div className="flex-shrink-0">
                            {hasAvatar ? (
                                <img 
                                    src="/avatar.jpg" 
                                    alt="Digital Assistant Avatar" 
                                    className="w-8 h-8 rounded-full border border-slate-300"
                                />
                            ) : (
                                <div className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center">
                                    <Bot className="w-5 h-5 text-white" />
                                </div>
                            )}
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
            <div className="border-t border-white/60 p-4 bg-white/90 rounded-b-3xl">
                {statusLabel && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
                        <span className="inline-flex h-2 w-2 rounded-full bg-slate-400 animate-pulse" />
                        <span className="flex items-center gap-1">
                            {statusLabel}
                            {streamStatus === 'generating_response' && (
                                <span className="inline-flex items-center gap-1">
                                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce" />
                                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce delay-100" />
                                    <span className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce delay-200" />
                                </span>
                            )}
                        </span>
                    </div>
                )}
                <div className="flex gap-3">
                    <input
                        ref={inputRef}
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyPress}
                        placeholder="Ask about deployment, infrastructure, or troubleshooting..."
                        className="flex-1 px-4 py-3 border border-slate-200 rounded-2xl focus:outline-none focus:ring-2 focus:ring-slate-600/40 focus:border-transparent text-slate-800 bg-white shadow-sm"
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
                        className="px-3 py-3 bg-white text-slate-700 rounded-2xl border border-slate-200 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-600/40 transition-all duration-200 ease-out active:scale-[0.98]"
                        aria-label="Upload file"
                    >
                        <Paperclip className="w-5 h-5" />
                    </button>
                    <button
                        onClick={sendMessage}
                        disabled={
                            (!input.trim() && !(selectedFile && uploadedFileId && uploadStatus === 'uploaded')) ||
                            isLoading ||
                            uploadStatus === 'uploading' ||
                            uploadStatus === 'error'
                        }
                        className="px-4 py-3 bg-slate-900 text-white rounded-2xl hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-slate-600/40 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-200 ease-out active:scale-[0.98]"
                    >
                        <Send className="w-5 h-5" />
                    </button>
                </div>
                {(selectedFile || uploadError) && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                        {selectedFile && (
                            <span className="inline-flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 border border-slate-200">
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
    );
}
