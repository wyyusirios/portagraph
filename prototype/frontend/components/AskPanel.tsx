'use client';

import { useState } from 'react';
import { api, type Answer } from '@/lib/api';

/** Чат с AI-ассистентом: каждый ответ сопровождается ссылками на файлы и строки. */
export default function AskPanel({ projectId }: { projectId: number }) {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<{ q: string; a: Answer }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const a = await api.ask(projectId, question, history.at(-1)?.a.sessionId);
      setHistory((h) => [...h, { q: question, a }]);
      setQuestion('');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex-1 space-y-4 overflow-y-auto">
        {history.map(({ q, a }) => (
          <div key={a.messageId} className="space-y-2">
            <p className="ml-auto max-w-xl rounded-lg bg-brand-500 p-3 text-white">{q}</p>
            <div className="max-w-2xl rounded-lg border bg-white p-3">
              <p className="whitespace-pre-wrap">{a.text}</p>
              {a.citations.length > 0 && (
                <ul className="mt-2 space-y-1 text-sm text-brand-600">
                  {a.citations.map((c) => (
                    <li key={`${c.fileId}-${c.startLine}`}>📄 {c.path}:{c.startLine}–{c.endLine}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <form onSubmit={submit} className="flex gap-2">
        <input
          className="flex-1 rounded-lg border px-3 py-2"
          placeholder="Например: где проверяется JWT и какие сервисы его используют?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button disabled={busy} className="rounded-lg bg-brand-500 px-4 py-2 text-white disabled:opacity-50">
          {busy ? 'Думаю…' : 'Спросить'}
        </button>
      </form>
    </div>
  );
}
