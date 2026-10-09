type Task = { actions: string[] };
type Board = { cycles: Task[]; reviews: Task[]; assigned_feedback: Task[] };

// Reassign is an HR tool offered on every open review, not work waiting on anyone.
const ALWAYS_AVAILABLE = new Set(['reassign']);

/** Cycles, reviews and feedback with a next step waiting on the reader (My Work and the Performance page). */
export function awaitingYou<T extends Task>(board: { cycles: T[]; reviews: T[]; assigned_feedback: T[] } & Board): T[] {
  return [...board.cycles, ...board.reviews, ...board.assigned_feedback]
    .filter(item => item.actions.some(action => !ALWAYS_AVAILABLE.has(action)));
}
