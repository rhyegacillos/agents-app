"use client"

import Link from 'next/link';
import { SignInButton, SignedIn, SignedOut, UserButton } from '@clerk/nextjs';
import ThemeToggle from '../components/ThemeToggle';

export default function Home() {
  const year = new Date().getFullYear();
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f6fbfb] text-slate-900 dark:bg-[#0b1217] dark:text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,#d7eef0_1px,transparent_0)] bg-[size:28px_28px] opacity-60 dark:hidden" />
        <div className="absolute inset-0 hidden bg-[radial-gradient(circle_at_1px_1px,#1f2a35_1px,transparent_0)] bg-[size:28px_28px] opacity-70 dark:block" />
        <div className="absolute -top-36 right-[-8%] h-96 w-96 rounded-full bg-gradient-to-br from-emerald-200/70 to-cyan-200/40 blur-3xl dark:from-emerald-900/40 dark:to-cyan-900/20" />
        <div className="absolute top-40 left-[-6%] h-80 w-80 rounded-full bg-gradient-to-br from-sky-200/50 to-teal-200/30 blur-3xl dark:from-sky-900/40 dark:to-teal-900/20" />
      </div>

      <div className="relative mx-auto max-w-6xl px-6 pt-16 pb-1">
        <nav className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
              Premium Healthcare SaaS
            </p>
            <h1 className="font-display text-2xl text-slate-900 dark:text-slate-100">
              MediNotes Pro
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700">
                  Sign In
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <div className="flex flex-wrap items-center gap-3 sm:gap-4">
                <Link
                  href="/product"
                  className="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700"
                >
                  Go to App
                </Link>
                <UserButton showName={true} />
              </div>
            </SignedIn>
          </div>
        </nav>

        <div className="safe-fixed-top-right fixed z-50">
          <ThemeToggle />
        </div>

        <section className="grid gap-10 pb-10 pt-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
              Premium Consultation Intelligence
            </p>
            <h2 className="font-display text-4xl text-slate-900 md:text-5xl dark:text-slate-100">
              Everything clinicians need to deliver a polished, patient-ready visit summary.
            </h2>
            <p className="mt-4 max-w-2xl text-base text-slate-600 dark:text-slate-300">
              Premium unlocks secure document and audio ingestion, English transcription, structured clinical detail
              extraction, clinical decision support, and one-click patient email delivery with clinic-branded formatting.
              A dedicated Patient History tab brings a searchable roster with last-visit context, date filters, and rich visit cards.
              MediNotes Assistant ties it together with proactive briefings, Q&A, and on-demand drafts.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {[
                'Structured summaries',
                'Clinical templates',
                'Patient Memory',
                'Patient History tab',
                'Action Coordinator',
                'Clinical Decision Support',
                'Quality Review',
                'MediNotes Assistant',
                'Doctor detail extraction',
                'Secure document ingestion',
                'Prescription images',
                'Audio to English',
                'Clinic-branded email',
              ].map((item) => (
                <span
                  key={item}
                  className="rounded-full border border-emerald-200 bg-white/80 px-3 py-1 text-xs font-semibold text-emerald-700 dark:border-emerald-700/60 dark:bg-slate-900/70 dark:text-emerald-300"
                >
                  {item}
                </span>
              ))}
            </div>
            <div className="mt-8 flex flex-wrap gap-4">
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="rounded-xl bg-emerald-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700">
                    Start Premium Trial
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <Link
                  href="/product"
                  className="rounded-xl bg-slate-900 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-200/60 transition hover:bg-slate-800 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400"
                >
                  Open Consultation Assistant
                </Link>
              </SignedIn>
            </div>
          </div>

          <div className="rounded-2xl border border-emerald-100/80 bg-white/90 p-6 shadow-[0_18px_40px_-32px_rgba(15,23,42,0.45)] dark:border-slate-700/80 dark:bg-slate-900/85 dark:shadow-[0_18px_40px_-32px_rgba(15,23,42,0.8)]">
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
              Premium Includes
            </p>
            <ul className="mt-4 space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    MediNotes Assistant
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>Proactive patient briefings, context-aware Q&A, on-demand documents, and in-app guidance.</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Patient Memory (RAG)
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>Automatically recalls past visits to provide context and track changes over time.</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Action Coordinator
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>Extracts next steps like follow-ups and prescriptions into structured, actionable items.</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Clinical Decision Support
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>Adds drug interaction checks and guideline notes to summaries.</li>
                    <li>Evidence-linked summaries with source snippets and external links.</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Quality Review
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>An automated check compares each summary against the original notes, finds missing or incorrect details, and regenerates the summary when needed</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                <div>
                  <p className="font-semibold text-slate-900 dark:text-slate-100">
                    Patient Visits History
                  </p>
                  <ul className="mt-1 ml-4 list-disc text-sm text-slate-600 dark:text-slate-300">
                    <li>Offers patient search, a timeline view, flexible filters, smooth pagination, and access to past visit summaries.</li>
                  </ul>
                </div>
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Structured visit summaries, next steps, and patient-ready email drafts in consistent clinical language.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Secure PDF, DOCX, TXT, and markdown ingestion with extraction for comprehensive visit context.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Prescription image transcription to English for medication capture and follow-up clarity.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Audio uploads transcribed to English to turn spoken consults into actionable summaries.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Auto-extraction of doctor name, clinic, phone, and reply-to email for signature-ready messages.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                One-click email sending with clinic-branded HTML formatting and optional language translation.
              </li>
            </ul>
          </div>
        </section>

        <section className="grid gap-6 pb-12 md:grid-cols-2 lg:grid-cols-3">
          {[
            {
              title: 'MediNotes Assistant',
              body: 'Proactive patient briefings, context-aware Q&A, on-demand drafts, and in-app guidance.',
            },
            {
              title: 'Summaries + Memory',
              body: 'Clear summaries that include relevant patient past visits.',
            },
            {
              title: 'Patient History Workspace',
              body: 'Toggle to a dedicated tab with searchable patient list, last-visit metadata, visit timeline, and date filters to narrow prior notes.',
            },
            {
              title: 'Action Coordinator',
              body: 'Turns Next Steps into structured, actionable items clinicians can follow up on.',
            },
            {
              title: 'Clinical Decision Support',
              body: 'Medication interaction checks, guideline lookups, and evidence links that cite sources.',
            },
            {
              title: 'Quality Review',
              body: 'Automated critic checks summaries against source notes and regenerates when needed.',
            },
            {
              title: 'Email Delivery',
              body: 'Patient-ready drafts with clinic branding and optional translation.',
            },
            {
              title: 'Documents + Audio',
              body: 'Ingest PDFs, notes, prescriptions, and audio transcripts into the visit context.',
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-2xl border border-slate-200 bg-white/90 p-5 shadow-[0_16px_32px_-28px_rgba(15,23,42,0.45)] dark:border-slate-700 dark:bg-slate-900/85 dark:shadow-[0_16px_32px_-28px_rgba(15,23,42,0.8)]"
            >
              <h3 className="font-display text-lg text-slate-900 dark:text-slate-100">
                {feature.title}
              </h3>
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
                {feature.body}
              </p>
            </div>
          ))}
        </section>

        <div className="text-center text-xs uppercase tracking-[0.3em] text-slate-500 dark:text-slate-400">
          HIPAA ready • Secure • Professional
        </div>
        <footer className="mt-2 flex min-h-[24px] flex-col gap-1 border-t border-slate-200/70 pt-1 text-[10px] text-slate-500 sm:flex-row sm:items-center dark:border-slate-700/70 dark:text-slate-400">
          <span className="w-full sm:flex-1 sm:text-left">{year}</span>
          <span className="w-full font-semibold sm:flex-1 sm:text-center">RG</span>
          <span className="w-full break-all sm:flex-1 sm:text-right">gacillos.rhye@gmail.com</span>
        </footer>
      </div>
    </main>
  );
}
