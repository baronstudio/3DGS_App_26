import React, { useCallback, useEffect, useRef, useState } from 'react';
import client from '../../api/client';
import { usePipelineStore } from '../../store/pipelineStore';

interface FrameInfo {
  filename: string;
  url: string;
  potentially_blurry?: boolean;
}

interface FrameGalleryProps {
  projectId: string;
  onDelete?: (filenames: string[]) => void;
}

interface FrameApiResponse {
  frames: FrameInfo[];
  total: number;
  blurry_count: number;
}

const VRAM_MB_PER_FRAME = 5;

export const FrameGallery: React.FC<FrameGalleryProps> = ({ projectId, onDelete }) => {
  const stepStatuses = usePipelineStore((s) => s.stepStatuses);
  const extractionRunning = stepStatuses[1] === 'running';

  const [frames, setFrames] = useState<FrameInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchFrames = useCallback(async () => {
    try {
      const res = await client.get<FrameApiResponse>(`/files/${projectId}/frames`);
      setFrames(res.data.frames ?? []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Initial fetch + polling while extraction runs
  useEffect(() => {
    fetchFrames();
  }, [fetchFrames]);

  useEffect(() => {
    if (extractionRunning) {
      intervalRef.current = setInterval(fetchFrames, 2000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [extractionRunning, fetchFrames]);

  const toggleSelect = (filename: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(filename)) next.delete(filename);
      else next.add(filename);
      return next;
    });
  };

  const handleBulkDelete = async () => {
    const toDelete = Array.from(selected);
    try {
      await client.delete(`/files/${projectId}/frames`, { data: { filenames: toDelete } });
      setFrames((prev) => prev.filter((f) => !toDelete.includes(f.filename)));
      setSelected(new Set());
      onDelete?.(toDelete);
    } catch {
      // ignore
    }
  };

  const vramEstimate = Math.round((frames.length * VRAM_MB_PER_FRAME) / 1024 * 10) / 10;
  const vramLabel = vramEstimate >= 1
    ? `~${vramEstimate}GB VRAM for RC`
    : `~${frames.length * VRAM_MB_PER_FRAME}MB VRAM for RC`;

  return (
    <div className="flex flex-col gap-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-300">
            {frames.length} frame{frames.length !== 1 ? 's' : ''} extracted
          </span>
          {frames.length > 0 && (
            <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded">
              {vramLabel}
            </span>
          )}
        </div>
        {selected.size > 0 && (
          <button
            onClick={handleBulkDelete}
            className="text-xs bg-red-600 hover:bg-red-700 text-white px-3 py-1 rounded transition-colors"
          >
            Delete {selected.size} selected
          </button>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="grid grid-cols-5 gap-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="aspect-video bg-slate-800 rounded animate-pulse" />
          ))}
        </div>
      ) : frames.length === 0 ? (
        <div className="text-slate-600 italic text-sm">No frames yet.</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
          {frames.map((frame) => {
            const isSelected = selected.has(frame.filename);
            return (
              <div
                key={frame.filename}
                className={`relative group cursor-pointer rounded overflow-hidden border-2 transition-colors ${
                  isSelected ? 'border-cyan-500' : 'border-transparent hover:border-slate-600'
                }`}
                onClick={() => toggleSelect(frame.filename)}
              >
                <img
                  src={frame.url}
                  alt={frame.filename}
                  className="w-full aspect-video object-cover bg-slate-900"
                  loading="lazy"
                />
                {frame.potentially_blurry && (
                  <div className="absolute top-1 left-1 bg-orange-500/90 text-white text-xs px-1 rounded">
                    ⚠ blurry
                  </div>
                )}
                <div className="absolute top-1 right-1">
                  <div
                    className={`w-4 h-4 rounded border-2 transition-colors ${
                      isSelected
                        ? 'bg-cyan-500 border-cyan-500'
                        : 'bg-slate-900/70 border-slate-500 opacity-0 group-hover:opacity-100'
                    }`}
                  />
                </div>
                <div className="text-xs text-slate-500 truncate px-1 py-0.5 bg-slate-950">
                  {frame.filename}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default FrameGallery;

