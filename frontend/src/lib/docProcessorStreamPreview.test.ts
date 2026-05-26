import { describe, expect, it } from 'vitest';
import {
  extractDocProcessorPreviewText,
  isDocProcessorWriteStream,
  languageForDocProcessorPreview,
} from './docProcessorStreamPreview';

describe('docProcessorStreamPreview', () => {
  it('detects write operations while streaming', () => {
    const raw = '{"operation":"write","file_path":"notes.md","content":"# Hello';
    expect(isDocProcessorWriteStream('markdown_processor', raw, {})).toBe(true);
    expect(isDocProcessorWriteStream('text_processor', '{"operation":"read"', {})).toBe(false);
  });

  it('extracts streaming markdown content from partial JSON', () => {
    const raw = '{"operation":"write","file_path":"a.md","content":"# Title\\n\\nBody';
    const text = extractDocProcessorPreviewText('markdown_processor', raw, {});
    expect(text).toContain('# Title');
    expect(text).toContain('Body');
  });

  it('extracts streaming text_processor data field', () => {
    const raw = '{"operation":"write","file_path":"log.txt","data":"line one\\nline';
    const text = extractDocProcessorPreviewText('text_processor', raw, {});
    expect(text).toContain('line one');
  });

  it('uses markdown language for md processor', () => {
    expect(languageForDocProcessorPreview('x.md', 'markdown_processor')).toBe('markdown');
    expect(languageForDocProcessorPreview('x.py', 'text_processor')).toBe('python');
  });
});
