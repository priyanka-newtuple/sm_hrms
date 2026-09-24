/**
 * State Machine Hook
 *
 * Provides convenient access to state machine configuration
 * derived from the current skin's state machine definition.
 * This is a platform hook that works with any skin configuration.
 */

import { useSkin } from '../../skins';

interface TransitionInfo {
  /** Target state */
  toState: string;
  /** Trigger name to execute this transition */
  trigger: string;
  /** Human-readable label */
  label: string;
}

/**
 * Hook to access state machine configuration for the current skin
 */
export function useStateMachine() {
  const {
    pipelineStages,
    transitionTriggers,
    stateMachineDefinition,
    skin,
    loading,
    error,
  } = useSkin();

  /**
   * Format trigger name as a human-readable label
   * e.g., "start_screening" -> "Start Screening"
   */
  const formatTriggerLabel = (trigger: string): string => {
    return trigger
      .split('_')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  /**
   * Get available transitions from a given state
   */
  const getTransitionsFrom = (state: string): TransitionInfo[] => {
    const triggers = transitionTriggers[state] || {};
    return Object.entries(triggers).map(([toState, trigger]) => ({
      toState,
      trigger,
      label: formatTriggerLabel(trigger),
    }));
  };

  /**
   * Get the trigger name for a specific state transition
   * Returns null if transition is not valid
   */
  const getTrigger = (fromState: string, toState: string): string | null => {
    return transitionTriggers[fromState]?.[toState] || null;
  };

  /**
   * Check if a transition is valid
   */
  const canTransition = (fromState: string, toState: string): boolean => {
    return !!transitionTriggers[fromState]?.[toState];
  };

  /**
   * Get stage configuration by state name
   */
  const getStage = (state: string) => {
    return pipelineStages.find((s) => s.state === state);
  };

  /**
   * Get the color for a state (including terminal states)
   */
  const getStateColor = (state: string): string => {
    return skin.board.stateColors[state] || '#9ca3af';
  };

  /**
   * Check if a state is terminal (not on the board)
   */
  const isTerminalState = (state: string): boolean => {
    return skin.board.terminalStates.includes(state);
  };

  /**
   * Get terminal states list
   */
  const getTerminalStates = (): string[] => {
    return skin.board.terminalStates;
  };

  return {
    /** Pipeline stages (non-terminal states) */
    stages: pipelineStages,
    /** All transition triggers */
    transitionTriggers,
    /** Full state machine definition (if loaded) */
    definition: stateMachineDefinition,
    /** Loading state */
    loading,
    /** Error message if failed to load */
    error,
    /** Get available transitions from a state */
    getTransitionsFrom,
    /** Get trigger name for a transition */
    getTrigger,
    /** Check if transition is valid */
    canTransition,
    /** Get stage config by state */
    getStage,
    /** Get color for any state */
    getStateColor,
    /** Check if state is terminal */
    isTerminalState,
    /** Get list of terminal states */
    getTerminalStates,
    /** Format trigger as label */
    formatTriggerLabel,
  };
}
