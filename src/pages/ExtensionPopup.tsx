import { useState } from 'react';
import { Link } from 'react-router-dom';
import { initialCaptureState } from '../data/mockData';
import type { CaptureState } from '../data/types';

/**
 * Chrome extension popup — a compact ~360px card with three capture states:
 * ACTIVE (Pause / Stop), PAUSED (Resume / Stop), STOPPED (Start Capture).
 *
 * This is an isolated preview route (/popup). In a real build these become the
 * Manifest V3 extension popup entry point. Capture actions are mock UI state —
 * no real browser capture is performed.
 */

const stateConfig: Record<CaptureState, { label: string; pill: string; hint: string }> = {
  active: {
    label: 'Active',
    pill: 'bg-safe-100 text-safe-700',
    hint: 'Capture is running. This page will be saved.',
  },
  paused: {
    label: 'Paused',
    pill: 'bg-warn-100 text-warn-700',
    hint: 'Capture is temporarily suspended.',
  },
  stopped: {
    label: 'Stopped',
    pill: 'bg-slate-100 text-slate-600',
    hint: 'Capture is inactive. Nothing is being saved.',
  },
};

export default function ExtensionPopup() {
  const [state, setState] = useState<CaptureState>(initialCaptureState);
  const [captured, setCaptured] = useState(false);
  const cfg = stateConfig[state];

  return (
    <div className="flex min-h-screen items-start justify-center bg-canvas p-6">
      <div className="w-[360px] overflow-hidden rounded-2xl border border-slate-100 bg-surface shadow-card">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white"
            >
              ↻
            </span>
            <span className="text-sm font-bold text-ink">RecallAI</span>
          </div>
          <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
            <span aria-hidden="true">🔒</span> Data stored locally
          </span>
        </div>

        {/* Capture status */}
        <div className="px-4 pt-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Capture status
            </span>
            <span
              data-testid={`popup-state-${state}`}
              className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${cfg.pill}`}
            >
              <span
                aria-hidden="true"
                className={`inline-block h-2 w-2 rounded-full ${
                  state === 'active'
                    ? 'bg-safe-500'
                    : state === 'paused'
                      ? 'bg-warn-500'
                      : 'bg-slate-400'
                }`}
              />
              {cfg.label}
            </span>
          </div>
          <p className="text-xs text-ink-muted">{cfg.hint}</p>
        </div>

        {/* Current website */}
        <div className="mx-4 mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
          <div className="text-xs font-medium text-ink-muted">Current website</div>
          <div className="mt-1 text-sm font-medium text-ink">arxiv.org</div>
          <div className="truncate text-xs text-ink-muted">
            MobileViT: Lightweight Vision Transformers
          </div>
        </div>

        {/* Controls */}
        <div className="px-4 py-4">
          {state === 'stopped' ? (
            <button
              type="button"
              onClick={() => setState('active')}
              className="w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600"
            >
              Start Capture
            </button>
          ) : (
            <div className="flex gap-2">
              {state === 'active' ? (
                <button
                  type="button"
                  onClick={() => setState('paused')}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:bg-slate-50"
                >
                  ⏸ Pause
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => setState('active')}
                  className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:bg-slate-50"
                >
                  ▶ Resume
                </button>
              )}
              <button
                type="button"
                onClick={() => setState('stopped')}
                className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-ink hover:bg-slate-50"
              >
                ⏹ Stop
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={() => setCaptured(true)}
            disabled={state !== 'active' || captured}
            className="mt-2 w-full rounded-xl border border-brand-200 bg-brand-50 px-4 py-2.5 text-sm font-semibold text-brand-700 hover:bg-brand-100 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {captured ? '✓ Page captured' : 'Capture this page'}
          </button>
        </div>

        {/* Recent capture summary */}
        <div className="border-t border-slate-100 px-4 py-3">
          <div className="mb-2 text-xs font-medium text-ink-muted">Recent captures</div>
          <ul className="space-y-1.5 text-xs text-ink">
            <li className="flex items-center justify-between">
              <span className="truncate">📄 Attention Mechanisms in ViTs</span>
              <span className="text-ink-muted">11:24 AM</span>
            </li>
            <li className="flex items-center justify-between">
              <span className="truncate">🔗 Q3 Design System RFC</span>
              <span className="text-ink-muted">10:45 AM</span>
            </li>
          </ul>
        </div>

        {/* Footer links */}
        <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs">
          <Link to="/panel" className="font-medium text-brand-700 hover:underline">
            Open companion →
          </Link>
          <Link to="/privacy" className="text-ink-muted hover:underline">
            Settings
          </Link>
        </div>
      </div>
    </div>
  );
}
