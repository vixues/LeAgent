/**
 * Central pdf.js loader. We import the worker as a URL asset so Vite bundles a
 * hashed copy and we avoid CDN / version-mismatch issues at runtime.
 */
import * as pdfjsLib from 'pdfjs-dist';
// `?url` makes Vite emit the worker as a static asset and hand us its URL.
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjsLib };
export type PdfDocument = Awaited<ReturnType<typeof pdfjsLib.getDocument>['promise']>;
export type PdfPageProxy = Awaited<ReturnType<PdfDocument['getPage']>>;
