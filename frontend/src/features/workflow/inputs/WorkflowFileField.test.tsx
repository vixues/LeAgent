import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useGenUiFormsStore } from '@/stores/genUiForms';
import type { Attachment } from '@/types/chat';

import { WorkflowFileField } from './WorkflowFileField';

const ATTACHMENTS: Attachment[] = [
  {
    id: 'att-1',
    name: 'report.csv',
    type: 'text/csv',
    localPath: '/uploads/report.csv',
  },
];

describe('WorkflowFileField', () => {
  it('writes attachment path when a chip is clicked', () => {
    const onChange = vi.fn();
    render(
      <WorkflowFileField
        name="user_input"
        label="Input file"
        value=""
        onChange={onChange}
        attachments={ATTACHMENTS}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /report\.csv/i }));
    expect(onChange).toHaveBeenCalledWith('/uploads/report.csv');
  });

  it('allows manual path entry when no attachments exist', () => {
    const onChange = vi.fn();
    render(
      <WorkflowFileField
        name="source"
        label="Source"
        value=""
        onChange={onChange}
        attachments={[]}
      />,
    );
    const input = screen.getByPlaceholderText(/file path or attachment name/i);
    fireEvent.change(input, { target: { value: 'manual/path.pdf' } });
    expect(onChange).toHaveBeenCalledWith('manual/path.pdf');
  });
});

describe('WorkflowInputPanel form store integration', () => {
  it('seeds defaults into genUiForms store', async () => {
    const { WorkflowInputPanel } = await import('../components/WorkflowInputPanel');
    useGenUiFormsStore.getState().clearForm('scope::root::wf-test');
    render(
      <WorkflowInputPanel
        inputs={[{ name: 'q', type: 'string', default: 'hello' }]}
        formKey="wf-test"
        flowId="flow-1"
        includeSubmit={false}
      />,
    );
    expect(useGenUiFormsStore.getState().getValues('scope::root::wf-test').q).toBe('hello');
  });
});
