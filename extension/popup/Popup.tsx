import { useCallback, useEffect, useMemo, useState } from 'react';
import { send } from './messaging';
import type { CaptureRecord, CaptureState, TabInfo } from '../types';

/**
 * RecallAI extension popup (Module 2). A compact ~360px card matching the
 * approved design. Talks to the background worker via typed messages; capture
 * is always user-triggered. Shows Active/Paused/Stopped states, the active tab
 * context, a Capture button, recent captures, and clear permission/error states.
 */

type Phase = 'idle' | 'capturing';
const BACKEND_STORAGE_KEY = 'recallai.backend';
const BACKEND_ORIGIN = 'http://127.0.0.1:8000/*';
const BACKEND_ENDPOINT = 'http://127.0.0.1:8000/api/v1/ingest/browser';

const statePill: Record<CaptureState, string> = {
  active: 'bg-safe-100 text-safe-700',
  paused: 'bg-warn-100 text-warn-700',
  stopped: 'bg-slate-100 text-slate-600',
};

const stateDot: Record<CaptureState, string> = {
  active: 'bg-safe-500',
  paused: 'bg-warn-500',
  stopped: 'bg-slate-400',
};

export default function Popup() {
  const [state, setState] = useState<CaptureState>('active');
  const [tab, setTab] = useState<TabInfo | null>(null);
  const [recent, setRecent] = useState<CaptureRecord[]>([]);
  const [phase, setPhase] = useState<Phase>('idle');
  const [message, setMessage] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [syncEnabled, setSyncEnabled] = useState(false);
  const [syncLoading, setSyncLoading] = useState(true);

  const domain = useMemo(() => {
    try {
      return tab?.url ? new URL(tab.url).hostname : '';
    } catch {
      return '';
    }
  }, [tab?.url]);

  const refresh = useCallback(async () => {
    const [stateRes, tabRes, recentRes] = await Promise.all([
      send<'GET_STATE'>({ type: 'GET_STATE' }),
      send<'GET_ACTIVE_TAB'>({ type: 'GET_ACTIVE_TAB' }),
      send<'LIST_RECENT'>({ type: 'LIST_RECENT', limit: 5 }),
    ]);
    if (stateRes.ok) setState(stateRes.data.state);
    if (tabRes.ok) setTab(tabRes.data.tab);
    if (recentRes.ok) setRecent(recentRes.data.records);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    void Promise.all([
      chrome.storage.local.get(BACKEND_STORAGE_KEY),
      chrome.permissions.contains({ origins: [BACKEND_ORIGIN] }),
    ])
      .then(([bag, permissionGranted]) => {
        const config = bag[BACKEND_STORAGE_KEY] as { enabled?: boolean } | undefined;
        const enabled = config?.enabled === true && permissionGranted;
        setSyncEnabled(enabled);
        if (config?.enabled && !permissionGranted) {
          return chrome.storage.local.set({
            [BACKEND_STORAGE_KEY]: { endpoint: BACKEND_ENDPOINT, enabled: false },
          });
        }
        return undefined;
      })
      .catch(() => setMessage({ kind: 'err', text: 'Could not read local API settings.' }))
      .finally(() => setSyncLoading(false));
  }, []);

  const setLocalApiSync = async (enabled: boolean) => {
    try {
      if (!enabled) {
        await chrome.storage.local.set({
          [BACKEND_STORAGE_KEY]: { endpoint: BACKEND_ENDPOINT, enabled: false },
        });
        setSyncEnabled(false);
        setMessage(null);
        return;
      }

      const granted = await chrome.permissions.request({ origins: [BACKEND_ORIGIN] });
      if (!granted) {
        setMessage({ kind: 'err', text: 'Local API permission was not granted. Captures remain local.' });
        return;
      }
      await chrome.storage.local.set({
        [BACKEND_STORAGE_KEY]: { endpoint: BACKEND_ENDPOINT, enabled: true },
      });
      setSyncEnabled(true);
      setMessage({ kind: 'ok', text: 'Local API sync is enabled for future captures.' });
    } catch {
      setMessage({ kind: 'err', text: 'Could not update local API settings. Captures remain local.' });
    }
  };

  const setCaptureState = async (next: CaptureState) => {
    const res = await send<'SET_STATE'>({ type: 'SET_STATE', state: next });
    if (res.ok) {
      setState(res.data.state);
      setMessage(null);
    } else {
      setMessage({ kind: 'err', text: res.error });
    }
  };

  const doCapture = async () => {
    if (phase === 'capturing') return; // disable repeated submissions
    if (!tab?.id) {
      setMessage({ kind: 'err', text: 'No active tab to capture.' });
      return;
    }
    setPhase('capturing');
    setMessage(null);
    const captureType = selectionMode ? 'selection' : 'full-page';
    const res = await send<'CAPTURE'>({ type: 'CAPTURE', tab, captureType });
    setPhase('idle');
    if (res.ok) {
      const r = res.data.record;
      setMessage({
        kind: 'ok',
        text: `Captured “${r.title}” · ${r.contentLength} chars · ${r.captureType}`,
      });
      void refresh();
    } else {
      setMessage({ kind: 'err', text: res.error });
    }
  };

  const canCaptureNow = state === 'active';

  return (
    <div className="w-[360px] bg-surface text-ink">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <span
            aria-hidden="true"
            className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white"
          >
            ↻
          </span>
          <span className="text-sm font-bold">RecallAI</span>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-safe-100 px-2 py-0.5 text-xs font-medium text-safe-700">
          🔒 Data stored locally
        </span>
      </header>

      {/* Capture status + controls */}
      <section className="px-4 pt-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            Capture status
          </span>
          <span
            data-testid={`popup-state-${state}`}
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${statePill[state]}`}
          >
            <span className={`inline-block h-2 w-2 rounded-full ${stateDot[state]}`} aria-hidden="true" />
            {state === 'active' ? 'Active Capture' : state === 'paused' ? 'Paused' : 'Stopped'}
          </span>
        </div>

        {state === 'stopped' ? (
          <button
            type="button"
            onClick={() => void setCaptureState('active')}
            className="w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600"
          >
            ▶ Start Capture
          </button>
        ) : (
          <div className="flex gap-2">
            {state === 'active' ? (
              <button
                type="button"
                onClick={() => void setCaptureState('paused')}
                className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold hover:bg-slate-50"
              >
                ⏸ Pause
              </button>
            ) : (
              <button
                type="button"
                onClick={() => void setCaptureState('active')}
                className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold hover:bg-slate-50"
              >
                ▶ Resume
              </button>
            )}
            <button
              type="button"
              onClick={() => void setCaptureState('stopped')}
              className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold hover:bg-slate-50"
            >
              ⏹ Stop
            </button>
          </div>
        )}
      </section>

      {/* Active tab context */}
      <section className="mx-4 mt-4 rounded-xl border border-slate-100 bg-slate-50 p-3">
        <div className="mb-1 text-xs font-medium text-ink-muted">🌐 Active tab</div>
        {tab?.title ? (
          <>
            <div className="truncate text-sm font-semibold" title={tab.title}>
              {tab.title}
            </div>
            <div className="truncate text-xs text-ink-muted">{domain || '—'}</div>
          </>
        ) : (
          <div className="text-sm text-ink-muted">
            No accessible tab. Chrome restricts some pages (chrome://, Web Store).
          </div>
        )}
      </section>

      {/* Capture controls */}
      <section className="px-4 py-4">
        <label className="mb-2 flex cursor-pointer items-center gap-2 text-xs text-ink-muted">
          <input
            type="checkbox"
            checked={selectionMode}
            onChange={(e) => setSelectionMode(e.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
          Capture only my selected text
        </label>
        <button
          type="button"
          onClick={() => void doCapture()}
          disabled={!canCaptureNow || phase === 'capturing' || !tab?.id}
          className="w-full rounded-xl bg-brand-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {phase === 'capturing'
            ? 'Capturing…'
            : selectionMode
              ? '💾 Capture selection'
              : '💾 Capture this page'}
        </button>
        {!canCaptureNow && (
          <p className="mt-2 text-center text-xs text-ink-muted">
            {state === 'paused'
              ? 'Capture is paused — resume to capture.'
              : 'Capture is stopped — start to capture.'}
          </p>
        )}

        {message && (
          <p
            role={message.kind === 'err' ? 'alert' : 'status'}
            className={`mt-3 rounded-lg px-3 py-2 text-xs ${
              message.kind === 'err'
                ? 'bg-red-50 text-red-700'
                : 'bg-safe-50 text-safe-700'
            }`}
          >
            {message.text}
          </p>
        )}
      </section>

      {/* Optional local API delivery: permission is requested only after explicit opt-in. */}
      <section className="mx-4 mb-3 rounded-xl border border-slate-100 p-3">
        <label className="flex cursor-pointer items-center justify-between gap-3 text-xs font-medium text-ink">
          <span>Send captures to local RecallAI API</span>
          <input
            type="checkbox"
            checked={syncEnabled}
            disabled={syncLoading}
            onChange={(event) => void setLocalApiSync(event.target.checked)}
            className="h-4 w-4 rounded border-slate-300"
          />
        </label>
        <p className="mt-1 text-xs text-ink-muted">
          Optional. Sends only to this device at 127.0.0.1:8000 after capture.
        </p>
      </section>

      {/* Recent captures */}
      <section className="border-t border-slate-100 px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-ink-muted">Recent captures</span>
          <span className="text-xs text-ink-muted">{recent.length}</span>
        </div>
        {recent.length === 0 ? (
          <p className="text-xs text-ink-muted">No captures yet. Click Capture to save one.</p>
        ) : (
          <ul className="space-y-1.5">
            {recent.map((r) => (
              <li
                key={r.id}
                className="flex items-center justify-between rounded-lg border border-slate-100 px-2.5 py-2 text-xs"
              >
                <span className="truncate">
                  {r.captureType === 'selection' ? '✂️' : '📄'} {r.title}
                </span>
                <span className="ml-2 shrink-0 text-ink-muted">{r.contentLength}c</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Footer */}
      <footer className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-ink-muted">
        <span>{syncEnabled ? 'Local API sync enabled.' : 'Captures stay in local storage.'}</span>
        <span>Local-first</span>
      </footer>
    </div>
  );
}

