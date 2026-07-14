import { describe, expect, it } from 'vitest';
import { selectVisibleMessageAttachments } from './chatAttachments';
import type { Attachment } from '@/types/chat';

function attachment(id: string, name: string): Attachment {
  return { id, name, type: 'text/plain', size: 1 };
}

describe('selectVisibleMessageAttachments', () => {
  it('hides runtime source files and keeps the latest logical file', () => {
    expect(
      selectVisibleMessageAttachments([
        attachment('source-1', '__last_source__.py'),
        attachment('report-v1', 'report.pdf'),
        attachment('report-v2', 'report.pdf'),
      ]),
    ).toEqual([attachment('report-v2', 'report.pdf')]);
  });

  it('does not collapse unresolved id-only attachments', () => {
    expect(
      selectVisibleMessageAttachments([
        attachment('a', 'attachment'),
        attachment('b', 'attachment'),
      ]).map((item) => item.id),
    ).toEqual(['a', 'b']);
  });
});
