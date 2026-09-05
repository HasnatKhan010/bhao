import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bhao — بھاؤ",
  description:
    "What things cost in Pakistan, weekly — and what they'll cost next week.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return children;
}
