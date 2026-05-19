import { describe, expect, it } from 'vitest';
import {
  getOfficePreviewRoute,
  resolveEffectiveMime,
} from '@/lib/mimeForPreview';

describe('getOfficePreviewRoute', () => {
  it('maps OOXML extensions', () => {
    expect(getOfficePreviewRoute('a.docx', 'application/octet-stream')).toBe(
      'docx',
    );
    expect(getOfficePreviewRoute('b.xlsx', '')).toBe('xlsx');
    expect(getOfficePreviewRoute('c.pptx', '')).toBe('pptx');
  });

  it('maps macro-enabled OOXML to OOXML preview routes', () => {
    expect(getOfficePreviewRoute('m.docm', '')).toBe('docx');
    expect(getOfficePreviewRoute('n.xlsm', '')).toBe('xlsx');
    expect(getOfficePreviewRoute('o.pptm', '')).toBe('pptx');
  });

  it('maps legacy binary extensions', () => {
    expect(getOfficePreviewRoute('old.doc', 'application/msword')).toBe(
      'legacy',
    );
    expect(getOfficePreviewRoute('old.xls', '')).toBe('legacy');
    expect(getOfficePreviewRoute('old.ppt', '')).toBe('legacy');
  });

  it('maps OpenDocument extensions', () => {
    expect(getOfficePreviewRoute('t.odt', '')).toBe('openDocument');
    expect(getOfficePreviewRoute('u.ods', '')).toBe('openDocument');
    expect(getOfficePreviewRoute('v.odp', '')).toBe('openDocument');
  });

  it('prefers extension over ambiguous MIME when extension is present', () => {
    const mime = resolveEffectiveMime(
      'application/zip',
      'report.docx',
    );
    expect(getOfficePreviewRoute('report.docx', mime)).toBe('docx');
  });

  it('infers from OOXML MIME when extension is missing', () => {
    expect(
      getOfficePreviewRoute(
        'unknown',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      ),
    ).toBe('docx');
    expect(
      getOfficePreviewRoute(
        'unknown',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      ),
    ).toBe('xlsx');
    expect(
      getOfficePreviewRoute(
        'unknown',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      ),
    ).toBe('pptx');
  });

  it('maps legacy MS MIME without helpful extension', () => {
    expect(getOfficePreviewRoute('blob', 'application/msword')).toBe('legacy');
    expect(getOfficePreviewRoute('blob', 'application/vnd.ms-excel')).toBe(
      'legacy',
    );
    expect(
      getOfficePreviewRoute('blob', 'application/vnd.ms-powerpoint'),
    ).toBe('legacy');
  });

  it('returns null for non-office types', () => {
    expect(getOfficePreviewRoute('a.pdf', 'application/pdf')).toBeNull();
    expect(getOfficePreviewRoute('x.txt', 'text/plain')).toBeNull();
  });
});
