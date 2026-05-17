import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useProjects } from '@/hooks/useProjects';
import { usePipelineStore } from '@/store/pipelineStore';
import { Plus, Trash2, PlayCircle, ImageOff } from 'lucide-react';
import type { StepStatus } from '@/types';

const STEP_LABELS: Record<number, string> = {
  0: 'Not started',
  1: 'Import',
  2: 'Extract',
  3: 'RC Align',
  4: 'LFS Train',
  5: 'Export',
  6: 'Blender',
};

const TOTAL_STEPS = 6;

function relativeDate(isoString: string): string {
  const diff = Date.now() - new Date(isoString).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
  const months = Math.floor(days / 30);
  return `${months} month${months > 1 ? 's' : ''} ago`;
}

interface ProjectListProps {
  /** Called after a project is selected/created, to navigate to the wizard */
  onNavigate?: () => void;
}

export const ProjectList: React.FC<ProjectListProps> = ({ onNavigate }) => {
  const { projects, setCurrentProject, setCurrentStep, hydrateFromProject } = usePipelineStore();
  const { createProject, deleteProject, selectProject } = useProjects();

  const handleNew = () => {
    const name = prompt('Project name:');
    if (!name?.trim()) return;
    setCurrentProject(null);
    setCurrentStep(1);
    createProject(name.trim()).then(() => onNavigate?.());
  };

  const handleResume = (id: string, step: number) => {
    const project = projects.find((p) => p.id === id);
    selectProject(id);
    if (project) {
      hydrateFromProject(project);
    } else {
      setCurrentStep(Math.max(step, 1));
    }
    onNavigate?.();
  };

  const handleDelete = (id: string, name: string) => {
    if (!window.confirm(`Delete project "${name}"? This cannot be undone.`)) return;
    deleteProject(id);
  };

  return (
    <Card className="bg-slate-800 border-slate-700">
      <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
        <CardTitle className="text-base font-semibold text-slate-100">Projects</CardTitle>
        <Button size="sm" variant="outline" className="gap-1 h-7 text-xs" onClick={handleNew}>
          <Plus className="w-3 h-3" />
          New Project
        </Button>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {projects.length === 0 ? (
          <p className="text-sm text-slate-500 text-center py-6">
            No projects yet. Start by importing a video.
          </p>
        ) : (
          <ul className="space-y-2">
            {projects.map((p) => {
              return (
                <li
                  key={p.id}
                  className="flex items-center gap-3 rounded-md bg-slate-900/60 px-3 py-2 border border-slate-700"
                >
                  {/* Thumbnail */}
                  <div className="w-12 h-12 shrink-0 rounded overflow-hidden bg-slate-800 border border-slate-700 flex items-center justify-center">
                    {p.thumbnail_url ? (
                      <img
                        src={`http://localhost:8000${p.thumbnail_url}`}
                        alt="thumbnail"
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <ImageOff className="w-5 h-5 text-slate-600" />
                    )}
                  </div>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-100 truncate">{p.name}</p>
                    <p className="text-xs text-slate-500">{relativeDate(p.created_at)}</p>
                    {/* Step progress */}
                    <div className="flex items-center gap-1.5 mt-1">
                      <div className="flex gap-0.5">
                        {Array.from({ length: TOTAL_STEPS }, (_, i) => {
                          const stepNum = i + 1;
                          const s = (p.step_status as Record<string, StepStatus>)?.[String(stepNum)];
                          return (
                            <div
                              key={stepNum}
                              className={`h-1.5 w-4 rounded-full ${
                                s === 'done' ? 'bg-green-500' :
                                s === 'running' ? 'bg-cyan-400 animate-pulse' :
                                s === 'error' ? 'bg-red-500' :
                                stepNum <= p.current_step ? 'bg-slate-400' : 'bg-slate-700'
                              }`}
                            />
                          );
                        })}
                      </div>
                      <span className="text-xs text-slate-500">
                        {p.current_step > 0 ? `${p.current_step}/${TOTAL_STEPS}` : '–'}
                      </span>
                    </div>
                  </div>

                  <Badge variant="outline" className="text-xs text-slate-400 border-slate-600 shrink-0">
                    {STEP_LABELS[p.current_step] ?? `Step ${p.current_step}`}
                  </Badge>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-xs text-blue-400 hover:text-blue-300"
                    onClick={() => handleResume(p.id, p.current_step)}
                  >
                    <PlayCircle className="w-3 h-3 mr-1" />
                    Resume
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 px-2 text-red-500 hover:text-red-400"
                    onClick={() => handleDelete(p.id, p.name)}
                  >
                    <Trash2 className="w-3 h-3" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
};
