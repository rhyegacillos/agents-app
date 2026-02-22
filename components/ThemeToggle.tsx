"use client"

import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

function applyTheme(theme: Theme) {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.style.colorScheme = theme;
}

export default function ThemeToggle() {
    const [theme, setTheme] = useState<Theme>('light');

    useEffect(() => {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        if (stored === 'light' || stored === 'dark') {
            setTheme(stored);
            applyTheme(stored);
            return;
        }
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        const initial = prefersDark ? 'dark' : 'light';
        setTheme(initial);
        applyTheme(initial);
    }, []);

    function toggleTheme() {
        const next = theme === 'dark' ? 'light' : 'dark';
        setTheme(next);
        window.localStorage.setItem(STORAGE_KEY, next);
        applyTheme(next);
    }

    return (
        <div className="flex items-center gap-2 rounded-full border border-slate-200 bg-white/85 px-2 py-1.5 shadow-sm backdrop-blur sm:px-3 sm:py-2 dark:border-slate-700 dark:bg-slate-900/85">
            <span className="hidden text-[10px] font-semibold uppercase tracking-[0.2em] text-slate-500 sm:inline dark:text-slate-400">
                Current Theme:
            </span>
            <button
                type="button"
                onClick={toggleTheme}
                aria-pressed={theme === 'dark'}
                className="min-h-11 rounded-full bg-slate-900 px-4 py-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-white transition hover:bg-slate-800 dark:bg-emerald-500 dark:text-slate-950 dark:hover:bg-emerald-400"
            >
                {theme === 'dark' ? 'Dark' : 'Light'}
            </button>
        </div>
    );
}
