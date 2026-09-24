import React, { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Underline from "@tiptap/extension-underline";
import { TextStyle } from "@tiptap/extension-text-style";
import { Color } from "@tiptap/extension-color";
import Highlight from "@tiptap/extension-highlight";
import TextAlign from "@tiptap/extension-text-align";
import Link from "@tiptap/extension-link";
import Image from "@tiptap/extension-image";
import CharacterCount from "@tiptap/extension-character-count";
import Placeholder from "@tiptap/extension-placeholder";
import { VariableChipNode } from "../extensions/VariableChipNode.ts";
import {
  cleanHTML,
  hydrateHTML,
  isSafeUrl,
  escapeHTML,
} from "../utils/html.ts";
import {
  IconBold, IconItalic, IconUnderline, IconList, IconListOrdered,
  IconLink, IconImage, IconUndo, IconRedo,
  IconAlignLeft, IconAlignCenter, IconAlignRight, IconButton,
  IconHighlight, IconCode, IconType, IconChevron, IconSparkle,
} from "./Icons.tsx";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button.tsx";
import type { Variable } from "../types";
import { Input } from "@/components/ui/input.tsx";
import { Label } from "@/components/ui/label.tsx";

// theme-exempt:start — WYSIWYG. Everything below styles the composed email
// itself, which renders on white in the recipient's client. These stay light in
// dark mode on purpose: they are content, not chrome.
const richContentClass = cn(
  "min-h-[280px] max-h-[60vh] overflow-y-auto bg-white text-sm leading-7 text-slate-900 outline-none",
  "[&_.ProseMirror]:min-h-[280px] [&_.ProseMirror]:px-5 [&_.ProseMirror]:py-4 [&_.ProseMirror]:outline-none",
  "[&_p]:mb-3 [&_h1]:mb-2 [&_h1]:mt-5 [&_h1]:text-2xl [&_h1]:font-bold [&_h1]:tracking-tight",
  "[&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-xl [&_h2]:font-bold [&_h2]:tracking-tight",
  "[&_h3]:mb-1.5 [&_h3]:mt-4 [&_h3]:text-base [&_h3]:font-semibold",
  "[&_ul]:mb-3 [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:mb-3 [&_ol]:list-decimal [&_ol]:pl-6",
  "[&_li]:my-1 [&_a]:text-blue-600 [&_a]:underline [&_hr]:my-4 [&_hr]:border-slate-200",
  "[&_img]:max-w-full [&_img]:rounded-md",
  "[&_.email-btn]:my-1 [&_.email-btn]:inline-block [&_.email-btn]:rounded-lg [&_.email-btn]:bg-blue-600 [&_.email-btn]:px-4 [&_.email-btn]:py-2.5 [&_.email-btn]:font-semibold [&_.email-btn]:text-white [&_.email-btn]:no-underline",
  "[&_.var-chip]:mx-px [&_.var-chip]:inline-flex [&_.var-chip]:select-all [&_.var-chip]:items-center [&_.var-chip]:rounded-md [&_.var-chip]:bg-blue-50 [&_.var-chip]:px-2 [&_.var-chip]:py-0.5 [&_.var-chip]:font-mono [&_.var-chip]:text-[12px] [&_.var-chip]:font-medium [&_.var-chip]:text-blue-700",
);
// theme-exempt:end

// Link extension extended to preserve class attribute (needed for email-btn CTAs)
const CustomLink = Link.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      class: {
        default: null,
        parseHTML: (element) => element.getAttribute("class"),
        renderHTML: (attributes) => {
          if (!attributes.class) return {};
          return { class: attributes.class };
        },
      },
    };
  },
}).configure({ openOnClick: false });

const TEXT_COLORS = [
  "#0b1220", "#5b6577", "#8a93a3", "#2f6bff", "#1c4ed8", "#7c3aed", "#db2777", "#d4283d",
  "#ea580c", "#ca8a04", "#15803d", "#0e9488", "#0284c7", "#6366f1", "#a16207", "#000000",
];
const HIGHLIGHT_COLORS = [
  "transparent", "#fef3c7", "#fee2e2", "#dcfce7", "#dbeafe", "#ede9fe", "#fce7f3", "#ffedd5",
];

// --- toolbar button ---------------------------------------------------------
interface ToolbarBtnProps {
  active?: boolean;
  disabled?: boolean;
  onMouseDown?: (e: React.MouseEvent) => void;
  title?: string;
  children: React.ReactNode;
}
function ToolbarBtn({ active, disabled, onMouseDown, title, children }: ToolbarBtnProps) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex h-7 min-w-7 items-center justify-center gap-1 rounded-md border border-transparent px-1.5 text-foreground transition",
        "hover:bg-muted",
        active && "border-border bg-card text-foreground shadow-sm",
      )}
      disabled={disabled}
      title={title}
      onMouseDown={(e) => { e.preventDefault(); onMouseDown?.(e); }}
    >
      {children}
    </button>
  );
}

// --- popovers ---------------------------------------------------------------
interface LinkPopoverProps {
  x: number; y: number;
  initialUrl: string; initialText: string;
  onCancel: () => void;
  onApply: (url: string, text: string) => void;
}
function LinkPopover({ x, y, initialUrl, initialText, onCancel, onApply }: LinkPopoverProps) {
  const [url, setUrl] = useState(initialUrl);
  const [text, setText] = useState(initialText);
  const urlRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setTimeout(() => urlRef.current?.focus(), 50); }, []);
  return (
    <div
      className="absolute z-40 min-w-[300px] rounded-xl border border-border bg-card p-3 shadow-2xl shadow-slate-900/10"
      style={{ left: x, top: y }}
    >
      <Label className="mb-1 block text-[11px] text-muted-foreground">URL</Label>
      <Input ref={urlRef} value={url} onChange={(e) => setUrl(e.target.value)}
        placeholder="https://example.com"
        onKeyDown={(e) => { if (e.key === "Enter") onApply(url, text); if (e.key === "Escape") onCancel(); }} />
      <div className="h-2" />
      <Label className="mb-1 block text-[11px] text-muted-foreground">Text (optional)</Label>
      <Input value={text} onChange={(e) => setText(e.target.value)}
        placeholder="Display text"
        onKeyDown={(e) => { if (e.key === "Enter") onApply(url, text); if (e.key === "Escape") onCancel(); }} />
      <div className="mt-2.5 flex justify-end gap-1.5">
        <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="sm" onClick={() => onApply(url, text)}>Add link</Button>
      </div>
    </div>
  );
}

interface ButtonPopoverState { x: number; y: number; url: string; label: string; }
interface ButtonPopoverProps extends ButtonPopoverState {
  onChange: (patch: Partial<ButtonPopoverState>) => void;
  onCancel: () => void;
  onApply: () => void;
}
function ButtonPopover({ x, y, url, label, onChange, onCancel, onApply }: ButtonPopoverProps) {
  const labelRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setTimeout(() => labelRef.current?.focus(), 50); }, []);
  return (
    <div
      className="absolute z-40 min-w-[300px] rounded-xl border border-border bg-card p-3 shadow-2xl shadow-slate-900/10"
      style={{ left: x, top: y }}
    >
      <Label className="mb-1 block text-[11px] text-muted-foreground">Button text</Label>
      <Input ref={labelRef} value={label} onChange={(e) => onChange({ label: e.target.value })}
        onKeyDown={(e) => { if (e.key === "Enter") onApply(); if (e.key === "Escape") onCancel(); }} />
      <div className="h-2" />
      <Label className="mb-1 block text-[11px] text-muted-foreground">Link to (use {"{{form_link}}"} for the form URL)</Label>
      <Input value={url} onChange={(e) => onChange({ url: e.target.value })}
        placeholder="https://… or {{form_link}}"
        onKeyDown={(e) => { if (e.key === "Enter") onApply(); if (e.key === "Escape") onCancel(); }} />
      <div className="mt-2.5 flex justify-end gap-1.5">
        <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="sm" onClick={onApply}>Insert button</Button>
      </div>
    </div>
  );
}

interface ImagePopoverState { x: number; y: number; url: string; }
interface ImagePopoverProps extends ImagePopoverState {
  onChange: (patch: Partial<ImagePopoverState>) => void;
  onCancel: () => void;
  onApply: () => void;
}
function ImagePopover({ x, y, url, onChange, onCancel, onApply }: ImagePopoverProps) {
  const urlRef = useRef<HTMLInputElement>(null);
  useEffect(() => { setTimeout(() => urlRef.current?.focus(), 50); }, []);
  return (
    <div
      className="absolute z-40 min-w-[320px] rounded-xl border border-border bg-card p-3 shadow-2xl shadow-slate-900/10"
      style={{ left: x, top: y }}
    >
      <Label className="mb-1 block text-[11px] text-muted-foreground">Image URL</Label>
      <Input ref={urlRef} value={url} onChange={(e) => onChange({ url: e.target.value })}
        placeholder="https://…/image.png"
        onKeyDown={(e) => { if (e.key === "Enter") onApply(); if (e.key === "Escape") onCancel(); }} />
      <div className="mt-2.5 flex justify-end gap-1.5">
        <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="sm" onClick={onApply}>Insert image</Button>
      </div>
    </div>
  );
}

interface ColorPopoverState { x: number; y: number; type: "fore" | "back"; }
interface SlashState {
  x: number;
  y: number;
  query: string;
  trigger: string;
  rangeFrom: number;
  rangeTo: number;
}

// --- main editor ------------------------------------------------------------
interface RichEditorProps {
  value: string;
  onChange: (v: string) => void;
  variables: Variable[];
  disabled?: boolean;
}

export function RichEditor({ value, onChange, variables, disabled = false }: RichEditorProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const sourceRef = useRef<HTMLTextAreaElement>(null);
  const [mode, setMode] = useState<"rich" | "source">("rich");
  const [focused, setFocused] = useState(false);
  const [linkPopover, setLinkPopover] = useState<{ x: number; y: number; initialText: string; initialUrl: string } | null>(null);
  const [btnPopover, setBtnPopover] = useState<ButtonPopoverState | null>(null);
  const [imgPopover, setImgPopover] = useState<ImagePopoverState | null>(null);
  const [colorPopover, setColorPopover] = useState<ColorPopoverState | null>(null);
  const [slash, setSlash] = useState<SlashState | null>(null);
  const [slashIdx, setSlashIdx] = useState(0);
  const isInternalUpdate = useRef(false);

  const closeFloatingUi = useCallback((keep?: "link" | "button" | "image" | "color" | "slash") => {
    if (keep !== "link") setLinkPopover(null);
    if (keep !== "button") setBtnPopover(null);
    if (keep !== "image") setImgPopover(null);
    if (keep !== "color") setColorPopover(null);
    if (keep !== "slash") setSlash(null);
  }, []);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3] } }),
      Underline,
      TextStyle,
      Color,
      Highlight.configure({ multicolor: true }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      CustomLink,
      Image,
      CharacterCount,
      Placeholder.configure({
        placeholder: "Write your email body here. Type / or {{ to insert a variable…",
      }),
      VariableChipNode,
    ],
    content: hydrateHTML(value),
    editable: !disabled,
    onUpdate: ({ editor }) => {
      isInternalUpdate.current = true;
      onChange(cleanHTML(editor.getHTML()));
    },
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
  });

  // Sync external value changes into editor (e.g. switching templates)
  useEffect(() => {
    if (!editor || mode !== "rich") return;
    if (isInternalUpdate.current) {
      isInternalUpdate.current = false;
      return;
    }
    editor.commands.setContent(hydrateHTML(value), { emitUpdate: false });
  }, [value, editor, mode]);

  useEffect(() => {
    editor?.setEditable(!disabled);
  }, [editor, disabled]);

  // Sync to source textarea when entering source mode
  useEffect(() => {
    if (mode === "source" && sourceRef.current) {
      sourceRef.current.value = value || "";
    }
  }, [mode, value]);

  // --- slash menu detection ---
  const checkTrigger = useCallback(() => {
    if (!editor || mode !== "rich") return;
    const { state } = editor;
    const { from } = state.selection;
    const textBefore = state.doc.textBetween(Math.max(0, from - 60), from, "\0", "\0");

    let m = textBefore.match(/(?:^|\s|\0)\/([\w.]*)$/);
    let trigger = "/";
    if (!m) { m = textBefore.match(/\{\{([\w.]*)$/); trigger = "{{"; }
    if (!m) { setSlash(null); return; }

    const query = m[1] ?? "";
    const rangeFrom = from - (trigger.length + query.length);
    const domSel = window.getSelection();
    if (!domSel || !domSel.rangeCount) { setSlash(null); return; }
    const range = domSel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const wrapRect = wrapRef.current?.getBoundingClientRect() ?? { left: 0, top: 0 };

    setSlash({
      x: rect.left - wrapRect.left,
      y: rect.bottom - wrapRect.top + 6,
      query,
      trigger,
      rangeFrom,
      rangeTo: from,
    });
    setSlashIdx(0);
  }, [editor, mode]);

  const filteredVars = useMemo(() => {
    const all = variables;
    if (!slash) return all;
    const q = slash.query.toLowerCase();
    if (!q) return all;
    return all.filter(
      (v) => v.key.toLowerCase().includes(q) || (v.label?.toLowerCase().includes(q) ?? false),
    );
  }, [slash, variables]);

  const insertVariable = useCallback((varKey: string) => {
    if (!editor) return;
    const content = [
      { type: "variableChip", attrs: { variable: varKey } },
      { type: "text", text: " " },
    ];

    if (slash) {
      editor
        .chain()
        .focus()
        .insertContentAt({ from: slash.rangeFrom, to: slash.rangeTo }, content)
        .run();
    } else {
      editor
        .chain()
        .focus()
        .insertContent(content)
        .run();
    }
    setSlash(null);
  }, [editor, slash]);

  // --- toolbar popover helpers ---
  const getAnchorPos = (anchorEl?: HTMLElement | null) => {
    if (anchorEl && wrapRef.current) {
      const rect = anchorEl.getBoundingClientRect();
      const wrapRect = wrapRef.current.getBoundingClientRect();
      return {
        x: rect.left - wrapRect.left,
        y: rect.bottom - wrapRect.top + 8,
      };
    }

    const domSel = window.getSelection();
    let x = 80, y = 80;
    if (domSel && domSel.rangeCount > 0 && wrapRef.current) {
      const rect = domSel.getRangeAt(0).getBoundingClientRect();
      const wrapRect = wrapRef.current.getBoundingClientRect();
      x = rect.left - wrapRect.left;
      y = rect.bottom - wrapRect.top + 8;
    }
    return { x, y };
  };

  const openLinkPopover = useCallback((anchorEl?: HTMLElement | null) => {
    if (!editor) return;
    if (linkPopover) {
      setLinkPopover(null);
      return;
    }
    const { x, y } = getAnchorPos(anchorEl);
    const initialText = editor.state.selection.empty
      ? ""
      : editor.state.doc.textBetween(editor.state.selection.from, editor.state.selection.to);
    const existingHref = editor.getAttributes("link").href ?? "https://";
    closeFloatingUi("link");
    setLinkPopover({ x, y, initialText, initialUrl: existingHref });
  }, [closeFloatingUi, editor, linkPopover]);

  const applyLink = (url: string, text: string) => {
    if (!editor) return;
    const safeUrl = isSafeUrl(url) ? url : "#";
    if (text && editor.state.selection.empty) {
      editor.chain().focus().insertContent(
        `<a href="${escapeHTML(safeUrl)}" target="_blank">${escapeHTML(text)}</a>`
      ).run();
    } else {
      editor.chain().focus().setLink({ href: safeUrl, target: "_blank" }).run();
    }
    closeFloatingUi();
  };

  const openButtonPopover = (anchorEl?: HTMLElement | null) => {
    if (btnPopover) {
      setBtnPopover(null);
      return;
    }
    const { x, y } = getAnchorPos(anchorEl);
    closeFloatingUi("button");
    setBtnPopover({ x, y, url: "https://", label: "Open Form" });
  };

  const applyButton = (url: string, label: string) => {
    if (!editor) return;
    const safeUrl = isSafeUrl(url) ? url : "#";
    editor.chain().focus().insertContent(
      `<p><a href="${escapeHTML(safeUrl)}" class="email-btn" target="_blank">${escapeHTML(label)}</a></p>`
    ).run();
    closeFloatingUi();
  };

  const openImagePopover = (anchorEl?: HTMLElement | null) => {
    if (imgPopover) {
      setImgPopover(null);
      return;
    }
    const { x, y } = getAnchorPos(anchorEl);
    closeFloatingUi("image");
    setImgPopover({ x, y, url: "" });
  };

  const applyImage = (url: string) => {
    if (!editor || !isSafeUrl(url)) { closeFloatingUi(); return; }
    editor.chain().focus().setImage({ src: url }).run();
    closeFloatingUi();
  };

  const openColorPopover = (type: "fore" | "back", btnEl: HTMLElement) => {
    if (colorPopover?.type === type) {
      setColorPopover(null);
      return;
    }
    if (!wrapRef.current) return;
    const rect = btnEl.getBoundingClientRect();
    const wrapRect = wrapRef.current.getBoundingClientRect();
    closeFloatingUi("color");
    setColorPopover({ x: rect.left - wrapRect.left, y: rect.bottom - wrapRect.top + 4, type });
  };

  const applyColor = (color: string) => {
    if (!editor || !colorPopover) return;
    if (colorPopover.type === "fore") {
      editor.chain().focus().setColor(color).run();
    } else {
      if (color === "transparent") {
        editor.chain().focus().unsetHighlight().run();
      } else {
        editor.chain().focus().setHighlight({ color }).run();
      }
    }
    closeFloatingUi();
  };

  const setBlock = (value: string, level?: number) => {
    if (!editor) return;
    if (value === "paragraph") {
      editor.chain().focus().setParagraph().run();
    } else if (value === "heading" && level) {
      editor.chain().focus().toggleHeading({ level: level as 1 | 2 | 3 }).run();
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (slash) {
      if (e.key === "ArrowDown") { e.preventDefault(); setSlashIdx((i) => Math.min(i + 1, filteredVars.length - 1)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSlashIdx((i) => Math.max(i - 1, 0)); return; }
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        const v = filteredVars[slashIdx];
        if (v) insertVariable(v.key);
        return;
      }
      if (e.key === "Escape") { e.preventDefault(); setSlash(null); return; }
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      openLinkPopover();
    }
  };

  const switchMode = (m: "rich" | "source") => {
    if (m === mode) return;
    if (m === "rich" && editor) {
      editor.commands.setContent(hydrateHTML(value), { emitUpdate: false });
    }
    setMode(m);
  };

  // Close popovers on outside click
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current) return;
      if (wrapRef.current.contains(e.target as Node)) return;
      closeFloatingUi();
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [closeFloatingUi]);

  const charCountStorage = editor?.storage.characterCount as
    | { words: () => number; characters: () => number }
    | undefined;
  const wordCount = charCountStorage?.words() ?? 0;
  const charCount = charCountStorage?.characters() ?? 0;

  const activeBlock = (() => {
    if (!editor) return "paragraph";
    if (editor.isActive("heading", { level: 1 })) return "h1";
    if (editor.isActive("heading", { level: 2 })) return "h2";
    if (editor.isActive("heading", { level: 3 })) return "h3";
    return "paragraph";
  })();

  const blockLabel = activeBlock === "h1" ? "Heading 1"
    : activeBlock === "h2" ? "Heading 2"
    : activeBlock === "h3" ? "Heading 3"
    : "Paragraph";

  return (
    <div
      className={cn(
        // WYSIWYG: the writing surface matches the white the email renders on.
        "relative overflow-visible rounded-xl border bg-card transition",
        focused
          ? "border-border shadow-[0_0_0_3px_rgba(15,23,42,0.08)]"
          : "border-border shadow-sm",
      )}
      ref={wrapRef}
      onKeyDown={handleKeyDown}
    >
      <div
        className="flex flex-wrap items-center gap-2 rounded-t-xl border-b border-border bg-muted/50 px-3 py-2"
        onMouseDown={(e) => e.preventDefault()}
      >
        <div className="flex items-center gap-1 pr-1">
          <ToolbarBtn title="Undo (⌘Z)" disabled={disabled} onMouseDown={() => editor?.chain().focus().undo().run()}>
            <IconUndo />
          </ToolbarBtn>
          <ToolbarBtn title="Redo (⌘⇧Z)" disabled={disabled} onMouseDown={() => editor?.chain().focus().redo().run()}>
            <IconRedo />
          </ToolbarBtn>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1 pr-1">
          <DropdownMenu>
            <DropdownMenuTrigger
              disabled={disabled}
              className="inline-flex h-7 items-center gap-1 rounded-md px-2 text-sm text-foreground transition hover:bg-muted"
              title="Text style"
            >
              {blockLabel}
              <IconChevron className="h-3 w-3" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="min-w-36 rounded-xl border border-border bg-card p-1 shadow-lg shadow-slate-900/10">
              <DropdownMenuItem className={cn(activeBlock === "paragraph" && "bg-muted text-foreground")} onClick={() => setBlock("paragraph")}>Paragraph</DropdownMenuItem>
              <DropdownMenuItem className={cn(activeBlock === "h1" && "bg-muted text-foreground")} onClick={() => setBlock("heading", 1)}>Heading 1</DropdownMenuItem>
              <DropdownMenuItem className={cn(activeBlock === "h2" && "bg-muted text-foreground")} onClick={() => setBlock("heading", 2)}>Heading 2</DropdownMenuItem>
              <DropdownMenuItem className={cn(activeBlock === "h3" && "bg-muted text-foreground")} onClick={() => setBlock("heading", 3)}>Heading 3</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1 pr-1">
          <ToolbarBtn title="Bold (⌘B)" disabled={disabled} active={editor?.isActive("bold") ?? false}
            onMouseDown={() => editor?.chain().focus().toggleBold().run()}>
            <IconBold className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Italic (⌘I)" disabled={disabled} active={editor?.isActive("italic") ?? false}
            onMouseDown={() => editor?.chain().focus().toggleItalic().run()}>
            <IconItalic className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Underline (⌘U)" disabled={disabled} active={editor?.isActive("underline") ?? false}
            onMouseDown={() => editor?.chain().focus().toggleUnderline().run()}>
            <IconUnderline className="h-3.5 w-3.5" />
          </ToolbarBtn>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1 pr-1">
          <button
            type="button"
            disabled={disabled}
            className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-foreground transition hover:bg-muted"
            title="Text color"
            onMouseDown={(e) => { e.preventDefault(); openColorPopover("fore", e.currentTarget); }}>
            <IconType className="h-3.5 w-3.5" />
            <IconChevron className="h-3 w-3" />
          </button>
          <button
            type="button"
            disabled={disabled}
            className="inline-flex h-7 items-center gap-1 rounded-md px-1.5 text-foreground transition hover:bg-muted"
            title="Highlight"
            onMouseDown={(e) => { e.preventDefault(); openColorPopover("back", e.currentTarget); }}>
            <IconHighlight className="h-3.5 w-3.5" />
            <IconChevron className="h-3 w-3" />
          </button>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1 pr-1">
          <ToolbarBtn title="Bullet list" disabled={disabled} active={editor?.isActive("bulletList") ?? false}
            onMouseDown={() => editor?.chain().focus().toggleBulletList().run()}>
            <IconList className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Numbered list" disabled={disabled} active={editor?.isActive("orderedList") ?? false}
            onMouseDown={() => editor?.chain().focus().toggleOrderedList().run()}>
            <IconListOrdered className="h-3.5 w-3.5" />
          </ToolbarBtn>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1 pr-1">
          <ToolbarBtn title="Align left" disabled={disabled} active={editor?.isActive({ textAlign: "left" }) ?? false}
            onMouseDown={() => editor?.chain().focus().setTextAlign("left").run()}>
            <IconAlignLeft className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Align center" disabled={disabled} active={editor?.isActive({ textAlign: "center" }) ?? false}
            onMouseDown={() => editor?.chain().focus().setTextAlign("center").run()}>
            <IconAlignCenter className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Align right" disabled={disabled} active={editor?.isActive({ textAlign: "right" }) ?? false}
            onMouseDown={() => editor?.chain().focus().setTextAlign("right").run()}>
            <IconAlignRight className="h-3.5 w-3.5" />
          </ToolbarBtn>
        </div>
        <div className="h-5 w-px bg-accent" />
        <div className="flex items-center gap-1">
          <ToolbarBtn title="Link (⌘K)" disabled={disabled} onMouseDown={(e) => openLinkPopover(e.currentTarget as HTMLElement)}>
            <IconLink className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Image" disabled={disabled} onMouseDown={(e) => openImagePopover(e.currentTarget as HTMLElement)}>
            <IconImage className="h-3.5 w-3.5" />
          </ToolbarBtn>
          <ToolbarBtn title="Insert button (CTA)" disabled={disabled} onMouseDown={(e) => openButtonPopover(e.currentTarget as HTMLElement)}>
            <IconButton className="h-3.5 w-3.5" />
          </ToolbarBtn>
        </div>
        <div className="flex-1" />
        <div className="flex items-center gap-1">
          <div className="inline-flex rounded-lg bg-muted p-1">
            <button
              disabled={disabled}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition",
                mode === "rich" && "bg-card text-foreground shadow-sm",
              )}
              onMouseDown={(e) => { e.preventDefault(); switchMode("rich"); }}>
              Visual
            </button>
            <button
              disabled={disabled}
              className={cn(
                "inline-flex items-center rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground transition",
                mode === "source" && "bg-card text-foreground shadow-sm",
              )}
              onMouseDown={(e) => { e.preventDefault(); switchMode("source"); }}>
              <IconCode className="mr-1 h-3.5 w-3.5" />
              Source
            </button>
          </div>
        </div>
      </div>

      {mode === "rich" ? (
        <EditorContent
          editor={editor}
          className={cn("email-template-editor-content", richContentClass)}
          onKeyUp={checkTrigger}
          onClick={checkTrigger}
        />
      ) : (
        <textarea
          ref={sourceRef}
          disabled={disabled}
          className="min-h-[280px] max-h-[60vh] w-full resize-none border-0 bg-muted/50 px-4 py-4 font-mono text-[12.5px] leading-6 text-foreground outline-none"
          defaultValue={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          spellCheck={false}
        />
      )}

      {slash && mode === "rich" && (
        <div
          className="absolute z-50 max-h-72 min-w-[260px] overflow-y-auto rounded-xl border border-border bg-card p-1 shadow-2xl shadow-slate-900/10"
          style={{ left: slash.x, top: slash.y }}
          onMouseDown={(e) => e.preventDefault()}
        >
          <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
            Variables {slash.query && `· "${slash.query}"`}
          </div>
          {filteredVars.length === 0 ? (
            <div className="px-2 py-2 text-sm text-muted-foreground">No matches</div>
          ) : (
            filteredVars.map((v, i) => (
              <button
                key={v.key}
                type="button"
                className={cn(
                  "flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition hover:bg-muted/50",
                  i === slashIdx && "bg-muted",
                )}
                onMouseEnter={() => setSlashIdx(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  insertVariable(v.key);
                }}
              >
                <div className="flex h-7 w-7 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <IconSparkle className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-foreground">{v.label || v.key}</div>
                  <div className={cn(
                    "font-mono text-[11px] text-muted-foreground",
                    i === slashIdx && "text-foreground",
                  )}>{`{{${v.key}}}`}</div>
                </div>
              </button>
            ))
          )}
        </div>
      )}

      {linkPopover && (
        <LinkPopover
          {...linkPopover}
          onCancel={() => setLinkPopover(null)}
          onApply={applyLink}
        />
      )}
      {btnPopover && (
        <ButtonPopover
          {...btnPopover}
          onChange={(p) => setBtnPopover((prev) => prev ? { ...prev, ...p } : null)}
          onCancel={() => setBtnPopover(null)}
          onApply={() => applyButton(btnPopover.url, btnPopover.label)}
        />
      )}
      {imgPopover && (
        <ImagePopover
          {...imgPopover}
          onChange={(p) => setImgPopover((prev) => prev ? { ...prev, ...p } : null)}
          onCancel={() => setImgPopover(null)}
          onApply={() => applyImage(imgPopover.url)}
        />
      )}
      {colorPopover && (
        <div
          className="absolute z-40 min-w-[220px] rounded-xl border border-border bg-card p-3 shadow-2xl shadow-slate-900/10"
          style={{ left: colorPopover.x, top: colorPopover.y }}
        >
          <label className="mb-1.5 block text-[11px] text-muted-foreground">
            {colorPopover.type === "fore" ? "Text color" : "Highlight"}
          </label>
          <div className="grid grid-cols-8 gap-1">
            {(colorPopover.type === "fore" ? TEXT_COLORS : HIGHLIGHT_COLORS).map((c) => (
              <button
                key={c}
                className="h-[22px] w-[22px] rounded-md border border-black/10 p-0 transition hover:scale-110"
                onClick={() => applyColor(c)}
                style={{
                  background: c === "transparent"
                    ? "linear-gradient(135deg, #fff 45%, #ddd 50%, #fff 55%)"
                    : c,
                }}
                title={c}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between rounded-b-xl border-t border-border bg-muted/50 px-4 py-2.5 text-[11.5px] text-muted-foreground">
        <div>{wordCount} words · {charCount} chars</div>
        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[11px]">
            Type{" "}
            <kbd className="rounded border border-border bg-card px-1.5 py-0.5">/</kbd>
            {" "}or{" "}
            <kbd className="rounded border border-border bg-card px-1.5 py-0.5">{"{{"}</kbd>
            {" "}for variables
          </span>
        </div>
      </div>
    </div>
  );
}
