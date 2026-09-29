import type { Metadata, Viewport } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';
import './extended.css';
import './team.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  title: 'Billing Control — Gestão odontológica',
  description: 'Gestão segura de pacientes e anamneses para clínicas odontológicas.',
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000'),
  openGraph: {
    title: 'Billing Control',
    description: 'Gestão odontológica simples e segura',
    images: [{ url: '/og.png', width: 1200, height: 630, alt: 'Billing Control — Gestão odontológica simples e segura' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Billing Control',
    description: 'Gestão odontológica simples e segura',
    images: ['/og.png'],
  },
};

export const viewport: Viewport = {
  themeColor: '#7B2FF2',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
