import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useGenUiFormsStore } from '@/stores/genUiForms';

import { WorkflowInputPanel } from './WorkflowInputPanel';

vi.mock('../hooks/useWorkflowInputRun', () => ({
  useWorkflowInputRun: () => ({ run: vi.fn().mockResolvedValue(undefined) }),
}));

describe('WorkflowInputPanel', () => {
  beforeEach(() => {
    useGenUiFormsStore.setState({ values: {} });
  });

  it('renders string and boolean fields', () => {
    render(
      <WorkflowInputPanel
        inputs={[
          { name: 'title', type: 'string', label: 'Title', required: true },
          { name: 'enabled', type: 'boolean', label: 'Enabled' },
        ]}
        formKey="wf-panel"
        flowId="flow-1"
        includeSubmit
      />,
    );
    expect(screen.getByLabelText(/title/i)).toBeTruthy();
    expect(screen.getByRole('switch')).toBeTruthy();
    expect(screen.getByRole('button', { name: /run|运行/i })).toBeTruthy();
  });

  it('updates form store on edit', async () => {
    render(
      <WorkflowInputPanel
        inputs={[{ name: 'q', type: 'string', label: 'Query' }]}
        formKey="wf-edit"
        flowId="flow-1"
        includeSubmit={false}
      />,
    );
    fireEvent.change(screen.getByLabelText('Query'), { target: { value: 'search me' } });
    await waitFor(() => {
      expect(useGenUiFormsStore.getState().getValues('scope::root::wf-edit').q).toBe('search me');
    });
  });
});
