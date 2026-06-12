import { describe, expect, it } from 'vitest';
import { nextTodoStatusOnClick } from './todoStatusUtils';

describe('nextTodoStatusOnClick', () => {
  it('cycles pending → in_progress → completed → pending', () => {
    expect(nextTodoStatusOnClick('pending')).toBe('in_progress');
    expect(nextTodoStatusOnClick('in_progress')).toBe('completed');
    expect(nextTodoStatusOnClick('completed')).toBe('pending');
  });

  it('resets terminal statuses to pending', () => {
    expect(nextTodoStatusOnClick('cancelled')).toBe('pending');
    expect(nextTodoStatusOnClick('failed')).toBe('pending');
  });
});
