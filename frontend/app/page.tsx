import Twin from '@/components/twin';

export default function Home() {
  return (
    <main className="h-screen overflow-hidden bg-[radial-gradient(circle_at_top,_#f8fafc,_#eef2f7_35%,_#e6ecf4_70%,_#e0e7f0_100%)]">
      <div className="container mx-auto px-4 pt-8 pb-4 h-full">
        <div className="max-w-5xl mx-auto h-full flex flex-col">
          <div className="flex flex-col items-center text-center gap-2 mb-6 shrink-0">
            <span className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1 text-[10px] uppercase tracking-[0.28em] text-slate-500 shadow-sm">
              Live agent
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400/60" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
            </span>
            <h1 className="text-[40px] sm:text-5xl font-semibold text-slate-900 font-display tracking-[0.02em]">
              AI in Production
            </h1>
            <div className="h-px w-16 bg-gradient-to-r from-transparent via-slate-400/60 to-transparent" />
            <p className="text-[15px] sm:text-lg text-slate-600 max-w-2xl leading-relaxed">
              A digital assistant for shipping and operating LLM systems—RAG, agents, and infra.
            </p>
          </div>

          <div className="transition-all duration-300 ease-out flex-1 min-h-0 flex flex-col relative">
            <div className="mt-auto">
              <Twin />
            </div>
          </div>
        </div>
      </div>
      <footer className="fixed bottom-3 left-1/2 z-50 -translate-x-1/2 text-[11px] text-slate-600/90">
        <span className="font-medium text-slate-700/90">Rhye Gacillos</span>
        <span className="mx-2 text-slate-400/90">·</span>
        <a
          href="mailto:gacillos.rhye@gmail.com"
          className="text-slate-700/90 underline decoration-slate-300/90 underline-offset-2 hover:text-slate-900"
        >
          gacillos.rhye@gmail.com
        </a>
      </footer>
    </main>
  );
}
