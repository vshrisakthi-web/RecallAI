import { describe, it, expect } from 'vitest';
import { isValidMessage } from '../lib/messages';

describe('isValidMessage (Task 2.10 G — invalid messages rejected)', () => {
  it('accepts valid messages', () => {
    expect(isValidMessage({ type: 'GET_STATE' })).toBe(true);
    expect(isValidMessage({ type: 'SET_STATE', state: 'paused' })).toBe(true);
    expect(isValidMessage({ type: 'CAPTURE', tab: { id: 1 }, captureType: 'full-page' })).toBe(true);
    expect(isValidMessage({ type: 'DELETE_RECORD', id: 'abc' })).toBe(true);
  });

  it('rejects unknown types and malformed payloads', () => {
    expect(isValidMessage({ type: 'NOPE' })).toBe(false);
    expect(isValidMessage({ type: 'SET_STATE', state: 'bogus' })).toBe(false);
    expect(isValidMessage({ type: 'CAPTURE', tab: {}, captureType: 'weird' })).toBe(false);
    expect(isValidMessage({ type: 'GET_RECORD' })).toBe(false); // missing id
    expect(isValidMessage(null)).toBe(false);
    expect(isValidMessage('string')).toBe(false);
    expect(isValidMessage(42)).toBe(false);
  });
});
