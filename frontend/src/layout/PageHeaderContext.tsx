import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import type { BreadcrumbSegment } from '../components/ui/Breadcrumb';

interface PageHeaderState {
  title: string;
  breadcrumb?: BreadcrumbSegment[];
}

interface PageHeaderContextValue {
  header: PageHeaderState;
  setHeader: (state: PageHeaderState) => void;
}

const PageHeaderContext = createContext<PageHeaderContextValue | undefined>(undefined);

export function PageHeaderProvider({ children }: { children: ReactNode }) {
  const [header, setHeader] = useState<PageHeaderState>({ title: '' });
  return <PageHeaderContext.Provider value={{ header, setHeader }}>{children}</PageHeaderContext.Provider>;
}

// Called by each page (in a useEffect) to set the topbar's title/breadcrumb
// (DESIGN_SPEC §2.1: topbar shows "current page title ... or breadcrumb when nested").
export function usePageTitle(title: string, breadcrumb?: BreadcrumbSegment[]) {
  const ctx = useContext(PageHeaderContext);
  if (!ctx) throw new Error('usePageTitle must be used within PageHeaderProvider');
  const { setHeader } = ctx;
  useEffect(() => {
    setHeader({ title, breadcrumb });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title, JSON.stringify(breadcrumb)]);
}

export function usePageHeader(): PageHeaderState {
  const ctx = useContext(PageHeaderContext);
  if (!ctx) throw new Error('usePageHeader must be used within PageHeaderProvider');
  return ctx.header;
}
