import type { User } from "@/core/types";

/** Action kind for the User Assignment workflow action. */
export const ENTITY_ASSIGN_USER_KIND = "entity.assign_user";

/** How the action picks its target. */
export type AssignmentType = "user" | "originator";

/** Label for one org user, matching how the record detail screen names them. */
export function userLabel(user: User): string {
  return user.full_name || user.email;
}
