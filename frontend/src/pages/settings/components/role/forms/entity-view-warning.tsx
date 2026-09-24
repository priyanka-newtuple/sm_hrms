import { EyeOffIcon } from "../shared/icons"

// Shown when the role can't view the active entity — field rules below are inert.
export function EntityViewWarning({ entity }: { entity: string }) {
  return (
    <div className="flex gap-[11px] items-start py-3 px-[15px] rounded-[11px] mb-4 border border-warning/30 bg-warning-subtle">
      <span className="text-warning flex mt-[1px]">
        <EyeOffIcon width={16} height={16} />
      </span>
      <div className="text-[13px] text-warning leading-[1.5]">
        This role can&apos;t view <strong>{entity}</strong> records. Field rules below won&apos;t
        apply until you enable <strong>View</strong> in the Entity Access tab.
      </div>
    </div>
  )
}
