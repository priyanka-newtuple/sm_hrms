/**
 * Icon Mapping Utility
 *
 * Maps string icon names from the database to Lucide React components.
 * Used for entity-type-driven navigation and UI elements.
 */

import {
  User,
  Users,
  Briefcase,
  FileText,
  LayoutGrid,
  Settings,
  BarChart3,
  Calendar,
  Mail,
  Phone,
  MapPin,
  Building,
  Tag,
  Star,
  Heart,
  Flag,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Info,
  HelpCircle,
  Search,
  Filter,
  Plus,
  Minus,
  Edit,
  Trash,
  Download,
  Upload,
  Share,
  Link,
  ExternalLink,
  Copy,
  Clipboard,
  Archive,
  Folder,
  File,
  Image,
  Video,
  Music,
  Code,
  Terminal,
  Database,
  Server,
  Cloud,
  Wifi,
  Lock,
  Unlock,
  Key,
  Shield,
  Eye,
  EyeOff,
  Bell,
  BellOff,
  MessageSquare,
  MessageCircle,
  Send,
  Inbox,
  AtSign,
  Hash,
  Percent,
  DollarSign,
  CreditCard,
  ShoppingCart,
  Package,
  Truck,
  Home,
  Map,
  Navigation,
  Compass,
  Globe,
  Zap,
  Activity,
  TrendingUp,
  TrendingDown,
  PieChart,
  LineChart,
  BarChart,
  Target,
  Award,
  Gift,
  Bookmark,
  Paperclip,
  Layers,
  Grid,
  List,
  Menu,
  MoreHorizontal,
  MoreVertical,
  ChevronUp,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  RotateCw,
  Repeat,
  Shuffle,
  Play,
  Pause,
  Square,
  Circle,
  Triangle,
  Hexagon,
  Octagon,
  Box,
  type LucideIcon,
} from 'lucide-react';

/**
 * Map of icon names to Lucide components.
 * Icon names should match what's stored in EntityTypeDefinition.icon
 */
const iconMap: Record<string, LucideIcon> = {
  // People
  user: User,
  users: Users,

  // Business
  briefcase: Briefcase,
  building: Building,

  // Documents
  'file-text': FileText,
  file: File,
  folder: Folder,
  clipboard: Clipboard,
  paperclip: Paperclip,

  // Layout
  'layout-grid': LayoutGrid,
  grid: Grid,
  list: List,
  layers: Layers,
  menu: Menu,

  // Actions
  settings: Settings,
  search: Search,
  filter: Filter,
  plus: Plus,
  minus: Minus,
  edit: Edit,
  trash: Trash,
  download: Download,
  upload: Upload,
  share: Share,
  link: Link,
  'external-link': ExternalLink,
  copy: Copy,
  archive: Archive,

  // Status
  'check-circle': CheckCircle,
  'x-circle': XCircle,
  'alert-circle': AlertCircle,
  info: Info,
  'help-circle': HelpCircle,

  // Communication
  mail: Mail,
  phone: Phone,
  'message-square': MessageSquare,
  'message-circle': MessageCircle,
  send: Send,
  inbox: Inbox,
  bell: Bell,
  'bell-off': BellOff,

  // Time
  calendar: Calendar,
  clock: Clock,

  // Location
  'map-pin': MapPin,
  map: Map,
  navigation: Navigation,
  compass: Compass,
  globe: Globe,
  home: Home,

  // Tags & Labels
  tag: Tag,
  hash: Hash,
  'at-sign': AtSign,
  bookmark: Bookmark,

  // Rating & Favorites
  star: Star,
  heart: Heart,
  flag: Flag,
  award: Award,
  gift: Gift,
  target: Target,

  // Security
  lock: Lock,
  unlock: Unlock,
  key: Key,
  shield: Shield,
  eye: Eye,
  'eye-off': EyeOff,

  // Analytics
  'bar-chart-3': BarChart3,
  'bar-chart': BarChart,
  'pie-chart': PieChart,
  'line-chart': LineChart,
  activity: Activity,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,

  // Money
  'dollar-sign': DollarSign,
  percent: Percent,
  'credit-card': CreditCard,
  'shopping-cart': ShoppingCart,

  // Shipping
  package: Package,
  truck: Truck,
  box: Box,

  // Media
  image: Image,
  video: Video,
  music: Music,
  play: Play,
  pause: Pause,

  // Tech
  code: Code,
  terminal: Terminal,
  database: Database,
  server: Server,
  cloud: Cloud,
  wifi: Wifi,
  zap: Zap,

  // Navigation arrows
  'chevron-up': ChevronUp,
  'chevron-down': ChevronDown,
  'chevron-left': ChevronLeft,
  'chevron-right': ChevronRight,
  'arrow-up': ArrowUp,
  'arrow-down': ArrowDown,
  'arrow-left': ArrowLeft,
  'arrow-right': ArrowRight,

  // Actions
  'refresh-cw': RefreshCw,
  'rotate-cw': RotateCw,
  repeat: Repeat,
  shuffle: Shuffle,

  // More
  'more-horizontal': MoreHorizontal,
  'more-vertical': MoreVertical,

  // Shapes
  square: Square,
  circle: Circle,
  triangle: Triangle,
  hexagon: Hexagon,
  octagon: Octagon,
};

/**
 * Get a Lucide icon component by name.
 * Returns a default icon if the name is not found.
 *
 * @param iconName - The icon name (e.g., "user", "briefcase", "file-text")
 * @param fallback - Fallback icon if not found (default: Box)
 * @returns Lucide icon component
 */
export function getIcon(iconName: string | null | undefined, fallback: LucideIcon = Box): LucideIcon {
  if (!iconName) return fallback;
  return iconMap[iconName.toLowerCase()] || fallback;
}

/**
 * Check if an icon name exists in the map.
 *
 * @param iconName - The icon name to check
 * @returns true if the icon exists
 */
export function hasIcon(iconName: string): boolean {
  return iconName.toLowerCase() in iconMap;
}

/**
 * Get all available icon names.
 *
 * @returns Array of available icon names
 */
export function getAvailableIcons(): string[] {
  return Object.keys(iconMap);
}

export default iconMap;
