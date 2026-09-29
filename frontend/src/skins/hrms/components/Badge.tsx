type Tone = "neutral" | "success" | "warning" | "danger" | "info";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-gray-50 text-gray-600",
  success: "bg-success/10 text-success",
  warning: "bg-highlight/10 text-highlight",
  danger: "bg-danger/10 text-danger",
  info: "bg-cobalt/10 text-cobalt",
};

const STATUS_TONE: Record<string, Tone> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
  rejected: "danger",
  active: "success",
  on_hold: "warning",
  completed: "neutral",
  planned: "info",
  open: "info",
  assigned: "warning",
  in_progress: "warning",
  resolved: "success",
  closed: "neutral",
  in_stock: "neutral",
  under_repair: "warning",
  retired: "neutral",
  not_started: "neutral",
  low: "neutral",
  medium: "info",
  high: "warning",
  urgent: "danger",
};

export function Badge({ tone, children }: { tone?: Tone; children: string }) {
  const resolved = tone ?? STATUS_TONE[children.toLowerCase()] ?? "neutral";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium capitalize ${TONE_CLASSES[resolved]}`}
    >
      {children.replace(/_/g, " ")}
    </span>
  );
}
