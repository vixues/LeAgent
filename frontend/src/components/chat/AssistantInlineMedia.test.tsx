import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { Attachment } from '@/types/chat';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_k: string, d?: string) => d ?? _k }),
}));

vi.mock('./media/ChatImage', () => ({
  ChatImage: ({ src }: { src?: string }) => <div data-testid="chat-image" data-src={src} />,
}));

vi.mock('./media/ChatInlineVideo', () => ({
  ChatInlineVideo: ({ src }: { src: string }) => <div data-testid="chat-video" data-src={src} />,
}));

vi.mock('./media/ChatInlineModel3D', () => ({
  ChatInlineModel3D: ({ src }: { src: string }) => <div data-testid="chat-model3d" data-src={src} />,
}));

vi.mock('./AttachmentCard', () => ({
  AttachmentCard: ({ attachment }: { attachment: Attachment }) => (
    <div data-testid="attachment-card" data-id={attachment.id} />
  ),
}));

import { AssistantInlineMedia } from './AssistantInlineMedia';

const att = (over: Partial<Attachment>): Attachment => ({
  id: 'a',
  name: 'a',
  type: '',
  size: 0,
  ...over,
});

describe('AssistantInlineMedia', () => {
  it('renders nothing for empty media', () => {
    const { container } = render(<AssistantInlineMedia media={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('routes media to image / video / card by kind', () => {
    render(
      <AssistantInlineMedia
        media={[
          att({ id: 'img', kind: 'image', previewUrl: '/p/img' }),
          att({ id: 'vid', kind: 'video', previewUrl: '/p/vid' }),
          att({ id: 'doc', kind: 'document' }),
        ]}
        native
      />,
    );
    expect(screen.getByTestId('chat-image')).toHaveAttribute('data-src', '/p/img');
    expect(screen.getByTestId('chat-video')).toHaveAttribute('data-src', '/p/vid');
    expect(screen.getByTestId('attachment-card')).toHaveAttribute('data-id', 'doc');
  });

  it('infers media kind from mime type when kind is absent', () => {
    render(<AssistantInlineMedia media={[att({ id: 'm', type: 'image/png', previewUrl: '/p/m' })]} />);
    expect(screen.getByTestId('chat-image')).toHaveAttribute('data-src', '/p/m');
  });

  it('renders generated 3D models inline instead of a download card', () => {
    render(
      <AssistantInlineMedia
        media={[
          att({ id: 'mesh', kind: 'model3d', previewUrl: '/p/mesh' }),
          att({ id: 'glb', name: 'hero.glb', previewUrl: '/p/glb' }),
        ]}
      />,
    );
    const viewers = screen.getAllByTestId('chat-model3d');
    expect(viewers).toHaveLength(2);
    expect(viewers[0]).toHaveAttribute('data-src', '/p/mesh');
    expect(viewers[1]).toHaveAttribute('data-src', '/p/glb');
  });
});
