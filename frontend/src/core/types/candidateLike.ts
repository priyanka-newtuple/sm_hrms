/**
 * Candidate Like Types
 *
 * Types for the team interest (likes) feature on candidates.
 */

/**
 * Full like record returned from API
 */
export interface CandidateLike {
  id: string;
  organization_id: string;
  candidate_id: string;
  user_id: string;
  user_name: string;
  user_role: string;
  user_avatar_url: string | null;
  created_at: string;
}

/**
 * Minimal data for avatar stack display
 */
export interface CandidateLikeSummary {
  user_id: string;
  user_name: string;
  user_avatar_url: string | null;
}

/**
 * Response from listing likes for a single candidate
 */
export interface CandidateLikeListResponse {
  likes: CandidateLike[];
  total: number;
  current_user_liked: boolean;
}

/**
 * Summary for a single candidate in bulk response
 */
export interface CandidateLikeBulkItem {
  candidate_id: string;
  count: number;
  users: CandidateLikeSummary[];
  current_user_liked: boolean;
}

/**
 * Response from bulk fetch endpoint
 */
export interface BulkLikesSummaryResponse {
  items: Record<string, CandidateLikeBulkItem>;
}
