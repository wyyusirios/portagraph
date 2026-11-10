'use client';

import { useState } from 'react';
import SystemMap from '@/components/SystemMap';

export default function MapPage({ params }: { params: { id: string } }) {
  const [mode, setMode] = useState<'overview' | 'detailed'>('overview');
  const [selected, setSelected] = useState<string | null>(null);
  const projectId = Number(params.id);

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        {(['overview', 'detailed'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-lg px-3 py-1.5 text-sm ${mode === m ? 'bg-brand-500 text-white' : 'border bg-white'}`}
          >
            {m === 'overview' ? 'Карта системы' : 'Граф зависимостей'}
          </button>
        ))}
        <a href={`/projects/${projectId}/assistant`} className="ml-auto text-sm text-brand-600">AI-ассистент →</a>
      </div>
      <SystemMap projectId={projectId} mode={mode} onSelect={setSelected} />
      {selected && <p className="text-sm text-slate-500">Выбран узел #{selected}</p>}
    </section>
  );
}
