import {
  Code2,
  FileText,
  Image,
  File,
  FileArchive,
  FileCode,
  FileJson,
  FileSpreadsheet,
  FolderGit2,
  Layout,
  Table,
  Terminal,
  Database,
  Hash,
  Film,
  Music,
  BookOpen,
  Braces,
} from 'lucide-react';
import type { ArtifactType } from '@/types/artifact';

type IconCategory = 'code' | 'doc' | 'data' | 'media' | 'archive' | 'generic';

const CATEGORY_CLASS: Record<IconCategory, string> = {
  code: 'text-sky-500 dark:text-sky-400',
  doc: 'text-amber-500 dark:text-amber-400',
  data: 'text-mint-500 dark:text-mint-400',
  media: 'text-fuchsia-500 dark:text-fuchsia-400',
  archive: 'text-muted-foreground',
  generic: 'text-muted-foreground-tertiary',
};

function icon(node: React.ReactNode, category: IconCategory) {
  return (
    <span
      className={`inline-flex items-center justify-center ${CATEGORY_CLASS[category]}`}
    >
      {node}
    </span>
  );
}

/* ─── Artifact type icons ────────────────────────────────────── */
const TYPE_ICON: Record<ArtifactType, React.ReactNode> = {
  code: icon(<Code2 className="w-4 h-4" />, 'code'),
  file: icon(<FileText className="w-4 h-4" />, 'doc'),
  workflow: icon(<FolderGit2 className="w-4 h-4" />, 'data'),
  table: icon(<Table className="w-4 h-4" />, 'data'),
  markdown: icon(<BookOpen className="w-4 h-4" />, 'doc'),
  image: icon(<Image className="w-4 h-4" />, 'media'),
  html: icon(<Layout className="w-4 h-4" />, 'code'),
  react: icon(<Braces className="w-4 h-4" />, 'code'),
  mermaid: icon(<FolderGit2 className="w-4 h-4" />, 'data'),
};

export function getArtifactIcon(type: ArtifactType): React.ReactNode {
  return TYPE_ICON[type] ?? icon(<File className="w-4 h-4" />, 'generic');
}

/* ─── File extension icons ───────────────────────────────────── */
export function getFileExtensionIcon(filename: string): React.ReactNode {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';
  const I = (klass?: string) => `w-4 h-4 ${klass ?? ''}`;

  switch (ext) {
    // code
    case 'ts':
    case 'tsx':
    case 'js':
    case 'jsx':
    case 'mjs':
    case 'cjs':
      return icon(<FileCode className={I()} />, 'code');
    case 'py':
    case 'rb':
    case 'go':
    case 'rs':
    case 'java':
    case 'c':
    case 'cpp':
    case 'cc':
    case 'h':
    case 'hpp':
    case 'swift':
    case 'kt':
    case 'scala':
      return icon(<Code2 className={I()} />, 'code');
    case 'sh':
    case 'bash':
    case 'zsh':
    case 'fish':
      return icon(<Terminal className={I()} />, 'code');
    case 'css':
    case 'scss':
    case 'sass':
    case 'less':
      return icon(<Hash className={I()} />, 'code');
    case 'html':
    case 'htm':
    case 'xml':
      return icon(<Layout className={I()} />, 'code');

    // data / config
    case 'json':
      return icon(<FileJson className={I()} />, 'data');
    case 'yaml':
    case 'yml':
    case 'toml':
    case 'ini':
    case 'env':
      return icon(<Braces className={I()} />, 'data');
    case 'sql':
      return icon(<Database className={I()} />, 'data');
    case 'csv':
    case 'tsv':
    case 'xls':
    case 'xlsx':
    case 'ods':
      return icon(<FileSpreadsheet className={I()} />, 'data');

    // docs
    case 'md':
    case 'mdx':
    case 'rst':
    case 'adoc':
      return icon(<BookOpen className={I()} />, 'doc');
    case 'txt':
    case 'log':
      return icon(<FileText className={I()} />, 'doc');
    case 'doc':
    case 'docx':
    case 'odt':
    case 'rtf':
      return icon(<FileText className={I()} />, 'doc');
    case 'pdf':
      return icon(<FileText className={I()} />, 'doc');
    case 'ppt':
    case 'pptx':
    case 'odp':
    case 'key':
      return icon(<Layout className={I()} />, 'doc');

    // media
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
    case 'avif':
    case 'ico':
    case 'bmp':
      return icon(<Image className={I()} />, 'media');
    case 'mp4':
    case 'mov':
    case 'webm':
    case 'mkv':
    case 'avi':
      return icon(<Film className={I()} />, 'media');
    case 'mp3':
    case 'wav':
    case 'flac':
    case 'ogg':
    case 'm4a':
      return icon(<Music className={I()} />, 'media');

    // archive
    case 'zip':
    case 'tar':
    case 'gz':
    case 'bz2':
    case 'xz':
    case 'rar':
    case '7z':
      return icon(<FileArchive className={I()} />, 'archive');

    default:
      return icon(<File className={I()} />, 'generic');
  }
}
