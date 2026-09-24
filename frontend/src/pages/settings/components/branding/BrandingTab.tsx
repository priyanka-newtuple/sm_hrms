/**
 * BrandingTab
 *
 * Lets an organization admin customize the application theme — brand color,
 * foreground color, corner radius, font, the top bar's size and color, and the
 * modal header color — with a live preview. Saved to the organization's settings
 * and applied immediately via the runtime theme applier.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { Loader2, RotateCcw, Palette, Image as ImageIcon } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '../../../../core/auth';
import { organizations, orgLogo } from '../../../../core/services/api';
import { getCurrentOrganizationId } from '../../../../core/services/api/client';
import { useLogoSrc } from '../../../../core/hooks/useLogoSrc';
import { useSkin } from '../../../../skins';
import {
  applyTheme,
  CONTENT_WIDTH_OPTIONS,
  FONT_OPTIONS,
  FONT_SIZE_OPTIONS,
  HEADER_SIZE_OPTIONS,
  NAV_LAYOUT_OPTIONS,
  SHADOW_OPTIONS,
  themeFromSettings,
  type OrgTheme,
} from '../../../../core/theme';

/** Selectable corner-radius presets (maps to the `--radius` token). */
const RADIUS_OPTIONS: Array<{ label: string; value: string }> = [
  { label: 'Square', value: '0rem' },
  { label: 'Subtle', value: '0.375rem' },
  { label: 'Default', value: '0.625rem' },
  { label: 'Rounded', value: '1rem' },
  { label: 'Pill', value: '1.5rem' },
];

function themesEqual(a: OrgTheme, b: OrgTheme): boolean {
  return (
    (a.navLayout ?? 'sidebar') === (b.navLayout ?? 'sidebar') &&
    (a.contentWidth ?? '1600px') === (b.contentWidth ?? '1600px') &&
    a.brandColor === b.brandColor &&
    a.brandForeground === b.brandForeground &&
    a.radius === b.radius &&
    a.fontId === b.fontId &&
    a.fontSize === b.fontSize &&
    a.headerHeight === b.headerHeight &&
    a.headerColor === b.headerColor &&
    a.modalColor === b.modalColor &&
    a.elementShadow === b.elementShadow &&
    a.customFontFamily === b.customFontFamily &&
    a.customFontHref === b.customFontHref
  );
}

type SetThemeField = <K extends keyof OrgTheme>(key: K, value: OrgTheme[K]) => void;

/**
 * Persist the theme to the organization, cache it (so it survives reloads), and
 * refresh the org in context so the tab reads the saved values on re-entry.
 */
async function persistTheme(theme: OrgTheme, refreshOrg: () => Promise<void>): Promise<void> {
  await organizations.updateBranding({ settings: { theme } });
  applyTheme(theme, true);
  await refreshOrg();
}

/** State, live-preview side-effects, and persistence for the theme draft. */
function useThemeDraft(): {
  draft: OrgTheme;
  set: SetThemeField;
  saving: boolean;
  isDirty: boolean;
  handleSave: () => Promise<void>;
  handleReset: () => void;
  handleCancel: () => void;
} {
  const { organization, refreshOrganization } = useAuth();
  const { skin } = useSkin();
  const orgId = organization?.id || getCurrentOrganizationId();
  // The theme currently persisted for this org (reverted to on cancel/unmount).
  // Skin's defaultTheme sits between global defaults and org overrides.
  const savedTheme = useMemo(
    () => themeFromSettings(organization?.settings, skin.defaultTheme),
    [organization?.settings, skin.defaultTheme],
  );

  const [draft, setDraft] = useState<OrgTheme>(savedTheme);
  const [saving, setSaving] = useState(false);
  const savedRef = useRef(savedTheme);

  // Reset draft/baseline when the active organization changes.
  useEffect(() => { savedRef.current = savedTheme; setDraft(savedTheme); }, [savedTheme]);
  // Live-preview the draft app-wide (uncached); revert any preview on unmount.
  useEffect(() => { applyTheme(draft, false); }, [draft]);
  useEffect(() => () => applyTheme(savedRef.current, false), []);

  const set: SetThemeField = (key, value) => setDraft((prev) => ({ ...prev, [key]: value }));

  const handleSave = async () => {
    if (!orgId) {
      toast.error('No active organization to save the theme to.');
      return;
    }
    setSaving(true);
    try {
      await persistTheme(draft, refreshOrganization);
      savedRef.current = draft;
      toast.success('Theme saved');
    } catch (e) {
      toast.error('Could not save theme', { description: e instanceof Error ? e.message : 'Failed to save theme' });
    } finally {
      setSaving(false);
    }
  };

  return {
    draft, set, saving,
    isDirty: !themesEqual(draft, savedRef.current),
    handleSave,
    handleReset: () => setDraft(themeFromSettings(null, skin.defaultTheme)),
    handleCancel: () => setDraft(savedRef.current),
  };
}

/** Run a logo mutation with busy state, org refresh, and success/error toasts. */
async function runLogoUpdate(
  action: () => Promise<unknown>,
  message: string,
  setBusy: (b: boolean) => void,
  refresh: () => Promise<void>,
): Promise<void> {
  setBusy(true);
  try {
    await action();
    await refresh();
    toast.success(message);
  } catch (e) {
    toast.error('Logo update failed', { description: e instanceof Error ? e.message : undefined });
  } finally {
    setBusy(false);
  }
}

/** Rename the organization (persisted immediately on save). */
function OrgNameSection() {
  const { organization, refreshOrganization } = useAuth();
  const [name, setName] = useState(organization?.name ?? '');
  const [saving, setSaving] = useState(false);

  // Seed draft when organization loads or changes (handles null-at-mount case).
  useEffect(() => { setName(organization?.name ?? ''); }, [organization?.name]);

  const isDirty = name.trim() !== (organization?.name ?? '');

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) { toast.error('Organization name cannot be empty'); return; }
    setSaving(true);
    try {
      await organizations.renameCurrent(trimmed);
      await refreshOrganization();
      toast.success('Organization name updated');
    } catch (err) {
      toast.error('Could not update name', { description: err instanceof Error ? err.message : undefined });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-8">
      <label htmlFor="org-name" className="block text-sm font-medium text-foreground mb-1.5">
        Organization name
      </label>
      <form onSubmit={handleSave} className="flex items-center gap-3 max-w-sm">
        <input
          id="org-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={255}
          required
          className="flex-1 h-10 rounded-lg border border-border px-3 text-sm"
          placeholder="Acme Inc."
        />
        <Button type="submit" variant="primary" size="sm" disabled={!isDirty || saving}>
          {saving && <Loader2 className="w-3 h-3 animate-spin" />}
          Save
        </Button>
      </form>
    </div>
  );
}

/** Upload / preview / remove the organization logo (persisted immediately). */
function LogoSection() {
  const { organization, refreshOrganization } = useAuth();
  const orgId = organization?.id || getCurrentOrganizationId();
  const [busy, setBusy] = useState(false);
  const logoSrc = useLogoSrc(organization?.logoUrl);

  const onFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !orgId) return;
    runLogoUpdate(async () => {
      const fileId = await orgLogo.upload(file);
      await organizations.updateBranding({ logo_url: fileId });
    }, 'Logo updated', setBusy, refreshOrganization);
  };

  return (
    <div className="mb-8">
      <label className="block text-sm font-medium text-foreground mb-1.5">Organization logo</label>
      <div className="flex items-center gap-4">
        <div className="flex size-16 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted/50">
          {logoSrc ? (
            <img src={logoSrc} alt="Organization logo" className="size-full object-contain" />
          ) : (
            <ImageIcon className="size-6 text-muted-foreground/60" />
          )}
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-muted/50">
          <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="hidden" onChange={onFile} disabled={busy} />
          Upload
        </label>
        {organization?.logoUrl && (
          <Button
            variant="ghost"
            onClick={() => runLogoUpdate(() => organizations.updateBranding({ logo_url: '' }), 'Logo removed', setBusy, refreshOrganization)}
            disabled={busy}
          >
            Remove
          </Button>
        )}
        {busy && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
      </div>
      <p className="text-xs text-muted-foreground mt-2">PNG, JPG, SVG, or WebP, up to 5MB. Shown in the sidebar.</p>
    </div>
  );
}

/** A color swatch paired with a hex text input. */
function ColorField({ label, value, onChange }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
      <div className="flex items-center gap-3">
        <input
          type="color"
          aria-label={label}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-10 w-14 rounded-lg border border-border bg-card p-1 cursor-pointer"
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="flex-1 h-10 rounded-lg border border-border px-3 text-sm font-mono"
        />
      </div>
    </div>
  );
}

/** A labelled single-line text input, optionally followed by a hint line. */
function TextField({ label, value, onChange, placeholder, hint }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full h-10 rounded-lg border border-border px-3 text-sm"
      />
      {hint && <p className="text-xs text-muted-foreground mt-1.5">{hint}</p>}
    </div>
  );
}

/** A labelled dropdown, optionally followed by a hint line. */
function SelectField({ label, value, onChange, options, hint }: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  hint?: string;
}) {
  return (
    <div>
      <label className="block text-sm font-medium text-foreground mb-1.5">{label}</label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full h-10 rounded-lg border border-border px-3 text-sm bg-card"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      {hint && <p className="text-xs text-muted-foreground mt-1.5">{hint}</p>}
    </div>
  );
}

/** The editable controls: colors, font, corner radius, shadow, and top-bar/modal styling. */
function ThemeControls({ draft, set }: { draft: OrgTheme; set: SetThemeField }) {
  return (
    <div className="space-y-5">
      <SelectField
        label="Navigation layout"
        value={draft.navLayout ?? 'sidebar'}
        onChange={(v) => set('navLayout', v as OrgTheme['navLayout'])}
        options={NAV_LAYOUT_OPTIONS}
        hint="Sidebar keeps navigation on the left; Top bar moves it into the header. Applies after saving."
      />
      <SelectField
        label="Content width"
        value={draft.contentWidth ?? '1600px'}
        onChange={(v) => set('contentWidth', v)}
        options={CONTENT_WIDTH_OPTIONS}
        hint="Maximum width of page content. Narrower content centers in the window."
      />
      <ColorField label="Brand color" value={draft.brandColor} onChange={(v) => set('brandColor', v)} />
      <ColorField label="Text on brand color" value={draft.brandForeground} onChange={(v) => set('brandForeground', v)} />
      <SelectField
        label="Font"
        value={draft.fontId}
        onChange={(v) => set('fontId', v)}
        options={FONT_OPTIONS.map((f) => ({ value: f.id, label: f.label }))}
      />
      {draft.fontId === 'custom' && (
        <>
          <TextField
            label="Custom font family"
            value={draft.customFontFamily ?? ''}
            onChange={(v) => set('customFontFamily', v)}
            placeholder="e.g. 'Nunito', sans-serif"
            hint="Paste a valid CSS font-family stack."
          />
          <TextField
            label="Custom font stylesheet URL"
            value={draft.customFontHref ?? ''}
            onChange={(v) => set('customFontHref', v)}
            placeholder="https://fonts.googleapis.com/css2?family=Nunito&display=swap"
            hint="Optional — Google Fonts or self-hosted stylesheet to load."
          />
        </>
      )}
      <SelectField
        label="Font size"
        value={draft.fontSize}
        onChange={(v) => set('fontSize', v)}
        options={FONT_SIZE_OPTIONS.map((s) => ({ value: s.value, label: `${s.label} (${s.value})` }))}
        hint="Scales all text and spacing across the app."
      />
      <SelectField
        label="Corner radius"
        value={draft.radius}
        onChange={(v) => set('radius', v)}
        options={RADIUS_OPTIONS.map((r) => ({ value: r.value, label: `${r.label} (${r.value})` }))}
      />
      <SelectField
        label="Card shadow"
        value={draft.elementShadow ?? 'none'}
        onChange={(v) => set('elementShadow', v)}
        options={SHADOW_OPTIONS.map((s) => ({ value: s.value, label: s.label }))}
        hint="Applied to cards and elevated surfaces across the app."
      />
      <ColorField label="Top bar color" value={draft.headerColor} onChange={(v) => set('headerColor', v)} />
      <SelectField
        label="Top bar size"
        value={draft.headerHeight}
        onChange={(v) => set('headerHeight', v)}
        options={HEADER_SIZE_OPTIONS.map((h) => ({ value: h.value, label: `${h.label} (${h.value})` }))}
        hint="Text on the top bar adjusts automatically to stay readable on your chosen color."
      />
      <ColorField label="Modal header color" value={draft.modalColor} onChange={(v) => set('modalColor', v)} />
      <ColorField
        label="Content background"
        value={draft.contentBackground ?? '#FFFFFF'}
        onChange={(v) => set('contentBackground', v)}
      />
    </div>
  );
}

/** Sample UI elements that reflect the draft theme. */
function ThemePreview({ draft }: { draft: OrgTheme }) {
  const onBrand = { backgroundColor: draft.brandColor, color: draft.brandForeground };
  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-4">Preview</div>
      <div className="space-y-4">
        <button
          type="button"
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-[var(--radius)]"
          style={onBrand}
        >
          <Palette className="w-4 h-4" />
          Primary button
        </button>
        <div className="rounded-[var(--radius)] border p-4" style={{ borderColor: draft.brandColor }}>
          <div className="text-sm font-semibold" style={{ color: draft.brandColor }}>Card heading</div>
          <p className="text-sm text-muted-foreground mt-1">The quick brown fox jumps over the lazy dog.</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block px-2.5 py-1 text-xs font-medium rounded-full" style={onBrand}>
            Badge
          </span>
          <span
            className="inline-block px-2.5 py-1 text-xs font-medium rounded-full"
            style={{ backgroundColor: `${draft.brandColor}1a`, color: draft.brandColor }}
          >
            Soft badge
          </span>
        </div>
      </div>
    </div>
  );
}

/** Save / Cancel / Reset footer. */
function ThemeActions({ isDirty, saving, onSave, onCancel, onReset }: {
  isDirty: boolean;
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
  onReset: () => void;
}) {
  return (
    <div className="flex items-center gap-3 mt-8 pt-5 border-t border-border">
      <Button variant="primary" onClick={onSave} disabled={!isDirty || saving}>
        {saving && <Loader2 className="w-4 h-4 animate-spin" />}
        Save theme
      </Button>
      <Button variant="ghost" onClick={onCancel} disabled={!isDirty || saving}>
        Cancel
      </Button>
      <Button variant="ghost-action" onClick={onReset} disabled={saving} className="ml-auto">
        <RotateCcw className="w-4 h-4" />
        Reset to default
      </Button>
    </div>
  );
}

export default function BrandingTab() {
  const { draft, set, saving, isDirty, handleSave, handleReset, handleCancel } = useThemeDraft();

  return (
    <div className="max-w-3xl">
      <div className="flex items-center gap-2 mb-1">
        <Palette className="w-5 h-5 text-cobalt" />
        <h2 className="text-lg font-medium text-foreground">Branding &amp; Theme</h2>
      </div>
      <p className="text-sm text-muted-foreground mb-6">
        Customize how the application looks for your organization. Changes preview
        instantly and apply for everyone once saved.
      </p>

      <OrgNameSection />
      <LogoSection />

      <div className="grid gap-6 md:grid-cols-2">
        <ThemeControls draft={draft} set={set} />
        <ThemePreview draft={draft} />
      </div>

      <ThemeActions
        isDirty={isDirty}
        saving={saving}
        onSave={handleSave}
        onCancel={handleCancel}
        onReset={handleReset}
      />
    </div>
  );
}
