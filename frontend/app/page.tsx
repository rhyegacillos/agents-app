import Twin from '@/components/twin';

export default function Home() {
  return (
    <main className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top,_#f8fafc,_#eef2f7_35%,_#e6ecf4_70%,_#e0e7f0_100%)]">
      <div className="container mx-auto px-4 py-8 h-full">
        <div className="max-w-5xl mx-auto h-full flex flex-col">
          <div className="flex flex-col items-center text-center gap-3 mb-6 shrink-0">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1 text-xs uppercase tracking-[0.2em] text-slate-500 shadow-sm">
              Live agent
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            </span>
            <h1 className="text-4xl sm:text-5xl font-semibold text-slate-900 font-display">
              AI in Production
            </h1>
            <p className="text-base sm:text-lg text-slate-600 max-w-2xl">
              A focused, always‑on digital assistant for deployment guidance,
              troubleshooting, and live walkthroughs.
            </p>
          </div>

          <div className="transition-all duration-300 ease-out flex-1 min-h-0 flex flex-col relative">
            <div className="mt-auto">
              <Twin />
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
