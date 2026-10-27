'use client';

import { useEffect, useState } from 'react';
import { api, type Project } from '@/lib/api';

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.projects().then(setProjects).catch((e: Error) => setError(e.message));
  }, []);

  return (
    <section className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Мои проекты</h1>
        <a href="/projects/new" className="rounded-lg bg-brand-500 px-4 py-2 text-white">+ Новый проект</a>
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <div className="grid gap-4 sm:grid-cols-2">
        {projects.map((p) => (
          <a key={p.id} href={`/projects/${p.id}/map`} className="rounded-xl border bg-white p-4 hover:shadow">
            <h2 className="font-medium">{p.name}</h2>
            <p className="mt-1 text-sm text-slate-500">{p.description ?? 'Без описания'}</p>
            <p className="mt-3 text-xs text-slate-400">Репозиториев: {p.repositoryCount}</p>
          </a>
        ))}
      </div>
    </section>
  );
}
