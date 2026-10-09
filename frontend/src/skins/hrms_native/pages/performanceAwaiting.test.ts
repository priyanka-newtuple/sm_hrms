import { describe, expect, it } from 'vitest';
import { awaitingYou } from './performanceAwaiting';

describe('awaitingYou', () => {
  it('counts items with a next step and ignores the always-offered Reassign', () => {
    const board = {
      cycles: [{ id: 'cycle', actions: ['start_reviews'] }],
      reviews: [{ id: 'mine', actions: ['add_goal', 'submit_goals'] }, { id: 'hr-only', actions: ['reassign'] },
        { id: 'both', actions: ['reassign', 'calibrate'] }, { id: 'done', actions: [] }],
      assigned_feedback: [{ id: 'feedback', actions: ['submit_feedback'] }],
    };
    expect(awaitingYou(board).map(item => item.id)).toEqual(['cycle', 'mine', 'both', 'feedback']);
  });
});
