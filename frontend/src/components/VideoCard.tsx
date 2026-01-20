import React from 'react';
import TrafficLight from './TrafficLight';

interface VideoCardProps {
    laneId: number;
    videoUrl: string;
    signalState: 'RED' | 'YELLOW' | 'GREEN';
    isEmergency: boolean;
    detections?: Array<{ class: string; confidence: number }>;
    onUploadSuccess?: (laneId: number) => void;
}

const VideoCard: React.FC<VideoCardProps> = ({ laneId, videoUrl, signalState, isEmergency, detections = [], onUploadSuccess }) => {
    // ... (refs and hooks)
    const fileInputRef = React.useRef<HTMLInputElement>(null);
    const [uploading, setUploading] = React.useState(false);
    const [streamKey, setStreamKey] = React.useState<number | null>(null);

    React.useEffect(() => {
        setStreamKey(Date.now());
    }, []);

    const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

    // ... (handlers)
    const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
        // ... (existing implementation)
        const file = event.target.files?.[0];
        if (!file) return;

        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch(`${apiBaseUrl}/upload/${laneId}`, {
                method: 'POST',
                body: formData,
            });
            if (response.ok) {
                console.log(`Video uploaded for Lane ${laneId}`);
                onUploadSuccess?.(laneId);
                setTimeout(() => setStreamKey(Date.now()), 1000);
            }
        } catch (error) {
            console.error('Upload failed', error);
        } finally {
            setUploading(false);
        }
    };

    // ... (other handlers)
    const handleSimulateEmergency = async () => {
        // ...
        try {
            await fetch(`${apiBaseUrl}/signal/${laneId}/simulate_emergency?active=true`, { method: 'POST' });
            setTimeout(() => {
                fetch(`${apiBaseUrl}/signal/${laneId}/simulate_emergency?active=false`, { method: 'POST' });
            }, 5000);
        } catch (error) {
            console.error('Simulation failed', error);
        }
    };

    const handleForceGreen = async () => {
        try {
            await fetch(`${apiBaseUrl}/signal/${laneId}/force`, { method: 'POST' });
        } catch (error) {
            console.error('Force green failed', error);
        }
    };

    return (
        <div className={`relative flex flex-col rounded-xl overflow-hidden border-4 transition-all duration-500 ${isEmergency
            ? 'border-red-500 shadow-[0_0_40px_rgba(239,68,68,0.6)] animate-pulse-slow'
            : 'border-slate-700 shadow-lg'
            } bg-slate-900`}>

            {/* Header */}
            <div className={`px-4 py-3 flex flex-wrap justify-between items-center gap-2 ${isEmergency ? 'bg-red-600' : 'bg-slate-800'}`}>
                <h2 className="text-xl font-bold text-white tracking-wider flex items-center gap-2">
                    LANE {laneId}
                    {isEmergency && <span className="text-xs bg-white text-red-600 px-2 py-0.5 rounded-full font-extrabold animate-bounce">EMERGENCY</span>}
                </h2>

                <div className="flex flex-wrap items-center gap-2">
                    <button
                        onClick={handleForceGreen}
                        className="text-[10px] bg-green-700 hover:bg-green-600 text-white px-2 py-1 rounded transition-colors border border-green-600 font-bold"
                    >
                        FORCE GREEN
                    </button>

                    <button
                        onClick={handleSimulateEmergency}
                        className="text-[10px] bg-red-700 hover:bg-red-600 text-white px-2 py-1 rounded transition-colors border border-red-600 font-bold"
                    >
                        SIMULATE EMER
                    </button>

                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleUpload}
                        className="hidden"
                        accept="video/mp4,video/x-m4v,video/*"
                    />
                    <button
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="text-[10px] bg-slate-700 hover:bg-slate-600 text-slate-200 px-2 py-1 rounded transition-colors border border-slate-600 flex items-center gap-1 disabled:opacity-50"
                    >
                        {uploading ? '...' : 'INSERT VIDEO'}
                    </button>

                    <button
                        onClick={async () => {
                            try {
                                await fetch(`${apiBaseUrl}/video/${laneId}`, { method: 'DELETE' });
                                setTimeout(() => setStreamKey(Date.now()), 500);
                            } catch (e) { console.error(e); }
                        }}
                        className="text-[10px] bg-slate-800 hover:bg-red-900/50 text-slate-400 hover:text-red-400 px-2 py-1 rounded transition-colors border border-slate-700 hover:border-red-800"
                        title="Clear Video"
                    >
                        ✕
                    </button>
                </div>
            </div>

            {/* Video Content */}
            <div className="relative aspect-video bg-black group">
                <img
                    src={streamKey ? `${videoUrl}?t=${streamKey}` : videoUrl}
                    alt={`Lane ${laneId} Feed`}
                    className="w-full h-full object-cover opacity-90 group-hover:opacity-100 transition-opacity"
                />

                {/* Signal Overlay */}
                <div className="absolute top-4 right-4 transform scale-75 origin-top-right">
                    <TrafficLight state={signalState} />
                </div>

                {/* Detections Panel */}
                {detections.length > 0 && (
                    <div className="absolute top-4 left-4 bg-black/80 backdrop-blur-sm border border-slate-600 rounded-lg p-2 max-w-xs">
                        <div className="text-[10px] text-slate-400 font-bold mb-1 uppercase tracking-wider">Detected Objects:</div>
                        <div className="space-y-1">
                            {detections.map((det, idx) => (
                                <div key={idx} className="flex items-center justify-between gap-2 text-xs">
                                    <span className="text-white font-mono capitalize">{det.class.replace(/_/g, ' ')}</span>
                                    <span className="text-green-400 font-bold">{(det.confidence * 100).toFixed(0)}%</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Status Text Overlay */}
                <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent p-4">
                    <div className="flex items-center gap-3">
                        <div className={`w-3 h-3 rounded-full ${signalState === 'GREEN' ? 'bg-green-500' : signalState === 'YELLOW' ? 'bg-yellow-500' : 'bg-red-600'}`} />
                        <span className="text-white font-mono text-lg">
                            SIGNAL: <span className={`${signalState === 'GREEN' ? 'text-green-400' : signalState === 'YELLOW' ? 'text-yellow-400' : 'text-red-500'} font-bold`}>{signalState}</span>
                        </span>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default VideoCard;
