// RecallAI — capture state machine (Module 2, Task 2.8)
//
// A tiny, pure state model for the capture lifecycle. "Active" means the user is
// *allowed* to initiate a capture — it never implies continuous background
// surveillance. Transitions are explicit and testable.

import type { CaptureState } from '../types';

/** Which actions are valid from a given state. */
export interface StateDefinition {
  label: string;
  /** May the user initiate a capture right now? */
  canCapture: boolean;
  /** Which state transitions are allowed. */
  allowed: CaptureState[];
}

export const STATE_TABLE: Record<CaptureState, StateDefinition> = {
  active: { label: 'Active', canCapture: true, allowed: ['paused', 'stopped'] },
  paused: { label: 'Paused', canCapture: false, allowed: ['active', 'stopped'] },
  stopped: { label: 'Stopped', canCapture: false, allowed: ['active'] },
};

/** True when a capture may be initiated in the given state. */
export function canCapture(state: CaptureState): boolean {
  return STATE_TABLE[state].canCapture;
}

/** True when `from → to` is an allowed transition. */
export function canTransition(from: CaptureState, to: CaptureState): boolean {
  if (from === to) return true; // idempotent no-op
  return STATE_TABLE[from].allowed.includes(to);
}

/** Human label for a state. */
export function stateLabel(state: CaptureState): string {
  return STATE_TABLE[state].label;
}
