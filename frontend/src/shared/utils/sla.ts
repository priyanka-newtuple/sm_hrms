export type SlaUnit = "none" | "minutes" | "hours" | "days";

export function slaToUnit(seconds: number | null): SlaUnit {
  if (!seconds) return "none";
  if (seconds % 86400 === 0) return "days";
  if (seconds % 3600 === 0) return "hours";
  return "minutes";
}

export function slaToAmount(seconds: number | null): string {
  if (!seconds) return "";
  if (seconds % 86400 === 0) return String(seconds / 86400);
  if (seconds % 3600 === 0) return String(seconds / 3600);
  return String(Math.round(seconds / 60));
}

export function buildSlaSeconds(amount: string, unit: SlaUnit): number | null {
  const n = Number(amount);
  if (!amount || isNaN(n) || n <= 0 || unit === "none") return null;
  if (unit === "minutes") return n * 60;
  if (unit === "hours") return n * 3600;
  return n * 86400;
}
