/**
 * Stage Comment Types
 *
 * Types for stage-specific comments on entities with visibility controls,
 * edit tracking, and configurable requirements.
 */

import type { UserRole } from '../../../core/auth/types';

/** Visibility levels for stage comments */
export type CommentVisibility = 'all' | 'internal' | 'role_restricted';

/** Single edit history entry */
export interface EditHistoryEntry {
  text: string;
  edited_at: string;
  edited_by: string;
  edited_by_name: string;
}

/** Stage comment from the API */
export interface StageComment {
  comment_id: string;
  entity_id: string;
  entity_type: string;
  stage: string;
  text: string;
  author_id: string;
  author_name: string;
  author_role: UserRole;
  visibility: CommentVisibility;
  visible_to_roles?: string[];
  is_edited: boolean;
  edited_at?: string;
  edit_history?: EditHistoryEntry[];
  archived_at?: string;
  created_at: string;
}

/** Request to create a new comment */
export interface StageCommentCreate {
  stage: string;
  text: string;
  visibility?: CommentVisibility;
  visible_to_roles?: string[];
}

/** Request to update a comment */
export interface StageCommentUpdate {
  text: string;
}

/** Response from listing comments */
export interface StageCommentListResponse {
  comments: StageComment[];
  total: number;
}

/** Comment requirement configuration for a transition */
export interface CommentRequirement {
  enabled: boolean;
  roles: UserRole[];
  min_length?: number;
  label?: string;
  placeholder?: string;
}

/** Comment requirements for all transitions from current state */
export interface TransitionCommentRequirements {
  current_state: string;
  requirements: Record<string, CommentRequirement>;
}

/** Result of checking if a comment requirement is satisfied */
export interface CommentRequirementCheck {
  trigger: string;
  to_state?: string;
  requirement?: CommentRequirement;
  is_satisfied: boolean;
  existing_comment_id?: string;
  message?: string;
}
