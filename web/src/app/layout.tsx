import type { Metadata } from "next";
import { Hanken_Grotesk, Instrument_Serif } from "next/font/google";
import { AuthGate } from "@/components/AuthGate";
import "./globals.css";

const hanken = Hanken_Grotesk({ subsets: ["latin"], variable: "--font-hanken" });
const instrument = Instrument_Serif({ subsets: ["latin"], weight: "400", style: ["normal", "italic"], variable: "--font-instrument" });

export const metadata: Metadata = {
  title: "Wayfarer · AI trip planner",
  description: "Describe a trip in a sentence. Get real flights, hotels and a day-by-day plan.",
  icons: { icon: "/icon.svg" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${hanken.variable} ${instrument.variable}`}>
      <body className="min-h-dvh">
        {children}
        <AuthGate />
      </body>
    </html>
  );
}
