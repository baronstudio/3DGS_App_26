import React, { useEffect, useState } from 'react';
import { Download, Copy, ExternalLink, RefreshCw, FileBox } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useSettings } from '@/hooks/useSettings';
import { PlyViewer } from '@/components/panels/PlyViewer';
import type { ExportFile } from '@/types';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(filename: string): string {
  const ext = filename.slice(filename.lastIndexOf('.')).toLowerCase();
  if (ext === '.ply') return '✦';
  if (ext === '.csv') return '⊞';
  if (ext === '.rscmd') return '⚙';
  return '📄';
}

const Step5_Export: React.FC = () => {
  const { currentProjectId, exportFiles, stepStatuses } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { settings } = useSettings();
  const [copied, setCopied] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const status = stepStatuses[4];
  const isRunning = status === 'running';
  const isDone = status === 'done';
  const prevStatus = stepStatuses[3]; // LFS status

  const supersplatBase = settings?.tools?.supersplat_url ?? 'http://localhost:4000';

  const plyFile = exportFiles.find((f: ExportFile) => f.filename.endsWith('.ply'));

  // Auto-run export when LFS step completes
  useEffect(() => {
    if (prevStatus === 'done' && status === 'pending' && currentProjectId) {
      startPipeline(currentProjectId, 5, {}).catch(() => {});
    }
  }, [prevStatus, status, currentProjectId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleReRun = async () => {
    if (!currentProjectId) return;
    setError(null);
    try {
      await startPipeline(currentProjectId, 5, {});
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to run export';
      setError(msg);
    }
  };

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const handleOpenSuperSplat = (plyUrl: string) => {
    window.open(`${supersplatBase}?load=${encodeURIComponent(plyUrl)}`, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-100">Step 5 — Export &amp; Launch</h2>
        <Button
          variant="outline"
          size="sm"
          onClick={handleReRun}
          disabled={isRunning || !currentProjectId}
          className="border-slate-600 text-slate-300 hover:text-slate-100 gap-1"
        >
          <RefreshCw className="w-4 h-4" />
          Re-run Export Scan
        </Button>
      </div>

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      {/* Export files list */}
      {exportFiles.length > 0 ? (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">Export files</p>
          {exportFiles.map((file: ExportFile) => {
            const isPly = file.filename.endsWith('.ply');
            return (
              <div
                key={file.filename}
                className="flex items-center gap-3 rounded-lg bg-slate-800 border border-slate-700 px-4 py-3"
              >
                <span className="text-lg">{fileIcon(file.filename)}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-sm text-slate-100 truncate">{file.filename}</p>
                  {file.size_bytes > 0 && (
                    <p className="text-xs text-slate-500">{formatBytes(file.size_bytes)}</p>
                  )}
                </div>
                <div className="flex gap-1 shrink-0">
                  {isPly && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleOpenSuperSplat(file.url)}
                      className="text-cyan-400 hover:text-cyan-300 gap-1 text-xs"
                    >
                      <ExternalLink className="w-3 h-3" />
                      SuperSplat
                    </Button>
                  )}
                  <a href={file.url} download={file.filename}>
                    <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-100">
                      <Download className="w-4 h-4" />
                    </Button>
                  </a>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleCopy(file.url, file.filename)}
                    className="text-slate-400 hover:text-slate-100"
                  >
                    <Copy className="w-4 h-4" />
                    {copied === file.filename && (
                      <span className="text-xs text-green-400 ml-1">Copied!</span>
                    )}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="flex flex-col items-center gap-3 py-10 text-slate-500">
          {isRunning ? (
            <>
              <svg className="w-8 h-8 animate-spin text-slate-600" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              <span className="text-sm italic">Waiting for export output…</span>
            </>
          ) : (
            <>
              <FileBox className="w-8 h-8" />
              <span className="text-sm">No export files yet</span>
            </>
          )}
        </div>
      )}

      {/* PLY viewer */}
      {currentProjectId && (plyFile || isDone) && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 overflow-hidden">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide px-4 pt-3 pb-2">
            PLY Viewer (SuperSplat)
          </p>
          <PlyViewer projectId={currentProjectId} />
        </div>
      )}
    </div>
  );
};

export default Step5_Export;
