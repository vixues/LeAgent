const TARGET = 64;
const MAX_DATA_URL_CHARS = 120_000;

function assertSmallEnough(dataUrl: string): string {
  if (dataUrl.length > MAX_DATA_URL_CHARS) {
    throw new Error('ICON_TOO_LARGE');
  }
  return dataUrl;
}

function base64EncodeUtf8(value: string): string {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return window.btoa(binary);
}

async function svgFileToDataUrl(file: File): Promise<string> {
  const text = await file.text();
  if (!/<svg[\s>]/i.test(text)) {
    throw new Error('INVALID_SVG');
  }
  if (/<script|<foreignObject|\son\w+=/i.test(text)) {
    throw new Error('INVALID_SVG');
  }
  const encoded = base64EncodeUtf8(text);
  return assertSmallEnough(`data:image/svg+xml;base64,${encoded}`);
}

export async function fileToBrandingIconDataUrl(file: File): Promise<string> {
  if (file.type === 'image/svg+xml' || file.name.toLowerCase().endsWith('.svg')) {
    return svgFileToDataUrl(file);
  }

  const bitmap = await createImageBitmap(file);
  try {
    const scale = Math.min(TARGET / bitmap.width, TARGET / bitmap.height, 1);
    const w = Math.max(1, Math.round(bitmap.width * scale));
    const h = Math.max(1, Math.round(bitmap.height * scale));
    const canvas = document.createElement('canvas');
    canvas.width = TARGET;
    canvas.height = TARGET;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas unsupported');
    ctx.clearRect(0, 0, TARGET, TARGET);
    const dx = (TARGET - w) / 2;
    const dy = (TARGET - h) / 2;
    ctx.drawImage(bitmap, dx, dy, w, h);
    const dataUrl = canvas.toDataURL('image/png');
    return assertSmallEnough(dataUrl);
  } finally {
    bitmap.close();
  }
}

export { MAX_DATA_URL_CHARS as MAX_BRANDING_ICON_DATA_URL_CHARS };
