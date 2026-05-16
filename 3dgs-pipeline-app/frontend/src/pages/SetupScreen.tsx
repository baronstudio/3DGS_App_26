import React from 'react';
import { useSettings } from '@/hooks/useSettings';
import { Button } from '@/components/ui/button';

const StubStatus: React.FC = () => {
    const { settings } = useSettings();

    if (!settings) {
        return <div>Loading stub status...</div>;
    }

    const toolStubStatus = [
        { name: 'FFmpeg', stub: settings.stubs.ffmpeg_stub, found: !!settings.tools.ffmpeg_path },
        { name: 'RealityCapture', stub: settings.stubs.rc_stub, found: !!settings.tools.rc_exe_path },
        { name: 'LichtFeld Studio', stub: settings.stubs.lfs_stub, found: !!settings.tools.lfs_exe_path },
        { name: 'Blender', stub: settings.stubs.blender_stub, found: !!settings.tools.blender_exe_path },
    ];

    return (
        <div className="border border-gray-700 rounded-lg p-4 mt-6 bg-gray-800/30 w-full max-w-md mx-auto">
            <h2 className="text-lg font-semibold text-center mb-4 text-white">
                🔧 Development Mode
            </h2>
            <div className="font-mono text-sm space-y-2">
                {toolStubStatus.map(tool => (
                    <div key={tool.name} className="flex justify-between items-center">
                        <span className="text-gray-300">{tool.name.padEnd(18, ' ')}</span>
                        {tool.stub ? (
                            <span className="text-orange-400">[STUB]   ⚠️ simulated</span>
                        ) : (
                            tool.found ? (
                                <span className="text-green-400">[real]   ✅ found</span>
                            ) : (
                                <span className="text-red-400">[real]   ❌ not found</span>
                            )
                        )}
                    </div>
                ))}
            </div>
            <p className="text-xs text-gray-500 mt-4 text-center">
                Stub mode: pipeline runs end-to-end without GPU or compiled tools. Disable stubs in Settings when real tools are ready.
            </p>
        </div>
    );
};


export const SetupScreen: React.FC<{ onProceed?: () => void }> = ({ onProceed }) => {
    const { settings } = useSettings();
    const canProceed = settings != null && (
        Object.values(settings.stubs).some(stub => stub === true) ||
        (!!settings.tools.rc_exe_path && !!settings.tools.lfs_exe_path)
    );

    return (
        <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center justify-center p-4">
            <h1 className="text-4xl font-bold mb-8">3DGS Pipeline Setup</h1>
            <StubStatus />
            <Button className="mt-8" disabled={!canProceed} onClick={onProceed}>
                Proceed to Pipeline
            </Button>
        </div>
    );
};
