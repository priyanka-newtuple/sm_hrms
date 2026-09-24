import { Loader2 } from "lucide-react";

import type { User } from "@/core/types";

import { userLabel, type AssignmentType } from "./userAssignment";

interface UserAssignmentActionFieldsProps {
  users: User[];
  loading: boolean;
  assignmentType: AssignmentType;
  onAssignmentTypeChange: (value: AssignmentType) => void;
  userId: string;
  onUserIdChange: (value: string) => void;
}

/** Target controls for the User Assignment action: originator, or a chosen user. */
export function UserAssignmentActionFields({
  users,
  loading,
  assignmentType,
  onAssignmentTypeChange,
  userId,
  onUserIdChange,
}: UserAssignmentActionFieldsProps) {
  return (
    <>
      <div className="space-y-1.5">
        <label className="text-xs font-medium">Assignment target</label>
        <select
          value={assignmentType}
          onChange={(e) => onAssignmentTypeChange(e.target.value as AssignmentType)}
          className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="originator">Originator</option>
          <option value="user">Specific user</option>
        </select>
        <p className="text-xs text-muted-foreground">
          {assignmentType === "originator"
            ? "Assigns the record to whoever created it, resolved when the action runs."
            : "Assigns the record to the same user every time this state is entered."}
        </p>
      </div>

      {assignmentType === "user" && (
        <div className="space-y-1.5">
          <label className="text-xs font-medium">
            User <span className="text-destructive">*</span>
          </label>
          {loading ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> Loading users…
            </div>
          ) : (
            <select
              value={userId}
              onChange={(e) => onUserIdChange(e.target.value)}
              className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">Select user…</option>
              {users.map((user) => (
                <option key={user.id} value={user.id}>
                  {userLabel(user)}
                </option>
              ))}
            </select>
          )}
        </div>
      )}
    </>
  );
}
