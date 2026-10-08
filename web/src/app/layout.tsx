import type { Metadata } from "next";
import { Archivo } from "next/font/google";
import "./globals.css";

// One family. Its width axis gives the condensed codes and the wide title.
const archivo = Archivo({
  variable: "--font-archivo",
  subsets: ["latin"],
  axes: ["wdth"],
});

export const metadata: Metadata = {
  title: "Matchweek",
  description: "Weekly football predictions, locked before kickoff and checked against what happened.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${archivo.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">{children}</body>
    </html>
  );
}
