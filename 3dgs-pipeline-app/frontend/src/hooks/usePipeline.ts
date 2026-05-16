import client from '../api/client';
import { usePipelineStore } from '../store/pipelineStore';

export const usePipeline = () => {
  const { setPipelineRunning } = usePipelineStore();

  const startPipeline = async (
    projectId: string,
    fromStep: number,
    settings: object
  ) => {
    const response = await client.post('/pipeline/start', {
      project_id: projectId,
      from_step: fromStep,
      settings,
    });
    setPipelineRunning(true);
    return response.data;
  };

  const controlPipeline = async (
    projectId: string,
    action: 'pause' | 'resume' | 'abort'
  ) => {
    const response = await client.post('/pipeline/control', {
      project_id: projectId,
      action,
    });
    if (action === 'abort') setPipelineRunning(false);
    return response.data;
  };

  const fetchStatus = async (projectId: string) => {
    const response = await client.get('/pipeline/status', {
      params: { project_id: projectId },
    });
    return response.data;
  };

  return { startPipeline, controlPipeline, fetchStatus };
};

export default usePipeline;
