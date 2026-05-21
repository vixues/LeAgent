import { describe, expect, it } from 'vitest';
import {
  formatAgentPathLabel,
  formatWorkspaceDirLabel,
  isCodeExecWorkspaceDir,
  stripStoredUploadPrefix,
} from './agentPathDisplay';

describe('agentPathDisplay', () => {
  it('shortens legacy workspace directory keys', () => {
    expect(
      formatWorkspaceDirLabel(
        '00000000-0000-0000-0000-000000000001__35f3971b-d115-4db5-8b6a-eca9c717325e',
      ),
    ).toBe('local__35f3971b');
  });

  it('keeps compact workspace keys', () => {
    expect(formatWorkspaceDirLabel('local__35f3971b')).toBe('local__35f3971b');
  });

  it('strips full and short upload uuid prefixes', () => {
    expect(
      stripStoredUploadPrefix(
        '7bec7309-e393-403b-9d79-469f1abe26be_前海26年4月考勤餐补明细.xlsx',
      ),
    ).toBe('前海26年4月考勤餐补明细.xlsx');
    expect(stripStoredUploadPrefix('7bec7309_demo.csv')).toBe('demo.csv');
  });

  it('detects code-exec workspace roots', () => {
    expect(
      isCodeExecWorkspaceDir(
        '/home/yqc/.leagent/working/code-exec/00000000-0000-0000-0000-000000000001__35f3971b-d115-4db5-8b6a-eca9c717325e',
      ),
    ).toBe(true);
    expect(
      isCodeExecWorkspaceDir(
        '/home/yqc/.leagent/working/code-exec/local__35f3971b/out.csv',
      ),
    ).toBe(false);
  });

  it('formats agent path labels for files and workspaces', () => {
    expect(
      formatAgentPathLabel(
        '/home/yqc/.leagent/working/uploads/sess/7bec7309-e393-403b-9d79-469f1abe26be_report.xlsx',
      ),
    ).toBe('report.xlsx');
    expect(
      formatAgentPathLabel(
        '/home/yqc/.leagent/working/code-exec/local__35f3971b',
      ),
    ).toBe('local__35f3971b');
  });
});
