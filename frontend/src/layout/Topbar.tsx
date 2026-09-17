import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Menu, ChevronDown } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '../auth/AuthContext';
import { Avatar } from '../components/ui/Avatar';
import { RoleBadge } from '../components/ui/Badge';
import { LanguageSwitcher } from '../components/ui/LanguageSwitcher';
import { Breadcrumb } from '../components/ui/Breadcrumb';
import { usePageHeader } from './PageHeaderContext';

export function Topbar({ onOpenMobileNav }: { onOpenMobileNav: () => void }) {
  const { user, logout } = useAuth();
  const { t } = useTranslation();
  const header = usePageHeader();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  if (!user) return null;

  return (
    <header className="sticky top-0 z-topbar flex h-14 shrink-0 items-center gap-4 border-b border-neutral-200 bg-white px-4 sm:px-6">
      <button
        type="button"
        onClick={onOpenMobileNav}
        className="rounded-md p-1.5 text-neutral-600 hover:bg-neutral-100 lg:hidden"
        aria-label="open navigation"
      >
        <Menu size={24} />
      </button>

      {header.breadcrumb && header.breadcrumb.length > 0 ? (
        <Breadcrumb segments={header.breadcrumb} />
      ) : (
        <h1 className="truncate text-section-title text-neutral-900">{header.title}</h1>
      )}

      <div className="ml-auto hidden items-center gap-4 md:flex">
        <LanguageSwitcher />
        <div className="hidden h-6 w-px bg-neutral-200 sm:block" />
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((o) => !o)}
            className="flex items-center gap-2 rounded-md p-1 hover:bg-neutral-100"
          >
            <Avatar name={user.username} />
            <span className="hidden text-body text-neutral-800 sm:inline">{user.username}</span>
            <RoleBadge role={user.role} />
            <ChevronDown size={14} className="text-neutral-500" />
          </button>
          {menuOpen && (
            <div className="absolute right-0 z-popover mt-1 w-48 rounded-lg border border-neutral-200 bg-white py-1 shadow-md">
              <Link
                to="/settings/profile"
                onClick={() => setMenuOpen(false)}
                className="block px-4 py-2 text-body text-neutral-800 hover:bg-neutral-50"
              >
                {t('common.profileSettings')}
              </Link>
              <button
                type="button"
                onClick={() => {
                  setMenuOpen(false);
                  logout();
                }}
                className="block w-full px-4 py-2 text-left text-body text-neutral-800 hover:bg-neutral-50"
              >
                {t('common.logout')}
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
