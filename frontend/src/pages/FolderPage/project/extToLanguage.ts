/**
 * Map a file extension (or basename) to a highlight.js language token.
 *
 * highlight.js supports far more languages than this list, but mapping
 * the long tail isn't worth the bytes — anything not listed falls back
 * to ``plaintext`` and the auto-detector still kicks in for the body.
 */
const EXTENSION_TO_LANGUAGE: Record<string, string> = {
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  pyi: 'python',
  rb: 'ruby',
  go: 'go',
  rs: 'rust',
  java: 'java',
  kt: 'kotlin',
  kts: 'kotlin',
  c: 'c',
  h: 'c',
  cpp: 'cpp',
  cc: 'cpp',
  cxx: 'cpp',
  hpp: 'cpp',
  hh: 'cpp',
  cs: 'csharp',
  php: 'php',
  swift: 'swift',
  scala: 'scala',
  m: 'objectivec',
  mm: 'objectivec',
  json: 'json',
  yaml: 'yaml',
  yml: 'yaml',
  toml: 'ini',
  ini: 'ini',
  cfg: 'ini',
  conf: 'ini',
  xml: 'xml',
  html: 'xml',
  htm: 'xml',
  vue: 'xml',
  svelte: 'xml',
  css: 'css',
  scss: 'scss',
  sass: 'scss',
  less: 'less',
  md: 'markdown',
  mdx: 'markdown',
  rst: 'plaintext',
  sh: 'bash',
  bash: 'bash',
  zsh: 'bash',
  fish: 'bash',
  ps1: 'powershell',
  bat: 'dos',
  cmd: 'dos',
  sql: 'sql',
  graphql: 'graphql',
  gql: 'graphql',
  proto: 'protobuf',
  dockerfile: 'dockerfile',
  makefile: 'makefile',
};

const FILENAME_TO_LANGUAGE: Record<string, string> = {
  Dockerfile: 'dockerfile',
  Makefile: 'makefile',
  GNUmakefile: 'makefile',
  '.gitignore': 'plaintext',
  '.gitattributes': 'plaintext',
};

/** Return a highlight.js language token for the given path / filename. */
export function extToLanguage(path: string | null | undefined): string {
  if (!path) return 'plaintext';
  const name = path.split(/[\\/]/).pop() ?? path;
  if (FILENAME_TO_LANGUAGE[name]) return FILENAME_TO_LANGUAGE[name];
  const ext = name.includes('.') ? name.split('.').pop()!.toLowerCase() : '';
  return EXTENSION_TO_LANGUAGE[ext] ?? 'plaintext';
}
