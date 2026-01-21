"use client"

import Link from 'next/link';
import { SignInButton, SignedIn, SignedOut, UserButton } from '@clerk/nextjs';
import ThemeToggle from '../components/ThemeToggle';

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#f6fbfb] text-slate-900 dark:bg-[#0b1217] dark:text-slate-100">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_1px_1px,#d7eef0_1px,transparent_0)] bg-[size:28px_28px] opacity-60 dark:hidden" />
        <div className="absolute inset-0 hidden bg-[radial-gradient(circle_at_1px_1px,#1f2a35_1px,transparent_0)] bg-[size:28px_28px] opacity-70 dark:block" />
        <div className="absolute -top-36 right-[-8%] h-96 w-96 rounded-full bg-gradient-to-br from-emerald-200/70 to-cyan-200/40 blur-3xl dark:from-emerald-900/40 dark:to-cyan-900/20" />
        <div className="absolute top-40 left-[-6%] h-80 w-80 rounded-full bg-gradient-to-br from-sky-200/50 to-teal-200/30 blur-3xl dark:from-sky-900/40 dark:to-teal-900/20" />
      </div>

      <div className="relative mx-auto max-w-6xl px-6 py-10">
        <nav className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
              Premium Healthcare SaaS
            </p>
            <h1 className="font-display text-2xl text-slate-900 dark:text-slate-100">
              MediNotes Pro
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-lg shadow-emerald-200/60 transition hover:bg-emerald-700">
                  Sign In
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <div className="flex items-center gap-4">
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

        <div className="fixed right-4 top-4 z-50 sm:right-6 sm:top-6">
          <ThemeToggle />
        </div>

        <section className="grid gap-10 pb-10 pt-12 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
          <div>
            <p className="text-xs uppercase tracking-[0.3em] text-emerald-700 dark:text-emerald-300">
              Premium Consultation Intelligence
            </p>
            <h2 className="font-display text-4xl text-slate-900 md:text-5xl dark:text-slate-100">
              Everything clinicians need to deliver a polished visit summary.
            </h2>
            <p className="mt-4 max-w-2xl text-base text-slate-600 dark:text-slate-300">
              Premium unlocks document and audio ingestion, English transcription, doctor detail extraction, and
              one-click patient email delivery with a clinic-branded header.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              {[
                'Structured summaries',
                'Action items',
                'Patient email drafts',
                'PDF/DOCX/MD uploads',
                'Prescription images',
                'Audio to English',
                'Send email with reply-to',
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
                Professional summaries, action items, and patient-friendly email drafts.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Secure PDF, DOCX, and markdown uploads for consultation notes.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Handwritten prescription image transcription to English.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Audio uploads with Whisper transcription to English.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                Doctor name, clinic, phone, and reply-to extraction for signatures.
              </li>
              <li className="flex items-start gap-3">
                <span className="mt-1 h-2 w-2 rounded-full bg-emerald-500" />
                One-click email sending with clinic-branded headers.
              </li>
            </ul>
          </div>
        </section>

        <section className="grid gap-6 pb-12 md:grid-cols-2 lg:grid-cols-3">
          {[
            {
              title: 'Professional Summaries',
              body: 'Structured visit summaries for medical records in seconds.',
            },
            {
              title: 'Action Items',
              body: 'Clear follow-ups and next steps for every consultation.',
            },
            {
              title: 'Patient Email Drafts',
              body: 'Friendly, ready-to-send patient communication templates.',
            },
            {
              title: 'Documents + Prescriptions (Premium)',
              body: 'Ingest PDFs, DOCX, markdown, and prescription images for richer summaries.',
            },
            {
              title: 'Audio Transcription (Premium)',
              body: 'Upload audio and receive English transcription instantly.',
            },
            {
              title: 'Email Delivery (Premium)',
              body: 'Send emails with clinic-branded headers and reply-to routing.',
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
      </div>
    </main>
  );
}
