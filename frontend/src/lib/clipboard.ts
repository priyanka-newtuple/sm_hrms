/** Copy text in both standard and embedded browser contexts. */
export async function copyTextToClipboard(text: string): Promise<void> {
  const copyTarget = document.createElement('textarea');
  copyTarget.value = text;
  copyTarget.setAttribute('readonly', '');
  copyTarget.style.position = 'fixed';
  copyTarget.style.opacity = '0';
  document.body.appendChild(copyTarget);
  copyTarget.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(copyTarget);

  if (!copied) {
    await navigator.clipboard.writeText(text);
  }
}
