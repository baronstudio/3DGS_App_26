import { useEffect } from 'react';
import apiClient from '@/api/client';
import { usePipelineStore } from '../store/pipelineStore';
import type { Project } from '../types';

export const useProjects = () => {
  const { setProjects, addProject, removeProject, setCurrentProject } =
    usePipelineStore();

  const fetchProjects = async () => {
    const response = await apiClient.get<Project[]>('/projects/');
    setProjects(response.data);
  };

  const createProject = async (name: string, settings?: object) => {
    const response = await apiClient.post<Project>('/projects/create', {
      name,
      ...(settings ? { settings } : {}),
    });
    addProject(response.data);
    return response.data;
  };

  const deleteProject = async (id: string) => {
    await apiClient.delete(`/projects/${id}`);
    removeProject(id);
  };

  const selectProject = (id: string) => {
    setCurrentProject(id);
  };

  useEffect(() => {
    fetchProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { fetchProjects, createProject, deleteProject, selectProject };
};

export default useProjects;
