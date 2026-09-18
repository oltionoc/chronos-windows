import { useEffect, useState } from 'react';
import { Link, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SidebarContent } from './Sidebar';
import { Topbar } from './Topbar';
import { Drawer } from '../components/ui/Drawer';
import { PageHeaderProvider } from './PageHeaderContext';
import { useAuth } from '../auth/AuthContext';
import { useFetch } from '../lib/useFetch';
import { reportsApi } from '../api/endpoints';
import { hasUnseenAlerts } from '../lib/alertsSeen';
import { Avatar } from '../components/ui/Avatar';
import { RoleBadge } from '../components/ui/Badge';
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher';
import { LicenseGate } from '../auth/LicenseGate';

// DESIGN_SPEC §4.1 (sm/<640): language switcher + user menu move from the
// topbar into the nav drawer's top section at these widths (topbar only
// keeps hamburger + title there — see Topbar.tsx's `md:flex` cutoff).
// Hidden again at md+ (>=768) since the topbar shows these itself there.
function MobileUserSection({ onNavigate }: { onNavigate: () => void }) {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  if (!user) return null;
  return (
    <div className="shrink-0 border-b border-neutral-200 p-4 md:hidden">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Avatar name={user.username} />
          <div>
            <div className="text-body font-medium text-neutral-800">{user.username}</div>
            <RoleBadge role={user.role} />
          </div>
        </div>
        <LanguageSwitcher />
      </div>
      <div className="flex flex-col gap-1">
        <Link
          to="/settings/profile"
          onClick={onNavigate}
          className="rounded-md px-2 py-1.5 text-left text-body text-neutral-700 hover:bg-neutral-50"
        >
          {t('common.profileSettings')}
        </Link>
        <button
          type="button"
          onClick={() => {
            onNavigate();
            logout();
          }}
          className="rounded-md px-2 py-1.5 text-left text-body text-neutral-700 hover:bg-neutral-50"
        >
          {t('common.logout')}
        </button>
      </div>
    </div>
  );
}

const COLLAPSE_KEY = 'checkin_sidebar_collapsed';

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === '1');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  // Fetched once here (not inside Sidebar, which mounts twice — desktop +
  // mobile drawer) so the "new alerts" dot doesn't double-fetch. A fresh
  // page load/reload is enough cadence for this — not worth polling.
  const { data: alertsData } = useFetch(() => reportsApi.alerts({ days: 14 }), []);
  const alertsUnread = alertsData ? hasUnseenAlerts(alertsData.alerts) : false;

  return (
    <PageHeaderProvider>
      <div className="flex h-screen overflow-hidden bg-app">
        {/* Desktop sidebar (>=1024px), fixed width, own scroll, does not scroll with content */}
        <aside className="hidden shrink-0 lg:block" style={{ width: collapsed ? 64 : 240 }}>
          <SidebarContent collapsed={collapsed} onToggleCollapse={() => setCollapsed((c) => !c)} alertsUnread={alertsUnread} />
        </aside>

        {/* Off-canvas nav drawer (<1024px) */}
        <Drawer open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} side="left">
          <div className="flex h-full flex-col">
            <MobileUserSection onNavigate={() => setMobileNavOpen(false)} />
            <div className="min-h-0 flex-1">
              <SidebarContent
                collapsed={false}
                onNavigate={() => setMobileNavOpen(false)}
                showCollapseToggle={false}
                alertsUnread={alertsUnread}
              />
            </div>
          </div>
        </Drawer>

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onOpenMobileNav={() => setMobileNavOpen(true)} />
          <LicenseGate>
            <main className="flex-1 overflow-y-auto p-3 sm:p-6">
              <Outlet />
            </main>
          </LicenseGate>
        </div>
      </div>
    </PageHeaderProvider>
  );
}
