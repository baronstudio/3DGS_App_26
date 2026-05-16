import client from '../api/client';

export const usePipeline = () => {
  const startPipeline = async (projectId: string, step: string) => {
    return client.post('/pipeline/start', { project_id: projectId, step });
  };

  const controlPipeline = async (action: 'pause' | 'resume' | 'abort') => {
    return client.post('/pipeline/control', { action });
  };

  return { startPipeline, controlPipeline };
};
