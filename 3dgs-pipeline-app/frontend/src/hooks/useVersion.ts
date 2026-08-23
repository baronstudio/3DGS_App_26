import { useState, useEffect } from 'react';

// Matches the payload of backend/api/routes/version.py
export interface AppVersion {
  name: string;
  /** Commit date as YYYY.MM.DD, or null when the app is not run from a clone. */
  version: string | null;
  commit: string | null;
  commit_short: string | null;
  commit_date: string | null;
  branch: string | null;
  commit_url: string | null;
}

/**
 * App identity, read once per page load.
 *
 * The version cannot change while the server is up (it comes from the commit
 * the backend is running), so there is nothing to poll and nothing to refetch.
 */
export const useVersion = () => {
  const [version, setVersion] = useState<AppVersion | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch('/api/version/')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled && data) setVersion(data);
      })
      .catch((error) => console.error('Failed to fetch version:', error));
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
};
