/** Trigger a browser download for a Blob via a transient object URL. */
export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/** Pretty-print a value as JSON and download it using the existing browser flow. */
export function downloadJson(value: unknown, filename: string): void {
  const content = JSON.stringify(value, null, 2);
  const blob = new Blob([content], { type: 'application/json;charset=utf-8' });
  triggerDownload(blob, filename);
}
