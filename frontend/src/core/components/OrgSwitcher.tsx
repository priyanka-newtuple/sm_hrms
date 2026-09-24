"use client"

import * as React from "react"
import { Check, ChevronsUpDown, Loader2, Plus } from "lucide-react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useAuth } from "../auth"
import type { UserOrganizationMembership } from "../auth/types"
import { useLogoSrc } from "../hooks/useLogoSrc"
import { isSuperAdminUser } from "../utils"
import { cn } from "@/lib/utils"
import { resolveEnumLabel } from "@/shared/utils/labels"
import AddOrgModal from "./AddOrgModal"

const ROLE_LABEL: Record<string, string> = {
  superadmin: "Super Admin",
  admin: "Admin",
  recruiter: "Recruiter",
  hiring_manager: "Hiring Manager",
  viewer: "Viewer",
  member: "Member",
}

function formatRole(role?: string | null): string {
  if (!role) return "Member"
  return ROLE_LABEL[role] ?? resolveEnumLabel(role)
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const GRADIENTS = [
  "from-violet-500 to-indigo-500",
  "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-500",
  "from-rose-500 to-pink-500",
  "from-sky-500 to-cyan-500",
]

function gradientFor(id: string): string {
  let hash = 0
  for (let i = 0; i < id.length; i++) hash = (hash * 31 + id.charCodeAt(i)) | 0
  return GRADIENTS[Math.abs(hash) % GRADIENTS.length]
}

type OrgSwitcherProps = {
  /**
   * Dropdown placement relative to the trigger. Defaults to 'right', which
   * fits a narrow sidebar rail (menu opens into the main content area).
   * Pass 'bottom' when rendering inline in a horizontal bar, where opening
   * sideways would overlap the rest of the bar's controls.
   */
  dropdownSide?: "bottom" | "right"
}

export function OrgSwitcher({ dropdownSide }: OrgSwitcherProps = {}) {
  const { isMobile } = useSidebar()
  const { organization, organizations, user, switchOrganization, refreshOrganizations } = useAuth()
  const logoSrc = useLogoSrc(organization?.logoUrl)
  const [pendingOrgId, setPendingOrgId] = React.useState<string | null>(null)
  const [showAddOrgModal, setShowAddOrgModal] = React.useState(false)

  const memberships: UserOrganizationMembership[] = React.useMemo(() => {
    if (organizations.length > 0) return organizations
    if (organization) {
      return [
        {
          id: null,
          organizationId: organization.id,
          organizationName: organization.name,
          organizationSlug: organization.slug,
          organizationDomain: null,
          organizationLogoUrl: organization.logoUrl ?? null,
          organizationStatus: "active",
          role: (user?.role ?? "member") as UserOrganizationMembership["role"],
          status: "active",
          isCurrent: true,
        },
      ]
    }
    return []
  }, [organization, organizations, user?.role])

  const sorted = React.useMemo(() => {
    return [...memberships].sort((a, b) => {
      if (a.isCurrent && !b.isCurrent) return -1
      if (!a.isCurrent && b.isCurrent) return 1
      return a.organizationName.localeCompare(b.organizationName)
    })
  }, [memberships])

  const current = sorted.find((m) => m.isCurrent) ?? sorted[0]

  const handleSwitch = async (orgId: string) => {
    if (pendingOrgId) return
    setPendingOrgId(orgId)
    try {
      await switchOrganization(orgId)
    } catch (err) {
      console.error("Failed to switch organization", err)
    } finally {
      setPendingOrgId(null)
    }
  }

  if (!current) return null

  const triggerName = current.organizationName
  const triggerRole = formatRole(current.role)

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground w-full"
                />
              }
            >
              {logoSrc ? (
                <div className="flex aspect-square size-9 items-center justify-center overflow-hidden rounded-lg bg-card shadow-sm ring-1 ring-black/5">
                  <img src={logoSrc} alt="" className="size-full object-contain" />
                </div>
              ) : (
                <div
                  className={cn(
                    "flex aspect-square size-9 items-center justify-center rounded-lg bg-gradient-to-br text-white text-sm font-semibold shadow-sm ring-1 ring-black/5",
                    gradientFor(current.organizationId)
                  )}
                >
                  {getInitials(triggerName)}
                </div>
              )}
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">{triggerName}</span>
                <span className="inline-flex items-center gap-1 text-[11px] text-sidebar-foreground/60">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  <span className="truncate">{triggerRole}</span>
                </span>
              </div>
              <ChevronsUpDown className="ml-auto size-4 opacity-60" />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className="w-(--radix-dropdown-menu-trigger-width) min-w-72 overflow-hidden rounded-xl p-1.5 shadow-xl"
              align="start"
              side={isMobile ? "bottom" : (dropdownSide ?? "right")}
              sideOffset={6}
            >
              <DropdownMenuGroup>
                <DropdownMenuLabel className="flex items-center justify-between px-2 pt-1.5 pb-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                  <span>Organizations</span>
                  <span className="text-muted-foreground/70 normal-case tracking-normal">
                    {sorted.length}
                  </span>
                </DropdownMenuLabel>
                {sorted.map((org) => {
                  const isCurrent = org.isCurrent
                  const isPending = pendingOrgId === org.organizationId
                  const isInactive = org.organizationStatus !== "active"
                  return (
                    <DropdownMenuItem
                      key={org.organizationId}
                      disabled={isPending || isInactive}
                      onClick={(e) => {
                        if (isCurrent) {
                          e.preventDefault()
                          return
                        }
                        void handleSwitch(org.organizationId)
                      }}
                      className={cn(
                        "group flex cursor-pointer items-center gap-3 rounded-lg p-2 transition-colors",
                        isCurrent
                          ? "bg-primary/10 ring-1 ring-inset ring-primary/30"
                          : "hover:bg-accent",
                        isInactive && "opacity-60"
                      )}
                    >
                      <div
                        className={cn(
                          "flex size-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-white text-xs font-semibold shadow-sm ring-1 ring-black/5",
                          gradientFor(org.organizationId)
                        )}
                      >
                        {getInitials(org.organizationName)}
                      </div>
                      <div className="flex min-w-0 flex-1 flex-col">
                        <span
                          className={cn(
                            "truncate text-sm",
                            isCurrent ? "font-semibold text-foreground" : "font-medium"
                          )}
                        >
                          {org.organizationName}
                        </span>
                        <span className="inline-flex items-center gap-1.5 truncate text-[11px] text-muted-foreground">
                          <span>{formatRole(org.role)}</span>
                          {isInactive && (
                            <span className="rounded-sm bg-muted px-1 py-px text-[9px] font-medium uppercase tracking-wider">
                              {org.organizationStatus}
                            </span>
                          )}
                        </span>
                      </div>
                      {isPending ? (
                        <Loader2 className="size-4 animate-spin text-muted-foreground" />
                      ) : isCurrent ? (
                        <span className="flex size-5 items-center justify-center rounded-full bg-primary text-primary-foreground">
                          <Check className="size-3" />
                        </span>
                      ) : (
                        <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                          Switch
                        </span>
                      )}
                    </DropdownMenuItem>
                  )
                })}
              </DropdownMenuGroup>
              {isSuperAdminUser(user) && (
                <>
                  <DropdownMenuSeparator className="my-1.5" />
                  <DropdownMenuItem
                    onClick={() => setShowAddOrgModal(true)}
                    className="flex cursor-pointer items-center gap-3 rounded-lg p-2 hover:bg-accent"
                  >
                    <div className="flex size-9 items-center justify-center rounded-lg border border-dashed border-border bg-transparent text-muted-foreground">
                      <Plus className="size-4" />
                    </div>
                    <span className="text-sm font-medium text-muted-foreground">
                      Add organization
                    </span>
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>

      {isSuperAdminUser(user) && (
        <AddOrgModal
          open={showAddOrgModal}
          onClose={() => setShowAddOrgModal(false)}
          onCreated={() => { void refreshOrganizations(); }}
        />
      )}
    </>
  )
}

export default OrgSwitcher
