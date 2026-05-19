import { describe, expect, it } from 'vitest';

import { matchComposerTriggerToken } from './composerTriggerToken';

describe('matchComposerTriggerToken', () => {
  it('matches @ after CJK text without a space', () => {
    expect(matchComposerTriggerToken('使用genui介绍@')).toEqual({
      kind: '@',
      query: '',
      tokenLength: 1,
    });
  });

  it('matches @ with query after whitespace', () => {
    expect(matchComposerTriggerToken('hello @ski')).toEqual({
      kind: '@',
      query: 'ski',
      tokenLength: 4,
    });
  });

  it('matches slash command token', () => {
    expect(matchComposerTriggerToken('/cle')).toEqual({
      kind: '/',
      query: 'cle',
      tokenLength: 4,
    });
  });

  it('returns null when no trigger at end', () => {
    expect(matchComposerTriggerToken('hello world')).toBeNull();
  });
});
