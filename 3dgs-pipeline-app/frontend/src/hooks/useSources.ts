import { useCallback, useEffect, useState } from 'react';
import client from '@/api/client';
import type { SourceFile, SourcesResponse } from '@/types';

/**
 * What sits in the project's `input/` directory, probed.
 *
 * Distinct from the `/probe` route step 2 already read: that one returns
 * `analysis/probe.json`, the metadata of the video the *last* extraction ran
 * on, and it does not exist until there has been one. This is what is on disk
 * now — which is what the next run will read.
 */
export const useSources = (projectId: string | null) => {
  const [sources, setSources] = useState<SourceFile[]>([]);
  const [extractionSource, setExtractionSource] = useState<string | null>(null);
  const [ffmpegAvailable, setFfmpegAvailable] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!projectId) {
      setSources([]);
      setExtractionSource(null);
      return;
    }
    setLoading(true);
    try {
      const res = await client.get<SourcesResponse>(`/files/${projectId}/sources`);
      setSources(res.data.sources);
      setExtractionSource(res.data.extraction_source);
      setFfmpegAvailable(res.data.ffmpeg_available);
      setError(null);
    } catch (e) {
      setSources([]);
      setError(e instanceof Error ? e.message : 'Failed to read the source files');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  /** The one video step 2 will extract from — the panel badges it, and step 2
   *  resolves its fps policy against it before any extraction has run. */
  const primary = sources.find((s) => s.is_extraction_source) ?? null;

  return { sources, primary, extractionSource, ffmpegAvailable, loading, error, refresh };
};
