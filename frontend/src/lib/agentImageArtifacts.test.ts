import { describe, expect, it } from 'vitest';
import { collectAgentImageArtifacts } from './agentImageArtifacts';
import type { Message } from '@/types/chat';

describe('collectAgentImageArtifacts', () => {
  it('ignores historical inline base64 code-execution images', () => {
    const messages = [
      {
        id: 'm1',
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        toolCalls: [
          {
            id: 'tc1',
            name: 'code_execution',
            status: 'success',
            result: {
              images: [{ path: 'plot.gif', mime: 'image/gif', base64: 'huge' }],
            },
          },
        ],
      },
    ] as unknown as Message[];

    expect(collectAgentImageArtifacts(messages)).toEqual([]);
  });

  it('collects managed image artifacts by preview URL and hash', () => {
    const messages = [
      {
        id: 'm1',
        role: 'assistant',
        content: '',
        timestamp: new Date(),
        toolCalls: [
          {
            id: 'tc1',
            name: 'code_execution',
            status: 'success',
            result: {
              managed_artifacts: [
                {
                  id: 'file-1',
                  filename: 'plot.gif',
                  content_type: 'image/gif',
                  preview_url: '/api/v1/files/file-1/preview?token=t',
                  download_url: '/api/v1/files/file-1/download?token=t',
                  sha256: 'abcdef1234567890',
                },
              ],
            },
          },
        ],
      },
    ] as unknown as Message[];

    expect(collectAgentImageArtifacts(messages)).toEqual([
      {
        id: 'file-1',
        fileName: 'plot.gif',
        mime: 'image/gif',
        previewUrl: '/api/v1/files/file-1/preview?token=t',
        downloadUrl: '/api/v1/files/file-1/download?token=t',
        sha256: 'abcdef1234567890',
      },
    ]);
  });
});
