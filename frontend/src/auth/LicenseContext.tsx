import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { licenseApi } from '../api/endpoints';
import type { LicenseStatus } from '../api/types';
import { setLicenseExpiredHandler } from '../api/licenseSignal';

interface LicenseContextValue {
  status: LicenseStatus | null;
  /** True once the API answers 402 (expired) on any request, or status says so. */
  expired: boolean;
  refresh: () => Promise<void>;
  /** Called by the API client when any request comes back 402. */
  markExpired: () => void;
}

const LicenseContext = createContext<LicenseContextValue | undefined>(undefined);

export function LicenseProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<LicenseStatus | null>(null);
  const [expired, setExpired] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const s = await licenseApi.status();
      setStatus(s);
      setExpired(s.expired);
    } catch {
      // /license/status stays reachable even when expired, so a failure here
      // is a transient network/auth issue, not an expiry signal.
    }
  }, []);

  const markExpired = useCallback(() => {
    setExpired(true);
    refresh();
  }, [refresh]);

  useEffect(() => {
    setLicenseExpiredHandler(markExpired);
    refresh();
    // Re-check hourly: an install left running across the expiry date should
    // lock without a page reload, and a pasted key should clear within the hour
    // even on another open tab.
    const t = setInterval(refresh, 60 * 60 * 1000);
    return () => {
      setLicenseExpiredHandler(null);
      clearInterval(t);
    };
  }, [refresh, markExpired]);

  return (
    <LicenseContext.Provider value={{ status, expired, refresh, markExpired }}>
      {children}
    </LicenseContext.Provider>
  );
}

export function useLicense(): LicenseContextValue {
  const ctx = useContext(LicenseContext);
  if (!ctx) throw new Error('useLicense must be used within LicenseProvider');
  return ctx;
}
