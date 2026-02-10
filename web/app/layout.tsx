import type { Metadata } from "next";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
});

const ibmPlexMono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Autonomous Trader",
  description: "FastAPI + Next.js dashboard for an agentic trading simulation",
  icons: {
    icon: "/favicon.ico",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${spaceGrotesk.variable} ${ibmPlexMono.variable}`}>
        {children}
        <footer className="appFootnote" aria-label="App footnote">
          <span className="appFootnoteName">Rhye Gacillos</span>
          <span className="appFootnoteSep">·</span>
          <a className="appFootnoteEmail" href="mailto:gacillos.rhye@gmail.com">
            gacillos.rhye@gmail.com
          </a>
        </footer>
      </body>
    </html>
  );
}
