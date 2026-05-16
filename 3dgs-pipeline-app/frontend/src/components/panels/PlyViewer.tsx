import React, { useEffect, useState } from 'react';
import { usePipelineStore } from '../../store/pipelineStore';
import { useSettings } from '../../hooks/useSettings';

interface PlyViewerProps {
  projectId: string;
  plyUrl?: string;
}

export const PlyViewer: React.FC<PlyViewerProps> = ({ projectId, plyUrl: plyUrlProp }) => {
  const exportFiles = usePipelineStore((s) => s.exportFiles);
  const { settings } = useSettings();

  // Resolve plyUrl: prefer prop, then auto-detect from exportFiles
  const [resolvedUrl, setResolvedUrl] = useState<string | undefined>(plyUrlProp);

  useEffect(() => {
    if (plyUrlProp) {
      setResolvedUrl(plyUrlProp);
      return;
    }
    const ply = exportFiles.find((f) => f.filename.endsWith('.ply'));
    if (ply) setResolvedUrl(ply.url);
  }, [plyUrlProp, exportFiles]);

  const supersplatBase = settings?.tools?.supersplat_url ?? 'http://localhost:4000';
  const iframeUrl = resolvedUrl
    ? `${supersplatBase}?load=${encodeURIComponent(resolvedUrl)}`
    : undefined;

  const handleCopyPath = () => {
    if (resolvedUrl) {
      navigator.clipboard.writeText(resolvedUrl).catch(() => {});
    }
  };

  if (!resolvedUrl) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-slate-500">
        <svg
          className="w-8 h-8 animate-spin text-slate-700"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
        <span className="text-sm italic">PLY file not ready yet…</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2 justify-end">
        <a
          href={resolvedUrl}
          download
          className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded transition-colors"
        >
          ⬇ Download PLY
        </a>
        <button
          onClick={handleCopyPath}
          className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-1.5 rounded transition-colors"
        >
          Copy path
        </button>
        <button
          onClick={() => window.open(iframeUrl, '_blank', 'noopener,noreferrer')}
          className="text-xs bg-cyan-700 hover:bg-cyan-600 text-white px-3 py-1.5 rounded transition-colors"
        >
          Open in SuperSplat ↗
        </button>
      </div>

      {/* Viewer iframe */}
      <iframe
        src={iframeUrl}
        title="PLY SuperSplat Viewer"
        sandbox="allow-scripts allow-same-origin"
        className="w-full rounded border border-slate-700"
        style={{ height: 400 }}
      />
    </div>
  );
};

export default PlyViewer;

