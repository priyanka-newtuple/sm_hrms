import type { LucideProps } from "lucide-react"
import {
  Shield,
  Users,
  Pencil,
  Copy,
  Plus,
  RefreshCw,
  Search,
  MoreHorizontal,
  Lock,
  ChevronDown,
  ChevronLeft,
  Check,
  Building2,
  FileText,
  Settings,
  MessageSquare,
  Plug,
  Table,
  Eye,
  EyeOff,
  Asterisk,
} from "lucide-react"

type IconProps = LucideProps & {
  sw?: number
}

function withSw<T extends IconProps>(
  Icon: React.ComponentType<LucideProps>,
  defaultSw: number
) {
  return function WrappedIcon({ sw = defaultSw, strokeWidth, ...props }: T) {
    return <Icon strokeWidth={strokeWidth ?? sw} {...props} />
  }
}

export const ShieldIcon = withSw(Shield, 1.7)
export const UsersIcon = withSw(Users, 1.7)
export const PencilIcon = withSw(Pencil, 1.7)
export const CopyIcon = withSw(Copy, 1.7)
export const PlusIcon = withSw(Plus, 1.8)
export const RefreshIcon = withSw(RefreshCw, 1.8)
export const SearchIcon = withSw(Search, 1.8)
export const MoreIcon = withSw(MoreHorizontal, 1.7)
export const LockIcon = withSw(Lock, 1.7)
export const CaretIcon = withSw(ChevronDown, 2)
export const BackIcon = withSw(ChevronLeft, 1.9)
export const CheckIcon = withSw(Check, 2.4)
export const OrgIcon = withSw(Building2, 1.7)
export const ContentIcon = withSw(FileText, 1.7)
export const AutoIcon = withSw(Settings, 1.7)
export const MsgIcon = withSw(MessageSquare, 1.7)
export const PlugIcon = withSw(Plug, 1.7)
export const EmptyIcon = withSw(Table, 1.5)
export const EyeIcon = withSw(Eye, 1.7)
export const EyeOffIcon = withSw(EyeOff, 1.7)
export const MaskIcon = withSw(Asterisk, 1.7)

