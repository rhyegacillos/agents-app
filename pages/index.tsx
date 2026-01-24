"use client";

import Link from "next/link";
import { SignInButton, SignedIn, SignedOut, UserButton, useUser } from "@clerk/nextjs";

export default function Home() {
  const { user, isLoaded } = useUser();

  const displayName = !isLoaded
    ? ""
    : user?.fullName ||
      user?.firstName ||
      user?.username ||
      user?.primaryEmailAddress?.emailAddress ||
      "";

  return (
    <main className="min-h-screen">
      {/* Background */}
      <div className="pointer-events-none fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-[#070a12]" />
        <div className="absolute inset-0 bg-[radial-gradient(1200px_600px_at_20%_-10%,rgba(99,102,241,0.35),transparent_55%),radial-gradient(900px_500px_at_85%_0%,rgba(59,130,246,0.25),transparent_55%),radial-gradient(1200px_700px_at_50%_110%,rgba(168,85,247,0.18),transparent_55%)]" />
        <div className="absolute inset-0 opacity-40 bg-[linear-gradient(to_bottom,rgba(255,255,255,0.06)_1px,transparent_1px),linear-gradient(to_right,rgba(255,255,255,0.06)_1px,transparent_1px)] bg-[size:48px_48px]" />
      </div>

      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-white/10 bg-black/20 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 bg-white/10 shadow-sm">
              <span className="text-white font-bold">IG</span>
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold text-white">IdeaGen</div>
              <div className="text-xs text-white/60">AI idea engine for the agent economy</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <a
              href="#features"
              className="hidden sm:inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-white/85 hover:bg-white/10"
            >
              Features
            </a>

            <a
              href="#pricing"
              className="hidden md:inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-white/85 hover:bg-white/10"
            >
              Plans
            </a>

            <SignedOut>
              <SignInButton mode="modal">
                <button className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>

            <SignedIn>
              <div className="flex items-center gap-3">
                {displayName ? (
                  <span className="hidden sm:inline max-w-[180px] truncate text-sm text-white/80">
                    {displayName}
                  </span>
                ) : null}
                <Link
                  href="/product"
                  className="inline-flex items-center justify-center rounded-xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
                >
                  Go to app
                </Link>
                <UserButton afterSignOutUrl="/" />
              </div>
            </SignedIn>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="mx-auto max-w-6xl px-4 pt-16 pb-10">
        <div className="grid items-center gap-10 md:grid-cols-2">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-white/80">
              <span className="h-2 w-2 rounded-full bg-emerald-400/80" />
              New: agentic diff insights + reports
            </div>

            <h1 className="mt-4 text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
              Generate high-conviction ideas
              <span className="text-white/70"> tailored to your market.</span>
            </h1>

            <p className="mt-4 text-base text-white/70 sm:text-lg">
              IdeaGen turns your constraints, industry, and persona into structured, decision-ready business ideas.
              Compare multiple LLMs, get recommended combinations, and export polished outputs.
            </p>

            <div className="mt-6 flex flex-col gap-3 sm:flex-row">
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="inline-flex w-full items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 sm:w-auto">
                    Get started free
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <Link
                  href="/product"
                  className="inline-flex w-full items-center justify-center rounded-2xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-700 sm:w-auto"
                >
                  Generate ideas now
                </Link>
              </SignedIn>

              {/* See the app: must sign in first */}
              <SignedOut>
                <SignInButton mode="modal">
                  <button className="inline-flex w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-white/85 hover:bg-white/10 sm:w-auto">
                    See the app
                  </button>
                </SignInButton>
              </SignedOut>
              <SignedIn>
                <Link
                  href="/product"
                  className="inline-flex w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold text-white/85 hover:bg-white/10 sm:w-auto"
                >
                  See the app
                </Link>
              </SignedIn>
            </div>

            <div className="mt-6 grid grid-cols-3 gap-3 text-xs text-white/70">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                <div className="text-white font-semibold">Multi‑model</div>
                <div className="mt-1 text-white/60">Compare outputs</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                <div className="text-white font-semibold">Agentic</div>
                <div className="mt-1 text-white/60">Retries + fallbacks</div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
                <div className="text-white font-semibold">Exportable</div>
                <div className="mt-1 text-white/60">PDF + email</div>
              </div>
            </div>
          </div>

          {/* Preview Card */}
          <div className="relative">
            <div className="absolute -inset-6 rounded-[32px] bg-[radial-gradient(circle_at_30%_30%,rgba(59,130,246,0.25),transparent_55%),radial-gradient(circle_at_80%_20%,rgba(99,102,241,0.22),transparent_60%)] blur-2xl" />
            <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-white/5 shadow-2xl">
              <div className="flex items-center justify-between border-b border-white/10 bg-black/20 px-5 py-4">
                <div className="text-sm font-semibold text-white">Idea Workspace</div>
                <div className="flex items-center gap-2 text-xs text-white/60">
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5">Premium</span>
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5">PDF</span>
                  <span className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5">Email</span>
                </div>
              </div>

              <div className="p-5">
                <div className="grid gap-3">
                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="text-xs text-white/60">Inputs</div>
                    <div className="mt-2 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-white/80">
                        Industry: Healthcare SaaS
                      </div>
                      <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-white/80">
                        Persona: Operator
                      </div>
                      <div className="col-span-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-white/80">
                        Constraints: budget, team size, urgency
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                    <div className="flex items-center justify-between">
                      <div className="text-xs text-white/60">Generated idea</div>
                      <div className="text-[11px] text-white/60">gpt‑5‑nano • gemini • deepseek</div>
                    </div>
                    <div className="mt-2 space-y-2">
                      <div className="h-3 w-5/6 rounded bg-white/10" />
                      <div className="h-3 w-11/12 rounded bg-white/10" />
                      <div className="h-3 w-4/5 rounded bg-white/10" />
                      <div className="h-3 w-2/3 rounded bg-white/10" />
                    </div>
                    <div className="mt-4 inline-flex items-center gap-2 rounded-xl bg-blue-600 px-3 py-2 text-xs font-semibold text-white">
                      Generate Ideas
                      <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    </div>
                  </div>
                </div>
              </div>

              <div className="border-t border-white/10 bg-black/20 px-5 py-3 text-xs text-white/60">
                Cutting-edge UI • designed for portfolio + monetization
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-4 py-14">
        <div className="flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white">IdeaGen features</h2>
            <p className="mt-1 text-sm text-white/70">Built for fast iteration, evaluation, and polished delivery.</p>
          </div>

          {/* Open product: must sign in first */}
          <SignedOut>
            <SignInButton mode="modal">
              <button className="hidden sm:inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-white/85 hover:bg-white/10">
                Open product →
              </button>
            </SignInButton>
          </SignedOut>
          <SignedIn>
            <Link
              href="/product"
              className="hidden sm:inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm font-semibold text-white/85 hover:bg-white/10"
            >
              Open product →
            </Link>
          </SignedIn>
        </div>

        <div className="mt-8 grid gap-4 md:grid-cols-3">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Structured idea output</div>
            <p className="mt-2 text-sm text-white/70">
              Generate decision-ready sections (problem, scope, moat, pricing, metrics, plan) with constraints applied.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Multi-model comparison</div>
            <p className="mt-2 text-sm text-white/70">
              Select multiple LLMs and compare results side-by-side in a clean tabbed viewer.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Recommend Combination (Premium)</div>
            <p className="mt-2 text-sm text-white/70">
              Get a recommended persona + constraints pairing, plus reasons you can reuse in messaging.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Constraints + personas</div>
            <p className="mt-2 text-sm text-white/70">
              Choose guardrails and tone. Premium unlocks multi-select constraints and full persona set.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Export report (Premium)</div>
            <p className="mt-2 text-sm text-white/70">
              Download PDF or email the output—ideal for sharing with cofounders, clients, or your own pipeline.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Saved results library</div>
            <p className="mt-2 text-sm text-white/70">
              Save multi-model runs by date and reload them any time to continue, export, or email.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Usage + storage tracking</div>
            <p className="mt-2 text-sm text-white/70">
              Live view of token, API, email, and saved-results storage limits with automatic resets.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Agentic Diff Mode</div>
            <p className="mt-2 text-sm text-white/70">
              Compare two saved runs with DeepSeek-powered insights and a clear winner recommendation.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Rank Reports (on demand)</div>
            <p className="mt-2 text-sm text-white/70">
              Select runs, generate a ranked executive summary, and export as PDF or email in one click.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-5">
            <div className="text-sm font-semibold text-white">Agentic reliability</div>
            <p className="mt-2 text-sm text-white/70">
              Monitoring-friendly logging + retry behavior for slow responses, and fallbacks for provider errors.
            </p>
          </div>
        </div>
      </section>

      {/* Plans */}
      <section id="pricing" className="mx-auto max-w-6xl px-4 pb-16">
        <div className="rounded-[32px] border border-white/10 bg-white/5 p-6 md:p-8">
          <div className="flex flex-col gap-2">
            <h2 className="text-2xl font-bold text-white">Plans</h2>
            <p className="text-sm text-white/70">
              Start free. Upgrade when you need multi-model comparison, recommendations, and export.
            </p>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <div className="rounded-3xl border border-white/10 bg-black/20 p-6">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-white">Free</div>
                <span className="text-xs text-white/60">Limited</span>
              </div>
              <ul className="mt-4 space-y-2 text-sm text-white/70">
                <li>• Generate ideas</li>
                <li>• 1 model at a time</li>
                <li>• Constraint selection limited</li>
                <li>• Persona limited</li>
                <li>• Saved results (100MB)</li>
                <li>• Agentic Diff Mode</li>
                <li>• Rank Reports (PDF only)</li>
                <li>• No recommend combination</li>
                <li>• No PDF/email export</li>
              </ul>
              <div className="mt-5">
                <SignedOut>
                  <SignInButton mode="modal">
                    <button className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white/85 hover:bg-white/10">
                      Start free
                    </button>
                  </SignInButton>
                </SignedOut>
                <SignedIn>
                  <Link
                    href="/product"
                    className="inline-flex w-full items-center justify-center rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-semibold text-white/85 hover:bg-white/10"
                  >
                    Open app
                  </Link>
                </SignedIn>
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-white/10 p-6">
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-white">Premium</div>
                <span className="text-xs rounded-full border border-white/10 bg-white/10 px-2 py-0.5 text-white/80">
                  Recommended
                </span>
              </div>
              <ul className="mt-4 space-y-2 text-sm text-white/70">
                <li>• Multi-model comparison</li>
                <li>• Multi-select constraints</li>
                <li>• Full persona set</li>
                <li>• Recommend Combination</li>
                <li>• Saved results (1GB)</li>
                <li>• Agentic Diff Mode</li>
                <li>• Rank Reports (PDF + email)</li>
                <li>• PDF export + email delivery</li>
              </ul>
              <div className="mt-5">
                <SignedOut>
                  <SignInButton mode="modal">
                    <button className="w-full rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700">
                      Upgrade
                    </button>
                  </SignInButton>
                </SignedOut>
                <SignedIn>
                  <Link
                    href="/product"
                    className="inline-flex w-full items-center justify-center rounded-2xl bg-blue-600 px-4 py-3 text-sm font-semibold text-white hover:bg-blue-700"
                  >
                    Upgrade
                  </Link>
                </SignedIn>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10 bg-black/20">
        <div className="mx-auto max-w-6xl px-4 py-8">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-white/70">© {new Date().getFullYear()} IdeaGen</div>
            <div className="text-sm text-white/70">RG</div>
          </div>
        </div>
      </footer>
    </main>
  );
}
