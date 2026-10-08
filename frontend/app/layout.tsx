import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "SUS Explorer", description: "Explore dados públicos de saúde com proveniência." };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body>{children}</body></html>;
}
