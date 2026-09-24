import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { LogOut, Settings2 } from 'lucide-react';
import { useSkin } from '../../skins';
import { useAuth } from '../../core/auth';
import { Button } from '@/components/ui/button';

interface SettingsLayoutProps {
  children: ReactNode;
}

function getUserInitials(fullName?: string): string {
  if (!fullName) return 'U';
  const names = fullName.trim().split(/\s+/);
  if (names.length === 1) return names[0][0]?.toUpperCase() || 'U';
  return `${names[0][0] || ''}${names[names.length - 1][0] || ''}`.toUpperCase();
}

export default function SettingsLayout({ children }: SettingsLayoutProps) {
  const { skin } = useSkin();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gradient-to-br from-background via-background to-primary/5">
      <header className="sticky top-0 z-40 border-b border-border/80 bg-background/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <Link to="/settings" className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/20">
                <span className="text-lg font-bold">{skin.branding.logoText}</span>
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">{skin.branding.name}</p>
                <p className="text-xs text-muted-foreground">Modular configuration harness</p>
              </div>
            </Link>
            <div className="hidden items-center gap-2 rounded-full border border-primary/15 bg-primary/5 px-3 py-1.5 text-sm font-medium text-primary md:flex">
              <Settings2 className="h-4 w-4" />
              Settings only
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-foreground">{user?.fullName || 'Unknown User'}</p>
              <p className="text-xs text-muted-foreground">{user?.email || 'No email available'}</p>
            </div>
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-primary to-sky-500 text-sm font-semibold text-white shadow-md">
              {getUserInitials(user?.fullName)}
            </div>
            <Button
              variant="secondary"
              rounded="full"
              onClick={() => void logout()}
              className="border-border hover:border-ring/30"
              icon={<LogOut className="h-4 w-4" />}
            >
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
