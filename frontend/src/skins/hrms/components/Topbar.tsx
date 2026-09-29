import { LogOut } from "lucide-react";

import { useAuth } from "@/skins/hrms/auth/AuthContext";

export function Topbar() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white/80 px-8 backdrop-blur">
      <div />
      {user && (
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm font-medium text-gray-900">{user.full_name}</div>
            <div className="text-xs text-gray-600">
              {user.designation} · {user.role_name}
            </div>
          </div>
          <button
            onClick={logout}
            className="flex h-9 w-9 items-center justify-center rounded-full text-gray-600 transition-colors duration-hover ease-brand hover:bg-gray-50 hover:text-cobalt"
            aria-label="Log out"
          >
            <LogOut size={16} />
          </button>
        </div>
      )}
    </header>
  );
}
