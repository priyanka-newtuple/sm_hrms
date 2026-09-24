import { EmptyIcon } from "../shared/icons"

interface EmptyTabProps {
  title: string
  blurb: string
}

export function EmptyTab({ title, blurb }: EmptyTabProps) {
  return (
    <div className="border border-dashed border-border rounded-2xl p-[64px_32px] text-center bg-muted">
      <div className="w-[52px] h-[52px] rounded-[14px] bg-card border border-border flex items-center justify-center mx-auto mb-4 text-muted-foreground">
        <EmptyIcon width={26} height={26} />
      </div>
      <div className="text-base font-bold mb-[6px]">{title}</div>
      <div className="text-[13.5px] text-muted-foreground max-w-[420px] mx-auto mb-5 leading-relaxed">
        {blurb}
      </div>
      <button className="inline-flex items-center gap-[7px] py-[9px] px-4 rounded-[9px] border border-border bg-card text-[13.5px] font-semibold text-foreground cursor-pointer transition-colors hover:bg-muted">
        Configure
      </button>
    </div>
  )
}
