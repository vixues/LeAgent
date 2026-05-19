/**
 * Split user message text into plain segments and inline reference tokens
 * (``@knowledge:…#uuid``, ``@skill:…#name``, ``@file:…`` / ``@file:…#id``)
 * for rich rendering.
 */

const UUID_TAIL =
  '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}';

const KNOWLEDGE_REF_RE = new RegExp(
  `@knowledge:([^#\\s@]+)#(${UUID_TAIL})`,
  'gi',
);

/** Manifest ``name`` (kebab-case) after ``#`` in ``@skill:label#name``. */
const SKILL_REF_RE = /@skill:([^#\s@]+)#([a-z0-9][a-z0-9_-]*)/gi;

/** ``@file:name`` or ``@file:name#attachmentId`` (id is opaque, not always UUID). */
const FILE_REF_RE = /@file:([^\s#@]+)(?:#([^\s@]+))?/gi;

export type UserMessageContentSegment =
  | { type: 'text'; value: string }
  | { type: 'knowledgeRef'; label: string; fileId: string; raw: string }
  | { type: 'skillRef'; label: string; skillName: string; raw: string }
  | { type: 'fileRef'; label: string; refId: string | undefined; raw: string };

function splitKnowledgeRefs(text: string): UserMessageContentSegment[] {
  const out: UserMessageContentSegment[] = [];
  KNOWLEDGE_REF_RE.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = KNOWLEDGE_REF_RE.exec(text)) !== null) {
    if (m.index > last) {
      out.push({ type: 'text', value: text.slice(last, m.index) });
    }
    out.push({
      type: 'knowledgeRef',
      label: (m[1] ?? '').trim(),
      fileId: m[2] ?? '',
      raw: m[0] ?? '',
    });
    last = m.index + (m[0]?.length ?? 0);
  }
  if (last < text.length) {
    out.push({ type: 'text', value: text.slice(last) });
  }
  return out;
}

function splitSkillRefsInText(text: string): UserMessageContentSegment[] {
  const out: UserMessageContentSegment[] = [];
  SKILL_REF_RE.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = SKILL_REF_RE.exec(text)) !== null) {
    if (m.index > last) {
      out.push({ type: 'text', value: text.slice(last, m.index) });
    }
    out.push({
      type: 'skillRef',
      label: (m[1] ?? '').trim(),
      skillName: m[2] ?? '',
      raw: m[0] ?? '',
    });
    last = m.index + (m[0]?.length ?? 0);
  }
  if (last < text.length) {
    out.push({ type: 'text', value: text.slice(last) });
  }
  return out;
}

function splitFileRefsInText(text: string): UserMessageContentSegment[] {
  const out: UserMessageContentSegment[] = [];
  FILE_REF_RE.lastIndex = 0;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = FILE_REF_RE.exec(text)) !== null) {
    if (m.index > last) {
      out.push({ type: 'text', value: text.slice(last, m.index) });
    }
    out.push({
      type: 'fileRef',
      label: (m[1] ?? '').trim(),
      refId: m[2]?.trim() || undefined,
      raw: m[0] ?? '',
    });
    last = m.index + (m[0]?.length ?? 0);
  }
  if (last < text.length) {
    out.push({ type: 'text', value: text.slice(last) });
  }
  return out;
}

/** Coalesce adjacent ``text`` segments. */
function mergeTextChunks(segments: UserMessageContentSegment[]): UserMessageContentSegment[] {
  const merged: UserMessageContentSegment[] = [];
  for (const seg of segments) {
    if (seg.type === 'text' && seg.value === '') continue;
    const prev = merged[merged.length - 1];
    if (seg.type === 'text' && prev?.type === 'text') {
      prev.value += seg.value;
    } else {
      merged.push(seg.type === 'text' ? { ...seg } : seg);
    }
  }
  return merged;
}

/**
 * Parse ``content`` into ordered segments. Order: ``@knowledge``, then
 * ``@skill``, then ``@file`` inside remaining text (so paths do not false-match).
 */
export function parseUserMessageRefs(content: string): UserMessageContentSegment[] {
  if (!content) return [];
  const afterKnowledge: UserMessageContentSegment[] = [];
  for (const chunk of splitKnowledgeRefs(content)) {
    if (chunk.type === 'text') {
      const afterSkill: UserMessageContentSegment[] = [];
      for (const sub of splitSkillRefsInText(chunk.value)) {
        if (sub.type === 'text') {
          afterSkill.push(...splitFileRefsInText(sub.value));
        } else {
          afterSkill.push(sub);
        }
      }
      afterKnowledge.push(...afterSkill);
    } else {
      afterKnowledge.push(chunk);
    }
  }
  return mergeTextChunks(afterKnowledge);
}
