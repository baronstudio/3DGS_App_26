import React, { useEffect, useState } from 'react';
import { Download, AlertTriangle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { usePipeline } from '@/hooks/usePipeline';
import { useSettings } from '@/hooks/useSettings';
import { ProgressBar } from '@/components/panels/ProgressBar';
import client from '@/api/client';

const BLEND_FILENAME = 'scene.blend';
const README_FILENAME = 'README_SPLATFORGE.txt';

const Step6_Blender: React.FC = () => {
  const { currentProjectId, stepStatuses, exportFiles } = usePipelineStore();
  const { startPipeline } = usePipeline();
  const { settings } = useSettings();
  const [readmeContent, setReadmeContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const status = stepStatuses[5];
  const isRunning = status === 'running';
  const isDone = status === 'done';

  const blenderPath = settings?.tools?.blender_exe_path ?? null;

  const blendFile = exportFiles.find((f) => f.filename === BLEND_FILENAME);
  const readmeFile = exportFiles.find((f) => f.filename === README_FILENAME);

  // Fetch README content on completion
  useEffect(() => {
    if (!isDone || !readmeFile) return;
    client
      .get<string>(readmeFile.url, { responseType: 'text' })
      .then((res) => setReadmeContent(res.data))
      .catch(() => setReadmeContent(null));
  }, [isDone, readmeFile]);

  const handleGenerate = async () => {
    if (!currentProjectId) return;
    setError(null);
    try {
      await startPipeline(currentProjectId, 6, {});
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start Blender scene generation';
      setError(msg);
    }
  };

  if (!blenderPath) {
    return (
      <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
        <h2 className="text-xl font-semibold text-slate-100">Step 6 — Blender Scene (Optional)</h2>
        <div className="flex flex-col items-center gap-3 rounded-lg bg-slate-800/50 border border-slate-700 px-6 py-10 text-center text-slate-500">
          <AlertTriangle className="w-8 h-8 text-slate-600" />
          <p className="text-sm">Blender not detected. Configure path in Settings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 6 — Blender Scene (Optional)</h2>

      {blenderPath && (
        <div className="text-xs text-slate-500 truncate">
          Blender: <span className="text-slate-400">{blenderPath}</span>
        </div>
      )}

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleGenerate}
        disabled={isRunning || !currentProjectId}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {isRunning ? 'Generating…' : 'Generate Blender Scene'}
      </Button>

      {(isRunning || isDone) && (
        <ProgressBar step="blender" label="Blender Scene" />
      )}

      {isDone && blendFile && (
        <div className="flex items-center gap-3 rounded-lg bg-slate-800 border border-slate-700 px-4 py-3">
          <span className="text-lg">🟠</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm text-slate-100">{blendFile.filename}</p>
          </div>
          <a href={blendFile.url} download={blendFile.filename}>
            <Button variant="ghost" size="sm" className="text-slate-400 hover:text-slate-100 gap-1">
              <Download className="w-4 h-4" />
              Download
            </Button>
          </a>
        </div>
      )}

      {isDone && readmeContent && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            SplatForge Instructions
          </p>
          <pre className="rounded-lg bg-slate-950 border border-slate-700 p-4 text-xs text-slate-300 overflow-auto max-h-64 whitespace-pre-wrap">
            {readmeContent}
          </pre>
        </div>
      )}

      {isDone && !readmeContent && (
        <div className="rounded-lg bg-slate-800 border border-slate-700 p-4 text-sm text-slate-300">
          <p className="font-medium text-slate-100 mb-2">Usage Instructions</p>
          <ol className="list-decimal list-inside space-y-1 text-slate-400">
            <li>Open <span className="text-slate-200">scene.blend</span> in Blender</li>
            <li>Install the <span className="text-slate-200">SplatForge</span> addon</li>
            <li>The splat object is pre-tagged and ready to render</li>
          </ol>
        </div>
      )}
    </div>
  );
};

export default Step6_Blender;
