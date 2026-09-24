import { Button } from "@/core/components";

interface RoleDetailFooterProps {
  dirty: boolean
  isSaving?: boolean
  canSave?: boolean
  error?: string | null
  onSave: () => void
  onCancel: () => void
  canWrite?: boolean
}

export function RoleDetailFooter({
  dirty,
  isSaving,
  canSave = true,
  error,
  onSave,
  onCancel,
  canWrite = true,
}: RoleDetailFooterProps) {
  return (
    <div className="border-t border-border backdrop-blur-sm py-3.5 shrink-0">
      <div className="px-10 flex items-center justify-between">
        {error ? (
          <span className="text-[13px] text-destructive">{error}</span>
        ) : (
          <span className="text-[13px] text-muted-foreground">
            {dirty ? "Unsaved changes" : "All changes saved"}
          </span>
        )}
        <div className="flex gap-2.5">
          <Button
            variant="outline"
            size="lg"
            onClick={onCancel}
            className="cursor-pointer transition-colors"
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="lg"
            onClick={onSave}
            disabled={!canWrite || isSaving || !canSave}
            className="cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Saving…' : 'Save changes'}
          </Button>
        </div>
      </div>
    </div>
  )
}
