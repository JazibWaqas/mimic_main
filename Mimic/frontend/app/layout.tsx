
import type { Metadata } from "next";
import { Inter, JetBrains_Mono, Cormorant_Garamond, Playfair_Display, DM_Serif_Display, Lora, Bebas_Neue, Montserrat } from "next/font/google";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { Suspense } from "react";
import { Header } from "@/components/header";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const cormorantGaramond = Cormorant_Garamond({
  variable: "--font-cormorant-garamond",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600", "700"],
});

const playfairDisplay = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
});

const dmSerifDisplay = DM_Serif_Display({
  variable: "--font-dm-serif",
  subsets: ["latin"],
  weight: ["400"],
});

const lora = Lora({
  variable: "--font-lora",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

const bebasNeue = Bebas_Neue({
  variable: "--font-bebas",
  subsets: ["latin"],
  weight: ["400"],
});

const montserrat = Montserrat({
  variable: "--font-montserrat",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "MIMIC | Surgical Cinematic Synthesis",
  description:
    "An advanced AI editor that replicates the visual pacing and intent of any reference video.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${inter.variable} ${jetbrainsMono.variable} ${cormorantGaramond.variable} ${playfairDisplay.variable} ${dmSerifDisplay.variable} ${lora.variable} ${bebasNeue.variable} ${montserrat.variable} antialiased text-foreground selection:bg-indigo-500 selection:text-white`}
        suppressHydrationWarning
      >
        <div className="bg-mesh" />
        <Header />
        <main className="relative z-10">
          <Suspense fallback={<div className="min-h-screen bg-black" />}>
            {children}
          </Suspense>
        </main>
        <Toaster position="bottom-right" theme="dark" />
      </body>
    </html>
  );
}
