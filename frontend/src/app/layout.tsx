import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Noto_Sans_Kannada } from "next/font/google";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth/auth-context";
import { QueryClientProvider } from "@/lib/ask/query-client-provider";
import "./globals.css";

const inter = Inter({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

// Code-mixed voice transcripts (steering-docs/VOICE_INTAKE_STEERING.md §4) can
// contain Kannada script inline with Latin text — Inter alone has no Kannada
// glyphs, so this is layered in as a fallback in the font stack (globals.css).
const notoSansKannada = Noto_Sans_Kannada({
  variable: "--font-kannada",
  subsets: ["kannada"],
});

export const metadata: Metadata = {
  title: "KSP Ask Platform",
  description: "Karnataka State Police — Intelligent Conversational AI & Crime Analytics Platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${inter.variable} ${jetbrainsMono.variable} ${notoSansKannada.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <QueryClientProvider>
          <AuthProvider>
            <TooltipProvider>{children}</TooltipProvider>
          </AuthProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}
