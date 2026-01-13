'use client';

import React from 'react';
import VideoCard from '@/components/VideoCard';
import { useSocket } from '@/hooks/useSocket';

export default function Home() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const wsUrl = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000/ws/emergency';

  const { data, isConnected } = useSocket(wsUrl);

  // Default lane configuration
  const lanes = [1, 2, 3, 4];
  const videoBaseUrl = `${apiBaseUrl}/video`;

  return (
    <main className="min-h-screen bg-slate-950 text-white p-8 font-sans selection:bg-red-500/30">

      {/* Header / Navbar */}
      <header className="mb-8 flex flex-col md:flex-row justify-between items-center bg-slate-900/50 p-6 rounded-2xl border border-slate-800 backdrop-blur-md sticky top-4 z-50 shadow-2xl">
        <div className="flex items-center gap-4">
          <div className="bg-red-600 p-2 rounded-lg shadow-[0_0_15px_rgba(220,38,38,0.5)]">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-white"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" /><polyline points="14 2 14 8 20 8" /><path d="M8 13h8" /><path d="M8 17h8" /><path d="M8 9h8" /></svg>
          </div>
          <div>
            <h1 className="text-3xl font-extrabold tracking-tighter bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">
              SMART TRAFFIC <span className="text-red-500">SENTINEL</span>
            </h1>
            <p className="text-slate-400 text-sm font-medium tracking-wide">Emergency Vehicle Detection & Pre-emption System</p>
          </div>
        </div>

        <div className="flex items-center gap-6 mt-4 md:mt-0">
          <div className="flex flex-col items-end">
            <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold mb-1">System Status</div>
            <div className={`flex items-center gap-2 px-3 py-1 rounded-full text-sm font-bold border ${isConnected ? 'bg-green-500/10 border-green-500/50 text-green-400' : 'bg-red-500/10 border-red-500/50 text-red-400'}`}>
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'}`} />
              {isConnected ? 'ONLINE' : 'OFFLINE'}
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative">
        {lanes.map((laneId) => {
          const laneKey = `lane${laneId}`;
          const signalState = data?.signals[laneKey] || 'RED';
          const isEmergency = data?.emergency.is_active && data.emergency.lane_id === laneId;
          const detections = data?.detections?.[laneKey] || [];

          return (
            <VideoCard
              key={laneId}
              laneId={laneId}
              videoUrl={`${videoBaseUrl}/${laneId}`}
              signalState={signalState}
              isEmergency={!!isEmergency}
              detections={detections}
            />
          );
        })}
      </div>

      {/* Global Alert Overlay */}
      {data?.emergency.is_active && (
        <div className="fixed bottom-8 left-1/2 transform -translate-x-1/2 z-50 w-full max-w-2xl px-4">
          <div className="bg-red-600/90 backdrop-blur-md text-white px-8 py-4 rounded-2xl shadow-[0_0_50px_rgba(220,38,38,0.5)] border-2 border-red-400 flex items-center justify-between animate-slide-up">
            <div className="flex items-center gap-4">
              <div className="bg-white text-red-600 p-2 rounded-full animate-bounce">
                <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" /><line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" /></svg>
              </div>
              <div>
                <h3 className="text-2xl font-bold uppercase tracking-widest">Pre-emption Active</h3>
                <p className="font-mono text-red-100">Emergency Detected in Lane <span className="font-bold text-white text-lg">{data.emergency.lane_id}</span>. Priority Given.</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <footer className="mt-12 text-center text-slate-600 text-sm font-light">
        &copy; 2026 AI-Powered Traffic Management. Powered by YOLOv8, FastAPI & Next.js.
      </footer>
    </main>
  );
}
