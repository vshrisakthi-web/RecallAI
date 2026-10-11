import { describe, it, expect } from 'vitest';
import { canCapture, canTransition, stateLabel, STATE_TABLE } from '../lib/state';

describe('capture state machine (Task 2.10 F)', () => {
  it('only ACTIVE allows capture', () => {
    expect(canCapture('active')).toBe(true);
    expect(canCapture('paused')).toBe(false);
    expect(canCapture('stopped')).toBe(false);
  });

  it('allows valid transitions', () => {
    expect(canTransition('active', 'paused')).toBe(true);
    expect(canTransition('active', 'stopped')).toBe(true);
    expect(canTransition('paused', 'active')).toBe(true); // resume
    expect(canTransition('paused', 'stopped')).toBe(true);
    expect(canTransition('stopped', 'active')).toBe(true); // start again
  });

  it('rejects invalid transitions', () => {
    expect(canTransition('stopped', 'paused')).toBe(false);
    expect(canTransition('paused', 'paused')).toBe(true); // idempotent
  });

  it('exposes labels', () => {
    expect(stateLabel('active')).toBe('Active');
    expect(STATE_TABLE.paused.canCapture).toBe(false);
  });
});
