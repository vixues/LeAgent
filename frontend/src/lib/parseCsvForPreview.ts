/**
 * Minimal RFC 4180–style CSV parse for in-browser preview (quoted fields, escaped quotes).
 * Caps output size so large pasted buffers stay responsive.
 */

const MAX_ROWS = 500;
const MAX_COLS = 64;
const MAX_SCAN_CHARS = 1_500_000;

export type CsvPreviewParseResult = {
  rows: string[][];
  truncatedRows: boolean;
  truncatedScan: boolean;
  truncatedCols: boolean;
};

export function parseCsvForPreview(input: string): CsvPreviewParseResult {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let inQuotes = false;
  let truncatedRows = false;
  let truncatedScan = false;
  let truncatedCols = false;

  const text = input.length > MAX_SCAN_CHARS ? input.slice(0, MAX_SCAN_CHARS) : input;
  if (text.length < input.length) truncatedScan = true;

  const pushField = () => {
    row.push(field);
    field = '';
  };

  const pushRow = () => {
    if (row.length > MAX_COLS) {
      truncatedCols = true;
      row = row.slice(0, MAX_COLS);
    }
    if (rows.length >= MAX_ROWS) {
      truncatedRows = true;
      row = [];
      return;
    }
    rows.push(row);
    row = [];
  };

  for (let i = 0; i < text.length && !truncatedRows; i++) {
    const c = text[i]!;

    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += c;
      }
      continue;
    }

    if (c === '"') {
      inQuotes = true;
      continue;
    }
    if (c === ',') {
      pushField();
      continue;
    }
    if (c === '\r') continue;
    if (c === '\n') {
      pushField();
      pushRow();
      continue;
    }
    field += c;
  }

  if (!truncatedRows) {
    pushField();
    const hasCells = row.some((cell) => cell.length > 0);
    if (row.length > 1 || hasCells || rows.length === 0) {
      pushRow();
    }
  }

  return { rows, truncatedRows, truncatedScan, truncatedCols };
}
