import { describe, expect, it } from 'vitest';
import type { Message } from '@/types/chat';
import {
  buildCodingProjectLoopbackPreviewUrl,
  codingProjectPreviewPathWithDocs,
  collectActivitySummary,
  collectProjectPathsWithOps,
  countProjectFamilyToolCalls,
  findLatestCodingProjectRunPreview,
  resolveCodingProjectPreviewUrlForEmbed,
  resolvePathPreview,
} from './projectToolEnvelope';

const assistant = (toolCalls: Message['toolCalls']): Message => ({
  id: crypto.randomUUID(),
  role: 'assistant',
  content: '',
  createdAt: new Date(0).toISOString(),
  toolCalls,
});

describe('projectToolEnvelope', () => {
  it('resolves read previews before write and edit snapshots', () => {
    const messages = [
      assistant([
        {
          id: 'write',
          name: 'project_write',
          arguments: { path: 'src/app.ts', content: 'written' },
          status: 'success',
        },
        {
          id: 'read',
          name: 'project_read',
          arguments: { path: 'src/app.ts' },
          result: 'current contents',
          status: 'success',
        },
      ]),
    ];

    expect(resolvePathPreview(messages, 'src/app.ts')).toEqual({
      kind: 'read',
      text: 'current contents',
    });
  });

  it('collects coding-agent changed files and activity paths with operations', () => {
    const messages = [
      assistant([
        {
          id: 'agent',
          name: 'coding_agent',
          arguments: { project_path: '/repo' },
          result: {
            changed_files: ['src/a.ts'],
            activity: [
              { tool: 'project_read', path: 'src/b.ts' },
              { tool: 'project_apply_patch', path: 'src/c.ts' },
            ],
          },
          status: 'success',
        },
      ]),
    ];

    expect(collectProjectPathsWithOps(messages)).toEqual([
      { path: '/repo', operation: 'unknown' },
      { path: 'src/a.ts', operation: 'edit' },
      { path: 'src/b.ts', operation: 'read' },
      { path: 'src/c.ts', operation: 'edit' },
    ]);
    expect(countProjectFamilyToolCalls(messages)).toBe(1);
  });

  it('summarizes completed project-family tool activity', () => {
    const messages = [
      assistant([
        {
          id: 'shell',
          name: 'project_shell',
          arguments: {},
          status: 'success',
        },
        {
          id: 'pending',
          name: 'project_read',
          arguments: { path: 'README.md' },
          status: 'pending',
        },
      ]),
    ];

    expect(collectActivitySummary(messages)).toEqual([
      {
        tool: 'project_shell',
        path: undefined,
        operation: 'execute',
        summary: 'Ran shell command',
      },
    ]);
  });

  it('findLatestCodingProjectRunPreview returns null when no successful run', () => {
    expect(findLatestCodingProjectRunPreview([])).toBeNull();
    expect(
      findLatestCodingProjectRunPreview([
        assistant([
          {
            id: 'run',
            name: 'coding_project_run',
            arguments: { project_id: 'x' },
            status: 'pending',
          },
        ]),
      ]),
    ).toBeNull();
  });

  it('findLatestCodingProjectRunPreview picks newest success and maps 0.0.0.0 host', () => {
    const older = assistant([
      {
        id: 'old',
        name: 'coding_project_run',
        arguments: { project_id: '00000000-0000-0000-0000-000000000001' },
        result: {
          project_id: '00000000-0000-0000-0000-000000000001',
          host: '127.0.0.1',
          port: 39000,
          preview_url: '/api/v1/coding-projects/u1/preview/?token=a',
          runtime_kind: 'frontend',
        },
        status: 'success',
      },
    ]);
    const newer = assistant([
      {
        id: 'new',
        name: 'coding_project_run',
        arguments: { project_id: '00000000-0000-0000-0000-000000000002' },
        result: {
          project_id: '00000000-0000-0000-0000-000000000002',
          host: '0.0.0.0',
          port: 39001,
          preview_url: '/api/v1/coding-projects/u2/preview/?token=b',
          runtime_kind: 'fastapi',
        },
        status: 'success',
      },
    ]);

    const messages = [older, newer];
    const info = findLatestCodingProjectRunPreview(messages);
    expect(info).not.toBeNull();
    expect(info!.projectId).toBe('00000000-0000-0000-0000-000000000002');
    expect(info!.iframeHost).toBe('127.0.0.1');
    expect(info!.host).toBe('0.0.0.0');
    expect(info!.port).toBe(39001);
    expect(info!.runtimeKind).toBe('fastapi');
    expect(buildCodingProjectLoopbackPreviewUrl(info!)).toBe('http://127.0.0.1:39001/docs');
  });

  it('codingProjectPreviewPathWithDocs inserts /docs before the query', () => {
    expect(codingProjectPreviewPathWithDocs('/api/v1/coding-projects/u/preview/?token=x')).toBe(
      '/api/v1/coding-projects/u/preview/docs?token=x',
    );
  });

  it('resolveCodingProjectPreviewUrlForEmbed uses loopback on http parent', () => {
    const info = {
      projectId: '00000000-0000-0000-0000-000000000002',
      host: '127.0.0.1',
      iframeHost: '127.0.0.1',
      port: 39001,
      previewUrl: '/api/v1/coding-projects/u2/preview/?token=b',
      runtimeKind: 'frontend' as const,
    };
    expect(resolveCodingProjectPreviewUrlForEmbed(info, 'http:')).toBe(
      'http://127.0.0.1:39001/',
    );
  });

  it('resolveCodingProjectPreviewUrlForEmbed uses signed proxy on https parent', () => {
    const info = {
      projectId: '00000000-0000-0000-0000-000000000002',
      host: '127.0.0.1',
      iframeHost: '127.0.0.1',
      port: 39001,
      previewUrl: '/api/v1/coding-projects/u2/preview/?token=b',
      runtimeKind: 'frontend' as const,
    };
    expect(resolveCodingProjectPreviewUrlForEmbed(info, 'https:')).toBe(
      '/api/v1/coding-projects/u2/preview/?token=b',
    );
  });

  it('resolveCodingProjectPreviewUrlForEmbed maps FastAPI to /preview/docs on https', () => {
    const info = {
      projectId: '00000000-0000-0000-0000-000000000002',
      host: '127.0.0.1',
      iframeHost: '127.0.0.1',
      port: 39001,
      previewUrl: '/api/v1/coding-projects/u2/preview/?token=b',
      runtimeKind: 'fastapi' as const,
    };
    expect(resolveCodingProjectPreviewUrlForEmbed(info, 'https:')).toBe(
      '/api/v1/coding-projects/u2/preview/docs?token=b',
    );
  });
});
