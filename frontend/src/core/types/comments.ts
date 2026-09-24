/**
 * Comment Types
 *
 * Types for the unified comment system that supports @mentions
 * and comments on any entity type.
 */

// Standard API response envelope used by every comments endpoint
export interface ApiEnvelope<T> {
    success: boolean;
    data: T | null;
    message: string;
    error_code: string | null;
  }
  
  // Mention info stored in comment
  export interface MentionInfo {
    user_id: string;
    full_name: string;
    position: number;
  }
  
  // Edit history entry for tracking comment edits
  export interface CommentEditHistoryEntry {
    previous_text: string;
    edited_at: string;
    edited_by_id: string;
    edited_by_name: string;
  }
  
  // Visibility options for comments
  export type CommentVisibility = 'all' | 'internal' | 'role_restricted';
  
  // Comment response from API
  export interface Comment {
    id: string;
    organization_id: string;
    entity_id: string;
    entity_type: string;
    workflow_id: string | null;
    state_id: string | null;
    state_name: string | null;
    text: string;
    mentions: MentionInfo[] | null;
    author_id: string | null;
    author_name: string;
    author_role: string | null;
    author_avatar_url: string | null;
    visibility: CommentVisibility;
    visible_to_roles: string[] | null;
    is_edited: boolean;
    edited_at: string | null;
    edit_history: CommentEditHistoryEntry[] | null;
    archived_at: string | null;
    archived_by: string | null;
    created_at: string;
  }
  
  // Create comment request
  export interface CommentCreate {
    text: string;
    workflow_id?: string;
    visibility?: CommentVisibility;
    visible_to_roles?: string[];
  }
  
  // Update comment request
  export interface CommentUpdate {
    text: string;
  }
  
  // List comments response
  export interface CommentListResponse {
    comments: Comment[];
    total: number;
  }
  
  // User search result for @mention autocomplete
  export interface UserSearchResult {
    id: string;
    full_name: string;
    email: string;
    role: string | null;
    avatar_url: string | null;
  }
  