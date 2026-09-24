import type React from "react"

import { type VisibilityMode } from "@/lib/entity-data"
import { EyeIcon, EyeOffIcon, MaskIcon } from "../shared/icons"

// Icon component keyed by the `icon` token on each VISIBILITY_MODES entry.
export const VISIBILITY_ICONS: Record<string, React.ComponentType<{ width?: number; height?: number }>> = {
  "eye-off": EyeOffIcon,
  eye:       EyeIcon,
  mask:      MaskIcon,
}

// The visibility modes the UI offers, in display order.
export const VISIBILITY_ORDER: VisibilityMode[] = ["none", "full", "masked"]
