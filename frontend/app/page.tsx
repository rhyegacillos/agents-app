import Twin from '@/components/twin';

export default function Home() {
  return (
    <main className="h-[100dvh] overflow-x-hidden bg-[radial-gradient(circle_at_top,_#f8fafc,_#eef2f7_35%,_#e6ecf4_70%,_#e0e7f0_100%)]">
      <div className="container mx-auto h-full px-3 pt-4 pb-3 sm:px-4 sm:pt-8 sm:pb-4">
        <div className="max-w-5xl mx-auto h-full flex flex-col">
          <div className="mb-3 flex shrink-0 flex-col items-center gap-1 text-center sm:mb-6 sm:gap-1.5">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/75 px-3.5 py-1.5 text-[11px] uppercase tracking-[0.24em] text-slate-500 shadow-sm">
              Live agent
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
            </span>
            <h1 className="font-display text-[26px] font-semibold tracking-[0.02em] text-slate-900 sm:text-5xl">
              Serverless Agentic AI Digital Assistant
            </h1>
            <div className="hidden h-px w-16 bg-gradient-to-r from-transparent via-slate-400/60 to-transparent sm:block" />
            <p className="hidden max-w-2xl text-[15px] leading-relaxed text-slate-600 sm:block sm:text-lg">
              Serverless AI assistant with tool orchestration (search, PDF, email, uploads) and user-approved memory.
              Includes async jobs, daily quotas, and AWS observability.
            </p>
          </div>

          <div className="transition-all duration-300 ease-out flex-1 min-h-0 flex flex-col relative">
            <div className="mt-auto">
              <Twin />
            </div>
          </div>
        </div>
      </div>
      <footer className="fixed bottom-0 left-1/2 z-50 -translate-x-1/2 py-1 text-[9px] tracking-[0.2em] text-slate-500/55">
        RG
      </footer>
    </main>
  );
}
