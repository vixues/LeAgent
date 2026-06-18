import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  dispatchGenUiAction,
  normalizeAction,
  registerGenUiActionAdapters,
  resetGenUiActionAdapters,
} from './genUiActionBus';

describe('genUiActionBus', () => {
  beforeEach(() => {
    resetGenUiActionAdapters();
  });

  it('normalizeAction maps bare string to send_message', () => {
    expect(normalizeAction('hello')).toEqual({
      type: 'send_message',
      payload: { content: 'hello' },
    });
  });

  it('normalizeAction parses send_message object', () => {
    const a = normalizeAction({ type: 'send_message', payload: { content: 'Hi' } });
    expect(a).toEqual({ type: 'send_message', payload: { content: 'Hi' } });
  });

  it('normalizeAction parses navigate', () => {
    const a = normalizeAction({ type: 'navigate', payload: { route: '/settings' } });
    expect(a).toEqual({ type: 'navigate', payload: { route: '/settings' } });
  });

  it('dispatchGenUiAction invokes sendMessage adapter', () => {
    const fn = vi.fn();
    registerGenUiActionAdapters({ sendMessage: fn });
    dispatchGenUiAction({ type: 'send_message', payload: { content: 'x' } });
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn).toHaveBeenCalledWith({ content: 'x' }, expect.any(Object));
  });

  it('run_workflow merges inline payload values with form context', () => {
    const fn = vi.fn();
    registerGenUiActionAdapters({ runWorkflow: fn });
    dispatchGenUiAction(
      { type: 'run_workflow', payload: { flowId: 'f1' } },
      { formValues: { prompt: 'from form' } },
    );
    expect(fn).toHaveBeenCalledWith(
      { flowId: 'f1', values: { prompt: 'from form' } },
      expect.objectContaining({ formValues: { prompt: 'from form' } }),
    );
  });
});
