type Task = { actions: string[] };
type Board = { cycles: Task[]; reviews: Task[]; assigned_feedback: Task[] };

// HR and manager tools offered on open items (reassigning, withdrawing, corrections), not work waiting on anyone.
const ALWAYS_AVAILABLE = new Set(['reassign', 'withdraw', 'correct_rating', 'add_participants', 'change_approver', 'reassign_feedback', 'cancel_feedback']);

/** Cycles, reviews and feedback with a next step waiting on the reader (My Work and the Performance page). */
export function awaitingYou<T extends Task>(board: { cycles: T[]; reviews: T[]; assigned_feedback: T[] } & Board): T[] {
  return [...board.cycles, ...board.reviews, ...board.assigned_feedback]
    .filter(item => item.actions.some(action => !ALWAYS_AVAILABLE.has(action)));
}
