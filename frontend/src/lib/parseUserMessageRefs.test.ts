import { describe, expect, it } from 'vitest';

import { parseUserMessageRefs } from './parseUserMessageRefs';

describe('parseUserMessageRefs', () => {
  it('parses @skill label and name', () => {
    const segs = parseUserMessageRefs('Hello @skill:My_Skill_Label#my-skill world');
    expect(segs).toEqual([
      { type: 'text', value: 'Hello ' },
      {
        type: 'skillRef',
        label: 'My_Skill_Label',
        skillName: 'my-skill',
        raw: '@skill:My_Skill_Label#my-skill',
      },
      { type: 'text', value: ' world' },
    ]);
  });

  it('orders knowledge before skill before file in text', () => {
    const text =
      '@knowledge:doc.pdf#11111111-1111-1111-1111-111111111111 x @skill:Label#foo @file:a.txt';
    const segs = parseUserMessageRefs(text);
    expect(segs.map((s) => s.type)).toEqual([
      'knowledgeRef',
      'text',
      'skillRef',
      'text',
      'fileRef',
    ]);
  });
});
