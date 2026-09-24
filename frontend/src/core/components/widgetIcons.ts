/**
 * Widget icon registry
 *
 * A curated, name-keyed map of Lucide icons offered for button widgets. Names
 * are persisted in the widget definition (`icon`), so both the builder's
 * IconPicker and the rendered widget resolve through this single source.
 */

import {
  ArrowRight,
  Bell,
  Briefcase,
  Calendar,
  ChartBar,
  CheckCircle,
  ClipboardList,
  Download,
  ExternalLink,
  FileText,
  Filter,
  Folder,
  Home,
  Inbox,
  LayoutGrid,
  Link,
  Mail,
  Plus,
  Search,
  Settings,
  Star,
  Upload,
  User,
  Users,
  Zap,
  type LucideIcon,
} from 'lucide-react';

export const WIDGET_ICONS: Record<string, LucideIcon> = {
  'arrow-right': ArrowRight,
  bell: Bell,
  briefcase: Briefcase,
  calendar: Calendar,
  'chart-bar': ChartBar,
  'check-circle': CheckCircle,
  'clipboard-list': ClipboardList,
  download: Download,
  'external-link': ExternalLink,
  'file-text': FileText,
  filter: Filter,
  folder: Folder,
  home: Home,
  inbox: Inbox,
  'layout-grid': LayoutGrid,
  link: Link,
  mail: Mail,
  plus: Plus,
  search: Search,
  settings: Settings,
  star: Star,
  upload: Upload,
  user: User,
  users: Users,
  zap: Zap,
};

export const WIDGET_ICON_NAMES = Object.keys(WIDGET_ICONS);

/** Resolve a stored icon name to its component, or null when unset/unknown. */
export function getWidgetIcon(name: string | undefined | null): LucideIcon | null {
  if (!name) return null;
  return WIDGET_ICONS[name] ?? null;
}
