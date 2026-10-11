import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { defaultPrivacySettings } from '../data/mockData';
import type { PrivacySettings as PrivacySettingsType } from '../data/types';

/**
 * Privacy Settings — capture preferences with plain-language explanations,
 * capture status, excluded/sensitive-page handling, and memory deletion controls.
 *
 * Design note: no Stitch export exists for this screen (Task 1.8 pending), so it
 * is built from docs/interface-specification.md and matches the shared design system.
 * No permission is implied as granted; controls are clearly labelled as preferences.
 */
export default function PrivacySettings() {
  const [settings, setSettings] = useState<PrivacySettingsType>(defaultPrivacySettings);
  const [newPattern, setNewPattern] = useState('');
  const [saved, setSaved] = useState(false);

  const toggle = (key: keyof PrivacySettingsType) => {
    setSettings((prev) => ({ ...prev, [key]: !prev[key] }));
    setSaved(false);
  };

  const addPattern = () => {
    const p = newPattern.trim();
    if (!p) return;
    setSettings((prev) => ({ ...prev, excludedPatterns: [...prev.excludedPatterns, p] }));
    setNewPattern('');
    setSaved(false);
  };

  const removePattern = (pattern: string) => {
    setSettings((prev) => ({
      ...prev,
      excludedPatterns: prev.excludedPatterns.filter((x) => x !== pattern),
    }));
    setSaved(false);
  };

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-ink">Privacy Settings</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Control what RecallAI captures and where your memories live. Everything is
          processed and stored on this device.
        </p>
      </div>

      {/* Local processing banner */}
      <div className="mb-6 flex items-start gap-3 rounded-2xl border border-safe-100 bg-safe-50 p-4">
        <span aria-hidden="true" className="text-xl">
          🛡️
        </span>
        <div>
          <h2 className="text-sm font-semibold text-safe-700">All processing is local</h2>
          <p className="mt-0.5 text-sm text-safe-700/90">
            Embeddings, search, and summaries run on this device. No memory data is sent
            to any server. These are mock preferences for the Module 1 UI.
          </p>
        </div>
      </div>

      {/* Capture status */}
      <Section title="Capture status">
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-100 bg-slate-50 p-4">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-safe-100 px-3 py-1 text-sm font-medium text-safe-700">
            <span className="inline-block h-2 w-2 rounded-full bg-safe-500" aria-hidden="true" />
            Active
          </span>
          <span className="text-sm text-ink-muted">
            Capture is running. You can pause or stop it from the extension popup.
          </span>
        </div>
      </Section>

      {/* Capture preferences */}
      <Section title="Capture preferences">
        <Toggle
          label="Auto-capture visited pages"
          description="Automatically save a memory when you visit a new page. Turn off to capture manually only."
          checked={settings.autoCapture}
          onChange={() => toggle('autoCapture')}
        />
        <Toggle
          label="Capture in Incognito windows"
          description="When off, nothing is captured while you browse in Incognito. This is a preference — Incognito capture still requires the extension permission."
          checked={settings.captureIncognito}
          onChange={() => toggle('captureIncognito')}
        />
        <Toggle
          label="Exclude sensitive pages"
          description="Skip pages matching sensitive patterns (e.g. banking, email) so they are never stored."
          checked={settings.excludeSensitivePages}
          onChange={() => toggle('excludeSensitivePages')}
        />
      </Section>

      {/* Excluded patterns */}
      <Section title="Excluded / sensitive pages">
        <p className="mb-3 text-sm text-ink-muted">
          Pages matching these patterns are never captured. (Mock list — preferences only.)
        </p>
        <ul className="mb-3 space-y-2">
          {settings.excludedPatterns.length === 0 && (
            <li className="text-sm text-ink-muted">No exclusions set.</li>
          )}
          {settings.excludedPatterns.map((pattern) => (
            <li
              key={pattern}
              className="flex items-center justify-between rounded-lg border border-slate-100 bg-white px-3 py-2 text-sm"
            >
              <code className="text-ink">{pattern}</code>
              <button
                type="button"
                onClick={() => removePattern(pattern)}
                className="text-xs font-medium text-red-600 hover:underline"
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
        <div className="flex gap-2">
          <label htmlFor="new-pattern" className="sr-only">
            New exclusion pattern
          </label>
          <input
            id="new-pattern"
            value={newPattern}
            onChange={(e) => setNewPattern(e.target.value)}
            placeholder="*://*.example.com/*"
            className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100"
          />
          <button
            type="button"
            onClick={addPattern}
            className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
          >
            Add
          </button>
        </div>
      </Section>

      {/* Memory deletion */}
      <Section title="Memory deletion">
        <Toggle
          label="Ask for confirmation before deleting"
          description="Show a confirmation step whenever you delete a memory."
          checked={settings.requireConfirmationToDelete}
          onChange={() => toggle('requireConfirmationToDelete')}
        />
        <div className="mt-3 rounded-xl border border-red-100 bg-red-50 p-4">
          <h3 className="text-sm font-semibold text-red-700">Delete all local memories</h3>
          <p className="mt-1 text-sm text-red-600">
            This erases every memory stored on this device. It cannot be undone. Manage
            individual memories from the{' '}
            <Link to="/timeline" className="font-medium underline">
              Memory Timeline
            </Link>
            .
          </p>
          <DeleteAllButton requireConfirmation={settings.requireConfirmationToDelete} />
        </div>
      </Section>

      <div className="mt-6 flex items-center gap-3">
        <button
          type="button"
          onClick={() => setSaved(true)}
          className="rounded-lg bg-brand-700 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600"
        >
          Save preferences
        </button>
        {saved && (
          <span role="status" className="text-sm text-safe-700">
            ✓ Preferences saved locally (mock — nothing is persisted in Module 1).
          </span>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-6 rounded-2xl border border-slate-100 bg-surface p-5 shadow-card">
      <h2 className="mb-4 text-base font-semibold text-ink">{title}</h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span>
        <span className="block text-sm font-medium text-ink">{label}</span>
        <span className="mt-0.5 block text-xs text-ink-muted">{description}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={onChange}
        className={[
          'relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition',
          checked ? 'bg-brand-600' : 'bg-slate-300',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all',
            checked ? 'left-[22px]' : 'left-0.5',
          ].join(' ')}
        />
      </button>
    </label>
  );
}

function DeleteAllButton({ requireConfirmation }: { requireConfirmation: boolean }) {
  const [confirming, setConfirming] = useState(false);
  if (!confirming) {
    return (
      <button
        type="button"
        onClick={() => setConfirming(true)}
        className="mt-3 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
      >
        Delete all memories
      </button>
    );
  }
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="text-sm text-red-700">
        {requireConfirmation ? 'Are you sure? This cannot be undone.' : 'Confirm deletion:'}
      </span>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm font-medium text-ink hover:bg-slate-50"
      >
        Cancel
      </button>
      <button
        type="button"
        onClick={() => setConfirming(false)}
        className="rounded-lg bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800"
      >
        Delete everything
      </button>
    </div>
  );
}
