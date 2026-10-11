import type { ReactNode } from 'react';

/** A single metric card for the Overview activity summary. */
export default function StatCard({
  icon,
  label,
  value,
  sub,
  footer,
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-surface p-5 shadow-card">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-ink-muted">{label}</span>
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-50 text-base"
        >
          {icon}
        </span>
      </div>
      <div className="text-2xl font-bold text-ink">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-muted">{sub}</div>}
      {footer && <div className="mt-3 text-xs text-ink-muted">{footer}</div>}
    </div>
  );
}
