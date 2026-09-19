import { NavLink } from 'react-router-dom';
import { BookOpen, ChevronLeft, ChevronRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import { useAuth } from '../auth/AuthContext';
import { Logo, LogoLockup } from '../components/ui/Logo';
import { SolisLabsLogo } from '../components/ui/SolisLabsLogo';
import { navForRole } from './navConfig';
import { useShowWeeklySchedule } from '../lib/uiPrefs';
import type { NavLeaf } from './navConfig';

function NavLinkItem({
  item,
  collapsed,
  onNavigate,
  showDot,
}: {
  item: NavLeaf;
  collapsed: boolean;
  onNavigate?: () => void;
  showDot?: boolean;
}) {
  const { t } = useTranslation();
  const Icon = item.icon;
  return (
    <NavLink
      to={item.to}
      end
      onClick={onNavigate}
      title={collapsed ? t(item.labelKey) : undefined}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-2.5 rounded-md px-3 py-1.5 text-nav-item transition-colors',
          collapsed && 'justify-center px-2',
          isActive ? 'bg-primary-600 text-white' : 'text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100'
        )
      }
    >
      <span className="relative shrink-0">
        <Icon size={18} />
        {showDot && (
          <span className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-danger-500" aria-label="unread" />
        )}
      </span>
      {!collapsed && <span className="truncate">{t(item.labelKey)}</span>}
    </NavLink>
  );
}

interface SidebarContentProps {
  collapsed: boolean;
  onToggleCollapse?: () => void;
  onNavigate?: () => void;
  showCollapseToggle?: boolean;
  alertsUnread?: boolean;
}

export function SidebarContent({
  collapsed,
  onToggleCollapse,
  onNavigate,
  showCollapseToggle = true,
  alertsUnread = false,
}: SidebarContentProps) {
  const { user } = useAuth();
  const { t } = useTranslation();
  const showWeekly = useShowWeeklySchedule();
  if (!user) return null;
  // Orari Javor (weekly schedule) is hidden from the sidebar unless enabled in
  // Settings — this client plans per-day in Orari Ditor. The route still works
  // and the weekly fallback still applies server-side; only the link hides.
  const nav = navForRole(user)
    .filter((node) => showWeekly || node.type !== 'link' || node.labelKey !== 'nav.shiftSchedules');

  return (
    <div className="flex h-full flex-col bg-sidebar">
      <div className={clsx('flex h-14 shrink-0 items-center border-b border-neutral-800', collapsed ? 'justify-center px-2' : 'px-4')}>
        {collapsed ? (
          <Logo size={22} className="shrink-0 text-white" />
        ) : (
          <LogoLockup variant="light" width={130} />
        )}
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto px-2 py-1.5">
        {nav.map((node, i) => {
          if (node.type === 'separator') return <div key={i} className="my-1 border-t border-neutral-800" />;
          if (node.type === 'group') {
            return (
              <div key={i} className="mt-2 first:mt-0">
                {!collapsed && (
                  <div className="px-3 pb-0 pt-0.5 text-group-label text-neutral-500">{t(node.labelKey)}</div>
                )}
                <div className="space-y-0.5">
                  {node.items.map((item) => (
                    <NavLinkItem
                      key={item.to}
                      item={item}
                      collapsed={collapsed}
                      onNavigate={onNavigate}
                      showDot={item.to === '/alerts' && alertsUnread}
                    />
                  ))}
                </div>
              </div>
            );
          }
          return (
            <NavLinkItem
              key={node.to}
              item={node}
              collapsed={collapsed}
              onNavigate={onNavigate}
              showDot={node.to === '/alerts' && alertsUnread}
            />
          );
        })}
      </nav>
      {/* Bottom block: the manual sits here rather than at the end of the
          nav list, so the scrolling nav keeps its full height and the link
          reads as a footer item, not another page in the menu. The manual is
          a static page served by this same container, so it opens with no
          internet connection — the deployments are on-premise and some sites
          have none. */}
      <div className="shrink-0 border-t border-neutral-800 pt-1">
        <a
          href="/manuali.html"
          target="_blank"
          rel="noreferrer"
          title={t('nav.manual')}
          className={clsx(
            'mx-1.5 flex items-center gap-3 rounded-md px-3 py-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100',
            collapsed && 'justify-center px-0'
          )}
        >
          <BookOpen size={18} className="shrink-0" />
          {!collapsed && <span className="truncate text-body">{t('nav.manual')}</span>}
        </a>
        {/* Stacked rather than inline: beside the label the lockup was capped
            by the 240px sidebar (worse in Albanian, where "Fuqizuar nga" is
            wider). On its own line it gets the full content width. */}
        {!collapsed && (
          <div className="flex flex-col items-center gap-0.5 px-3 pb-1.5 pt-0.5">
            {/* Deliberately not translated: this is the Solis Labs attribution, part of the mark. */}
          <span className="text-[10px] uppercase tracking-wide text-neutral-600">Powered by</span>
            <SolisLabsLogo width={148} variant="light" />
          </div>
        )}
      </div>
      {showCollapseToggle && onToggleCollapse && (
        <div className="shrink-0 border-t border-neutral-800 p-1.5">
          <button
            type="button"
            onClick={onToggleCollapse}
            className="flex w-full items-center justify-center gap-2 rounded-md px-3 py-1.5 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
          >
            {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>
      )}
    </div>
  );
}
