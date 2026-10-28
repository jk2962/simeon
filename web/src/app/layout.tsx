import type { Metadata } from "next";
import { Archivo, Unbounded } from "next/font/google";
import "./globals.css";

// One family. Its width axis gives the condensed codes and the wide title.
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
});

// A naturally wide face for the wordmark alone.
const unbounded = Unbounded({
  variable: "--font-unbounded",
  subsets: ["latin"],
  weight: "700",
});

export const metadata: Metadata = {
  title: "Simeon",
  description: "Weekly football predictions, locked before kickoff and checked against what happened.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${archivo.variable} ${unbounded.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
