import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export const LogViewer: React.FC = () => {
    return (
        <Card className="bg-gray-800 border-gray-700 h-64">
            <CardHeader>
                <CardTitle>Logs</CardTitle>
            </CardHeader>
            <CardContent className="h-full">
                <div className="bg-black h-full p-2 rounded font-mono text-sm overflow-y-auto">
                    <p>&gt; Starting pipeline...</p>
                    <p className="text-green-400">✔ Frames extracted successfully.</p>
                    <p>&gt; Computing matches...</p>
                </div>
            </CardContent>
        </Card>
    );
};
