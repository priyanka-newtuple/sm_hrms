export function isSafeUrl(url: string): boolean {
  const s = (url || "").trim().toLowerCase();
  return (
    s.startsWith("https://") ||
    s.startsWith("http://") ||
    s.startsWith("/") ||
    s.startsWith("#") ||
    s.startsWith("{{")
  );
}

export function escapeHTML(str: string): string {
  return String(str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function sanitizeDOM(root: HTMLElement): void {
  root.querySelectorAll("script, style").forEach((el) => el.remove());
  root.querySelectorAll("*").forEach((el) => {
    Array.from(el.attributes).forEach((attr) => {
      if (/^on/i.test(attr.name)) el.removeAttribute(attr.name);
      if (attr.name === "href" && !isSafeUrl(attr.value)) el.removeAttribute(attr.name);
      if (attr.name === "src" && !isSafeUrl(attr.value)) el.removeAttribute(attr.name);
    });
  });
}

export function replaceVarsInTextNodes(
  root: HTMLElement,
  make: (name: string) => Node,
): void {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
  const targets: Text[] = [];
  const probe = /\{\{\s*[\w.]+\s*\}\}/;
  let n: Node | null;
  while ((n = walker.nextNode())) {
    if (probe.test((n as Text).nodeValue ?? "")) targets.push(n as Text);
  }
  const re = /\{\{\s*([\w.]+)\s*\}\}/g;
  for (const t of targets) {
    const s = t.nodeValue ?? "";
    const frag = document.createDocumentFragment();
    let last = 0;
    let m: RegExpExecArray | null;
    re.lastIndex = 0;
    while ((m = re.exec(s)) !== null) {
      if (m.index > last) frag.appendChild(document.createTextNode(s.slice(last, m.index)));
      frag.appendChild(make(m[1]));
      last = m.index + m[0].length;
    }
    if (last < s.length) frag.appendChild(document.createTextNode(s.slice(last)));
    t.parentNode?.replaceChild(frag, t);
  }
}

// Converts stored HTML ({{varname}}) to Tiptap-loadable HTML (chip spans).
export function hydrateHTML(html: string): string {
  if (!html) return "<p><br></p>";
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  replaceVarsInTextNodes(tmp, (name) => {
    const chip = document.createElement("span");
    chip.className = "var-chip";
    chip.setAttribute("data-var", name);
    chip.setAttribute("contenteditable", "false");
    chip.textContent = name;
    return chip;
  });
  return tmp.innerHTML;
}

// Converts Tiptap output HTML (chip spans) back to stored format ({{varname}}).
export function cleanHTML(html: string): string {
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  tmp.querySelectorAll("span[data-var], .var-chip").forEach((c) => {
    const name = c.getAttribute("data-var") || c.textContent?.replace(/[{}]/g, "") || "";
    c.replaceWith(`{{${name}}}`);
  });
  sanitizeDOM(tmp);
  return tmp.innerHTML;
}

// For preview: renders {{varname}} as visible chip spans without editor dependency.
export function htmlToPreview(html: string): string {
  if (!html) return "";
  const tmp = document.createElement("div");
  tmp.innerHTML = html;
  sanitizeDOM(tmp);
  replaceVarsInTextNodes(tmp, (name) => {
    const chip = document.createElement("span");
    chip.className = "var-chip";
    chip.textContent = name;
    return chip;
  });
  return tmp.innerHTML;
}
