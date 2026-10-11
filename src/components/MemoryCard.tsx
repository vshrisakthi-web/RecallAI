import { Link } from 'react-router-dom';
import SourceBadge from './SourceBadge';
import type { Memory } from '../data/types';

/**
 * A memory preview card used on Overview and Memory Timeline. Links to the
 * Memory Detail route. Purely presentational — data comes from props.
 */
export default function MemoryCard({ memory }: { memory: Memory }) {
  return (
    <Link
      to={`/memory/${memory.id}`}
      className="group block rounded-2xl border border-slate-100 bg-surface p-5 shadow-card transition hover:border-brand-100 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
      <div className="mb-3 flex items-center justify-between">
        <SourceBadge type={memory.sourceType} />
        <span className="inline-flex items-center gap-1 text-xs font-medium text-safe-700">
          <span aria-hidden="true">💾</span> Local SSD
        </span>
      </div>

      <h3 className="mb-1 text-base font-semibold leading-snug text-ink group-hover:text-brand-700">
        {memory.title}
      </h3>

      <p className="mb-3 text-xs text-ink-muted">
        {memory.sourceName} • {memory.capturedLabel}
      </p>

      <p className="mb-3 text-sm leading-relaxed text-ink-muted">{memory.excerpt}</p>

      <div className="flex flex-wrap gap-1.5">
        {memory.tags.map((tag) => (
          <span key={tag} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
            {tag}
          </span>
        ))}
      </div>

      {memory.extractNote && (
        <p className="mt-3 text-xs italic text-slate-400">{memory.extractNote}</p>
      )}
    </Link>
  );
}
