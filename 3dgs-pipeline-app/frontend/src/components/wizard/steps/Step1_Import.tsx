import React, { useCallback, useEffect, useRef, useState } from 'react';
import { UploadCloud, X, FolderOpen, Trash2, Film, FileText, Loader2, CheckCircle, ImageOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePipelineStore } from '@/store/pipelineStore';
import { useProjects } from '@/hooks/useProjects';
import apiClient from '@/api/client';
import type { StepStatus } from '@/types';

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function toSlug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

const ACCEPTED_EXTS = ['.mp4', '.mov', '.srt'];

interface InputFile {
  filename: string;
  size_bytes: number;
}

// ---------------------------------------------------------------------------
// Sub-component: manage sources for an existing project
// ---------------------------------------------------------------------------
const ManageSources: React.FC = () => {
  const { currentProjectId, projects, stepStatuses, setCurrentStep, confirmStep } = usePipelineStore();
  const currentProject = projects.find((p) => p.id === currentProjectId);

  const [files, setFiles] = useState<InputFile[]>([]);
  const [loadingFiles, setLoadingFiles] = useState(true);
  const [isDragging, setIsDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const fetchFiles = useCallback(async () => {
    if (!currentProjectId) return;
    try {
      const res = await apiClient.get<{ files: InputFile[] }>(
        `/projects/${currentProjectId}/input-files`
      );
      setFiles(res.data.files);
    } finally {
      setLoadingFiles(false);
    }
  }, [currentProjectId]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const validateFile = (file: File): boolean => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    return ACCEPTED_EXTS.includes(ext);
  };

  const uploadFile = async (file: File) => {
    if (!currentProjectId) return;
    if (!validateFile(file)) {
      setError(`"${file.name}" is not accepted. Use .mp4, .mov, or .srt.`);
      return;
    }
    setError(null);
    setUploading(file.name);
    setUploadProgress(0);
    try {
      const form = new FormData();
      form.append('file', file);
      await apiClient.post(`/projects/${currentProjectId}/upload-input`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      await fetchFiles();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed';
      setError(msg);
    } finally {
      setUploading(null);
      setUploadProgress(0);
    }
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) uploadFile(file);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [currentProjectId]
  );

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) uploadFile(file);
    e.target.value = '';
  };

  const handleDelete = async (filename: string) => {
    if (!currentProjectId) return;
    if (!window.confirm(`Delete "${filename}" from this project?`)) return;
    try {
      await apiClient.delete(`/projects/${currentProjectId}/input-files/${encodeURIComponent(filename)}`);
      setFiles((prev) => prev.filter((f) => f.filename !== filename));
    } catch {
      setError(`Failed to delete "${filename}"`);
    }
  };

  const hasVideo = files.some((f) => /\.(mp4|mov)$/i.test(f.filename));

  const handleValidate = async () => {
    confirmStep(1);
    setCurrentStep(2);
    if (currentProjectId) {
      const statusForApi: Record<string, string> = {};
      Object.entries(stepStatuses).forEach(([k, v]) => { statusForApi[k] = v; });
      statusForApi['1'] = 'done';
      try {
        await apiClient.put(`/projects/${currentProjectId}`, {
          step_status: statusForApi,
          current_step: 2,
        });
      } catch {
        // non-blocking — navigation already happened
      }
    }
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <div>
        <h2 className="text-xl font-semibold text-slate-100">Step 1 — Source Videos</h2>
        {currentProject && (
          <p className="text-xs text-slate-400 mt-1">
            <FolderOpen className="inline w-3 h-3 mr-1" />
            {currentProject.name} — projects/{toSlug(currentProject.name)}/input/
          </p>
        )}
      </div>

      {/* Current files list */}
      <div className="flex flex-col gap-2">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
          Current source files
        </p>
        {loadingFiles ? (
          <div className="flex items-center gap-2 text-slate-500 text-sm py-4">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : files.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-600 bg-slate-800/30 px-4 py-6 text-center text-sm text-slate-500">
            No source files yet — drop or browse a video below
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {files.map((f) => {
              const isVideo = /\.(mp4|mov)$/i.test(f.filename);
              return (
                <li
                  key={f.filename}
                  className="flex items-center gap-3 rounded-md bg-slate-800 border border-slate-700 px-3 py-2"
                >
                  {isVideo
                    ? <Film className="w-4 h-4 text-cyan-400 shrink-0" />
                    : <FileText className="w-4 h-4 text-slate-400 shrink-0" />}
                  <span className="flex-1 text-sm text-slate-200 truncate">{f.filename}</span>
                  <span className="text-xs text-slate-500 shrink-0">{formatBytes(f.size_bytes)}</span>
                  <button
                    onClick={() => handleDelete(f.filename)}
                    className="text-slate-500 hover:text-red-400 transition-colors ml-1 shrink-0"
                    title="Remove file"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Upload zone */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-8 cursor-pointer transition-colors
          ${isDragging
            ? 'border-cyan-400 bg-cyan-950/30'
            : uploading
              ? 'border-slate-600 bg-slate-800/30 cursor-not-allowed'
              : 'border-slate-600 bg-slate-800/30 hover:border-slate-500'
          }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.mov,.srt"
          className="hidden"
          onChange={handleFileInput}
        />
        {uploading ? (
          <>
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin" />
            <p className="text-sm text-slate-300 truncate max-w-xs">{uploading}</p>
            <div className="w-full max-w-xs bg-slate-700 rounded-full h-1.5">
              <div
                className="bg-cyan-500 h-1.5 rounded-full transition-all"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <p className="text-xs text-slate-500">{uploadProgress}%</p>
          </>
        ) : (
          <>
            <UploadCloud className="w-7 h-7 text-slate-500" />
            <p className="text-sm text-slate-400">
              Drop a <span className="text-slate-300">.mp4</span> /{' '}
              <span className="text-slate-300">.mov</span> to add or replace, or click to browse
            </p>
            <p className="text-xs text-slate-500">Also supports .srt subtitle files</p>
          </>
        )}
      </div>

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleValidate}
        disabled={!hasVideo}
        className="bg-green-700 hover:bg-green-600 text-white gap-2"
      >
        <CheckCircle className="w-4 h-4" />
        Validate &amp; Continue to Extract Frames
      </Button>
      {!hasVideo && (
        <p className="text-xs text-slate-500 text-center -mt-4">
          Upload at least one .mp4 or .mov video to continue
        </p>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Sub-component: create a new project
// ---------------------------------------------------------------------------
const CreateProject: React.FC = () => {
  const { projects, setCurrentProject, setCurrentStep, hydrateFromProject } = usePipelineStore();
  const { createProject } = useProjects();

  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [projectName, setProjectName] = useState('');
  const [nameError, setNameError] = useState('');
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const slug = toSlug(projectName);

  const validateFile = (file: File): boolean => {
    const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
    return ACCEPTED_EXTS.includes(ext);
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback(() => setIsDragging(false), []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && validateFile(file)) setDroppedFile(file);
  }, []);

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && validateFile(file)) setDroppedFile(file);
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setProjectName(e.target.value);
    setNameError(e.target.value.trim().length < 3 ? 'Name must be at least 3 characters' : '');
  };

  const handleStart = async () => {
    if (projectName.trim().length < 3) {
      setNameError('Name must be at least 3 characters');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const project = await createProject(projectName.trim());
      // Upload video file if one was dropped
      if (droppedFile) {
        const form = new FormData();
        form.append('file', droppedFile);
        await apiClient.post(`/projects/${project.id}/upload-input`, form, {
          headers: { 'Content-Type': 'multipart/form-data' },
          onUploadProgress: (e) => {
            if (e.total) setUploadProgress(Math.round((e.loaded / e.total) * 100));
          },
        });
      }
      setCurrentProject(project.id);
      setCurrentStep(2);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create project';
      setError(msg);
    } finally {
      setLoading(false);
      setUploadProgress(0);
    }
  };

  const handleResumeProject = (id: string) => {
    const project = projects.find((p) => p.id === id);
    setCurrentProject(id);
    if (project) {
      hydrateFromProject(project);
    } else {
      setCurrentStep(2);
    }
  };

  const uploadLabel = droppedFile && loading
    ? uploadProgress > 0
      ? `Uploading… ${uploadProgress}%`
      : 'Creating project…'
    : loading
      ? 'Creating project…'
      : 'Start Import';

  return (
    <div className="flex flex-col gap-6 p-6 max-w-2xl mx-auto">
      <h2 className="text-xl font-semibold text-slate-100">Step 1 — Import Video</h2>

      {/* Drop Zone */}
      <div
        ref={dropRef}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !droppedFile && fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed p-10 cursor-pointer transition-colors
          ${isDragging
            ? 'border-cyan-400 bg-cyan-950/30'
            : droppedFile
              ? 'border-green-500 bg-green-950/20'
              : 'border-slate-600 bg-slate-800/50 hover:border-slate-500'
          }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".mp4,.mov,.srt"
          className="hidden"
          onChange={handleFileInput}
        />
        {droppedFile ? (
          <>
            <UploadCloud className="w-8 h-8 text-green-400" />
            <div className="text-center">
              <p className="text-sm font-medium text-slate-100">{droppedFile.name}</p>
              <p className="text-xs text-slate-400">{formatBytes(droppedFile.size)}</p>
            </div>
            {loading && uploadProgress > 0 && (
              <div className="w-full max-w-xs bg-slate-700 rounded-full h-1.5">
                <div
                  className="bg-cyan-500 h-1.5 rounded-full transition-all"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            )}
            {!loading && (
              <button
                className="absolute top-2 right-2 text-slate-400 hover:text-slate-100"
                onClick={(e) => { e.stopPropagation(); setDroppedFile(null); }}
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </>
        ) : (
          <>
            <UploadCloud className="w-8 h-8 text-slate-500" />
            <p className="text-sm text-slate-400">
              Drag &amp; drop <span className="text-slate-300">.mp4</span> or{' '}
              <span className="text-slate-300">.mov</span> here, or click to browse
            </p>
            <p className="text-xs text-slate-500">Optional: also drop a .srt subtitle file</p>
          </>
        )}
      </div>

      {/* Project name */}
      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-slate-300">Project name</label>
        <input
          type="text"
          value={projectName}
          onChange={handleNameChange}
          placeholder="e.g. My Video 2025"
          className="rounded-md bg-slate-800 border border-slate-600 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
        />
        {nameError && <p className="text-xs text-red-400">{nameError}</p>}
        {slug && !nameError && (
          <p className="text-xs text-slate-500">
            <FolderOpen className="inline w-3 h-3 mr-1" />
            folder: <span className="text-slate-400">projects/{slug}/</span>
          </p>
        )}
      </div>

      {error && (
        <p className="text-sm text-red-400 bg-red-950/30 border border-red-800 rounded px-3 py-2">
          {error}
        </p>
      )}

      <Button
        onClick={handleStart}
        disabled={loading || projectName.trim().length < 3}
        className="bg-cyan-600 hover:bg-cyan-500 text-white"
      >
        {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
        {uploadLabel}
      </Button>

      {/* Existing projects */}
      {projects.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">
            Resume existing project
          </p>
          <div className="flex flex-col gap-2">
            {projects.map((p) => {
              const TOTAL_STEPS = 6;
              const stepStatus = p.step_status as Record<string, StepStatus> | undefined;
              return (
                <button
                  key={p.id}
                  onClick={() => handleResumeProject(p.id)}
                  className="flex items-center gap-3 rounded-md bg-slate-700/60 hover:bg-slate-700 border border-slate-600 px-3 py-2 text-left transition-colors"
                >
                  {/* Thumbnail */}
                  <div className="w-12 h-12 shrink-0 rounded overflow-hidden bg-slate-800 border border-slate-600 flex items-center justify-center">
                    {p.thumbnail_url ? (
                      <img
                        src={`http://localhost:8000${p.thumbnail_url}`}
                        alt="thumb"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <ImageOff className="w-5 h-5 text-slate-600" />
                    )}
                  </div>
                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-100 truncate">{p.name}</p>
                    <div className="flex items-center gap-1.5 mt-1">
                      <div className="flex gap-0.5">
                        {Array.from({ length: TOTAL_STEPS }, (_, i) => {
                          const s = stepStatus?.[String(i + 1)];
                          return (
                            <div
                              key={i}
                              className={`h-1.5 w-4 rounded-full ${
                                s === 'done' ? 'bg-green-500' :
                                s === 'running' ? 'bg-cyan-400 animate-pulse' :
                                s === 'error' ? 'bg-red-500' :
                                'bg-slate-600'
                              }`}
                            />
                          );
                        })}
                      </div>
                      <span className="text-xs text-slate-400">
                        {p.current_step > 0 ? `Step ${p.current_step}/${TOTAL_STEPS}` : 'Not started'}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Root component: switches between Create and Manage modes
// ---------------------------------------------------------------------------
const Step1_Import: React.FC = () => {
  const { currentProjectId } = usePipelineStore();
  return currentProjectId ? <ManageSources /> : <CreateProject />;
};

export default Step1_Import;

