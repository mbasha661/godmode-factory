import "./globals.css";
import type { Metadata, Viewport } from "next";

export const metadata: Metadata = {
  title: "God Mode AI Software Factory",
  description: "Turn app ideas into planned, tested, packaged software projects.",
};
export const viewport: Viewport = { width: "device-width", initialScale: 1 };

const themeInit = `(function(){try{var t=localStorage.getItem('gmf-theme');if(t){document.documentElement.dataset.theme=t;}}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInit }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
