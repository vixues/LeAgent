import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatTerminalReasonBanner } from '@/components/chat/ChatTerminalReasonBanner';
import { useChatStore } from '@/stores/chat';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}));

const resumeMock = vi.fn();
vi.mock('@/hooks/useCheckpointResume', () => ({
  useCheckpointResume: () => resumeMock,
}));

describe('ChatTerminalReasonBanner', () => {
  beforeEach(() => {
    resumeMock.mockReset();
    useChatStore.setState({
      lastTerminalReason: null,
      lastCheckpointId: null,
      isStreaming: false,
      currentSessionId: 'sess-1',
    });
  });

  it('shows Continue after user abort when checkpoint is available', () => {
    useChatStore.setState({
      lastTerminalReason: 'aborted_streaming',
      lastCheckpointId: 'cp-1',
    });
    render(<ChatTerminalReasonBanner />);
    expect(screen.getByText('Stopped by user')).toBeInTheDocument();
    const continueBtn = screen.getByRole('button', { name: 'Continue' });
    fireEvent.click(continueBtn);
    expect(resumeMock).toHaveBeenCalledWith('sess-1');
  });

  it('hides Continue when checkpoint is missing', () => {
    useChatStore.setState({
      lastTerminalReason: 'aborted_streaming',
      lastCheckpointId: null,
    });
    render(<ChatTerminalReasonBanner />);
    expect(screen.getByText('Stopped by user')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Continue' })).toBeNull();
  });

  it('shows Continue for max_turns with checkpoint', () => {
    useChatStore.setState({
      lastTerminalReason: 'max_turns',
      lastCheckpointId: 'cp-2',
    });
    render(<ChatTerminalReasonBanner />);
    expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
  });
});
