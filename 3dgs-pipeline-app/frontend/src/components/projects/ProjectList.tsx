import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { useProjects } from '@/hooks/useProjects';

export const ProjectList: React.FC = () => {
    const { projects, createProject } = useProjects();

    const handleNewProject = () => {
        const name = prompt("Enter project name:");
        if (name) {
            createProject(name);
        }
    };

    return (
        <Card className="bg-gray-800 border-gray-700">
            <CardHeader>
                <CardTitle>Projects</CardTitle>
            </CardHeader>
            <CardContent>
                <ul className="space-y-2">
                    {projects.map(p => (
                        <li key={p.id} className="flex justify-between items-center">
                            <span>{p.name}</span>
                            <Button variant="outline" size="sm">Select</Button>
                        </li>
                    ))}
                </ul>
                <Button className="w-full mt-4" onClick={handleNewProject}>New Project</Button>
            </CardContent>
        </Card>
    );
};
