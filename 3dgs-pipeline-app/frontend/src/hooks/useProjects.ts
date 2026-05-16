import { useEffect, useState } from 'react';
import apiClient from '@/api/client';

export interface Project {
    id: string;
    name: string;
    created_at: string;
}

export const useProjects = () => {
    const [projects, setProjects] = useState<Project[]>([]);

    useEffect(() => {
        apiClient.get('/projects/').then(response => {
            setProjects(response.data);
        });
    }, []);

    const createProject = async (name: string) => {
        const response = await apiClient.post('/projects/', { name });
        setProjects([...projects, response.data]);
    };

    return { projects, createProject };
};
