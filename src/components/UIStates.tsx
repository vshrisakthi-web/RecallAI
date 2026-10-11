import type { ReactNode } from 'react';

/**
 * Shared, reusable UI-state blocks so every screen handles loading / empty /
 * error / no-matches consistently (Task 1.9 + 1.10 requirement).
 */

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="flex items-center justify-center gap-3 rounded-2xl border border-slate-100 bg-surface p-10 text-ink-muted shadow-card"
    >
      <span
        aria-hidden="true"
        className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-brand-100 border-t-brand-600"
      />
      {label}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-200 bg-surface p-10 text-center shadow-card">
      <div aria-hidden="true" className="mb-3 text-3xl">
        🗂️
      </div>
      <h3 className="mb-1 text-base font-semibold text-ink">{title}</h3>
      <p className="mx-auto mb-4 max-w-md text-sm text-ink-muted">{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  message = 'Something went wrong.',
  onRetry,
}: {
  message?: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="rounded-2xl border border-red-100 bg-red-50 p-6 text-center shadow-card"
    >
      <div aria-hidden="true" className="mb-2 text-2xl">
        ⚠️
      </div>
      <h3 className="mb-1 text-base font-semibold text-red-700">Error</h3>
      <p className="mb-4 text-sm text-red-600">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
        >
          Try again
        </button>
      )}
    </div>
  );
}

export function NoMatchesState({ query }: { query: string }) {
  return (
    <div className="rounded-2xl border border-slate-100 bg-surface p-10 text-center shadow-card">
      <div aria-hidden="true" className="mb-3 text-3xl">
        🔍
      </div>
      <h3 className="mb-1 text-base font-semibold text-ink">No matches</h3>
      <p className="text-sm text-ink-muted">
        No memories match <span className="font-medium">“{query}”</span>. Try a different
        search or clear the filters.
      </p>
    </div>
  );
}
