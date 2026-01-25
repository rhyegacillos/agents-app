"use client"

import { useState, FormEvent, ChangeEvent, useEffect, useRef } from 'react';
import { useAuth } from '@clerk/nextjs';
import DatePicker from 'react-datepicker';
import { fetchEventSource } from '@microsoft/fetch-event-source';
import { Protect, PricingTable, UserButton } from '@clerk/nextjs';
import ThemeToggle from '../components/ThemeToggle';

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

type ConsultationFormProps = {
    isPremium?: boolean;
};

type UploadPayload = {
    filename: string;
    file_b64: string;
    mime: string;
};

type PrescriptionEntry = {
    filename: string;
    text: string;
};

function ConsultationForm({ isPremium = true }: ConsultationFormProps) {
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
        setLoading(true);

        const jwt = await getToken();
        if (!jwt) {
            setOutput('Authentication required');
            setLoading(false);
            return;
        }

        const controller = new AbortController();
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
            await fetchEventSource('/api/consultation', {
                signal: controller.signal,
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${jwt}`,
                },
                body: JSON.stringify({
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
                        throw new Error(`HTTP ${res.status}`);
                    }
                },
                onmessage(ev) {
                    if (ev.event === 'metadata') {
                        try {
                            const data = JSON.parse(ev.data);
                            if (data.doctor_name) {
                                setDoctorName((prev) => prev || data.doctor_name);
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
                        } catch {
                            // Ignore metadata parse failures
                        }
                        return;
                    }

                    if (ev.event === 'actions') {
                        try {
                            const data = JSON.parse(ev.data);
                            if (Array.isArray(data)) {
                                setActions(data);
                            }
                        } catch {
                            // Ignore
                        }
                        return;
                    }

                    setStatusMessage((msg) => (msg ? 'Generating summary...' : ''));
                    buffer += ev.data;
                    setOutput(buffer);
                },
                onclose() { 
                    setLoading(false); 
                    setStatusMessage('');
                },
                onerror(err) {
                    console.error('SSE error:', err);
                    controller.abort();
                    setLoading(false);
                    setStatusMessage('Unable to generate summary. Please try again.');
                    setOutput('Unable to generate summary. Please try again.');
                },
            });
        } catch (err: any) {
            console.error('Request failed:', err);
            setOutput((prev) => prev || err?.message || 'Request failed. Please try again.');
            setLoading(false);
            setStatusMessage('');
        }
    }

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

    function formatDoctorName(name: string) {
        const trimmed = name.trim();
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
            const jwt = await getToken();
            if (!jwt) {
                setEmailStatus('Authentication required.');
                setSendingEmail(false);
                return;
            }

            const response = await fetch('/api/send-email', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${jwt}`,
                },
                body: JSON.stringify({
                    to: patientEmail.trim(),
                    subject,
                    html,
                    reply_to: doctorEmail.trim(),
                    clinic_name: clinicName.trim(),
                    language: selectedLanguage,
                }),
            });

            if (!response.ok) {
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

    return (
        <div className="mx-auto max-w-5xl px-6 pb-16">
            <form
                onSubmit={handleSubmit}
                className="animate-fade-in rounded-2xl border border-emerald-100/80 bg-white/90 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.55)] backdrop-blur dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.9)]"
            >
                <div className="border-b border-emerald-100/80 px-6 py-5">
                    <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
                        Clinical Intake
                    </p>
                    <h2 className="font-display text-2xl text-slate-900 dark:text-slate-100">Consultation Documentation</h2>
                    <p className="text-sm text-slate-500 dark:text-slate-300">
                        Enter visit details and upload relevant documents or audio recordings.
                    </p>
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
                                                <li key={file.filename} className="break-words">
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
                                                <li key={file.filename} className="break-words">
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
                                                <li key={file.filename} className="break-words">
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
        </div>
    );
}

export default function Product() {
    return (
        <main className="relative min-h-screen overflow-hidden bg-[#f6fbfb] text-slate-900 dark:bg-[#0b1217] dark:text-slate-100">
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
                                and patient-ready communication in minutes.
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
                            <UserButton showName={true} />
                        </div>
                    </div>
                </header>

                <div className="fixed right-4 top-4 z-50 sm:right-6 sm:top-6">
                    <ThemeToggle />
                </div>

                <Protect
                    plan="premium_subscription"
                    fallback={
                        <>
                            <ConsultationForm isPremium={false} />
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
                    <ConsultationForm />
                </Protect>
            </div>
        </main>
    );
}
