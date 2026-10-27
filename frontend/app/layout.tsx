import './globals.css';
import type { ReactNode } from 'react';

export const metadata = { title: 'PortaGraph', description: 'Анализ и визуализация программных проектов' };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <header className="flex items-center gap-3 border-b bg-white px-6 py-3">
          <span className="text-lg font-semibold text-brand-900">PortaGraph</span>
          <nav className="ml-6 flex gap-4 text-sm text-slate-600">
            <a href="/">Проекты</a>
          </nav>
        </header>
        <main className="p-6">{children}</main>
      </body>
    </html>
  );
}
