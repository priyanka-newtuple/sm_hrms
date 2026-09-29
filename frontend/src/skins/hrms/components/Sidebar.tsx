import {
  Briefcase,
  Building2,
  ClipboardCheck,
  Clock,
  LayoutGrid,
  Laptop,
  LifeBuoy,
  TrendingUp,
  Settings2,
  UserPlus,
  Users,
} from "lucide-react";
import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { onboardingApi } from "@/skins/hrms/api/onboarding";
import { workApi } from "@/skins/hrms/api/work";
import { useAuth } from "@/skins/hrms/auth/AuthContext";

import { usePermission } from "@/skins/hrms/auth/usePermission";
import { FEATURES } from "@/skins/hrms/lib/features";

const NAV_ITEMS = [
  { to: "/employees", label: "Employees", icon: Users, feature: FEATURES.EMPLOYEE_DIRECTORY },
  { to: "/onboarding", label: "Onboarding", icon: UserPlus, feature: FEATURES.EMPLOYEE_ONBOARDING },
  { to: "/customers", label: "Customers", icon: Building2, feature: FEATURES.CUSTOMERS },
  { to: "/projects", label: "Projects", icon: Briefcase, feature: FEATURES.PROJECTS },
  { to: "/allocations", label: "Allocations", icon: LayoutGrid, feature: FEATURES.ALLOCATIONS },
  { to: "/timesheets", label: "Timesheets", icon: Clock, feature: FEATURES.TIMESHEETS },
  { to: "/performance", label: "Performance", icon: TrendingUp, feature: FEATURES.PERFORMANCE_MANAGEMENT },
  { to: "/hr-cockpit", label: "HR Cockpit", icon: Settings2, feature: FEATURES.HR_COCKPIT },
  { to: "/assets", label: "Assets", icon: Laptop, feature: FEATURES.ASSET_MANAGEMENT },
  { to: "/helpdesk", label: "Help Desk", icon: LifeBuoy, feature: FEATURES.HELP_DESK },
];

export function Sidebar() {
  const { user } = useAuth();
  const { data: counts } = useQuery({
    queryKey: ["work", user?.employee_id, "summary"], queryFn: workApi.summary,
    refetchInterval: 30000, refetchOnWindowFocus: true,
  });
  const { data: onboarding } = useQuery({
    queryKey: ["onboarding", user?.employee_id, "self-nav"], queryFn: onboardingApi.myOnboarding,
  });
  return (
    <aside className="flex h-screen w-60 flex-col border-r border-gray-200 bg-white">
      <div className="flex items-center gap-2 px-6 py-6">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-cobalt text-sm font-semibold text-white">
          N
        </div>
        <span className="text-sm font-semibold tracking-tight text-gray-900">Newtuple HRMS</span>
      </div>
      <nav className="flex-1 space-y-1 px-3">
        <SidebarLink to="/my-work" label="My Work" icon={ClipboardCheck} count={counts?.total} />
        {onboarding && onboarding.status !== "completed" && <SidebarLink to="/welcome" label="My Onboarding" icon={UserPlus} />}
        {NAV_ITEMS.map((item) => (
          <SidebarLink key={item.to} {...item} />
        ))}
      </nav>
    </aside>
  );
}

function SidebarLink({
  to,
  label,
  icon: Icon,
  feature,
  count,
}: {
  to: string;
  label: string;
  icon: typeof Users;
  feature?: string;
  count?: number;
}) {
  const canView = usePermission(feature ?? "", feature === FEATURES.EMPLOYEE_ONBOARDING ? "manage" : "view");
  if (feature && !canView) return null;

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-full px-4 py-2.5 text-sm font-medium transition-colors duration-hover ease-brand ${
          isActive ? "bg-cobalt text-white" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
        }`
      }
    >
      <Icon size={16} strokeWidth={1.5} />
      {label}
      {!!count && <span className="ml-auto rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-900" aria-label={`${count} pending items`}>{count}</span>}
    </NavLink>
  );
}
