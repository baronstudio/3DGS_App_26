import { useCallback, useEffect, useRef, useState } from 'react';
import client from '@/api/client';
import type { Region, RegionState } from '@/types';

/**
 * The Reconstruction Region of one project: fetch, edit locally, PUT on demand.
 *
 * Deliberately **not** the debounced auto-save of `useProjectSettings`. A
 * threshold is a preference and lands where it lands; a region is a validation,
 * and it is written to `region.rsbox` — the file RealityScan reloads — so it
 * moves when the user says so and not while a gizmo is mid-drag.
 *
 * The wire format is the app's canonical frame throughout; the conversion onto
 * whatever frame the preview happens to be in is the viewer's (`regionBox.ts`).
 */
export function useRegion(projectId: string | null, enabled: boolean) {
  const [state, setState] = useState<RegionState | null>(null);
  const [draft, setDraft] = useState<Region | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  // The project the draft was edited against: a switch must not PUT one
  // project's box onto another's.
  const ownerRef = useRef<string | null>(null);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    if (!projectId || !enabled) {
      setState(null);
      setDraft(null);
      setDirty(false);
      return undefined;
    }
    let cancelled = false;
    setError(null);
    client.get<RegionState>(`/projects/${projectId}/region`)
      .then((res) => {
        if (cancelled) return;
        setState(res.data);
        setDraft(res.data.region);
        setDirty(false);
        ownerRef.current = projectId;
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setState(null);
        setDraft(null);
        setError(err instanceof Error ? err.message : 'Failed to read the region');
      });
    return () => { cancelled = true; };
  }, [projectId, enabled, nonce]);

  const edit = useCallback((region: Region) => {
    setDraft(region);
    setDirty(true);
  }, []);

  const save = useCallback(async () => {
    if (!projectId || !draft || ownerRef.current !== projectId) return;
    setSaving(true);
    setError(null);
    try {
      const res = await client.put<RegionState>(`/projects/${projectId}/region`, {
        centre: draft.centre,
        size: draft.size,
        euler_deg: draft.euler_deg,
        frame: draft.frame,
        source: 'manual',
      });
      setState(res.data);
      setDraft(res.data.region);
      setDirty(false);
      setSavedAt(Date.now());
    } catch (err: unknown) {
      // The draft is kept: a failed save must not throw away the placement.
      setError(err instanceof Error ? err.message : 'Failed to save the region');
    } finally {
      setSaving(false);
    }
  }, [projectId, draft]);

  /** Back to RealityScan's own region — deletes the two saved files. */
  const reset = useCallback(async () => {
    if (!projectId) return;
    setSaving(true);
    setError(null);
    try {
      const res = await client.delete<RegionState>(`/projects/${projectId}/region`);
      setState(res.data);
      setDraft(res.data.region);
      setDirty(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to reset the region');
    } finally {
      setSaving(false);
    }
  }, [projectId]);

  return { state, draft, edit, save, reset, refresh, dirty, saving, savedAt, error };
}

export default useRegion;
