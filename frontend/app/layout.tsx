import type { Metadata } from 'next';
import './globals.css';
import { ToastContainer } from '@/components/ui/Toast';

export const metadata: Metadata = {
  title: { default: 'Arada Intelligence OS', template: '%s · Arada' },
  description: 'Content intelligence platform with ML, webhooks, and analytics',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <ToastContainer />
      </body>
    </html>
  );
}
