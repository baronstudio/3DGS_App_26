import React from 'react';
import { Header } from '@/components/layout/Header';
import { ProjectList } from '@/components/projects/ProjectList';
import { PipelineView } from '@/components/pipeline/PipelineView';
import { Controls } from '@/components/pipeline/Controls';
import { LogViewer } from '@/components/pipeline/LogViewer';

export const MainPage: React.FC = () => {
    return (
        <div className="min-h-screen bg-gray-900 text-white flex flex-col">
            <Header />
            <div className="flex flex-1 p-4 gap-4">
                <div className="w-1/4 flex flex-col gap-4">
                    <ProjectList />
                    <Controls />
                </div>
                <div className="w-3/4 flex flex-col gap-4">
                    <PipelineView />
                    <LogViewer />
                </div>
            </div>
        </div>
    );
};
