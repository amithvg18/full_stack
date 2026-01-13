import React from 'react';

interface TrafficLightProps {
    state: 'RED' | 'YELLOW' | 'GREEN';
    className?: string;
}

const TrafficLight: React.FC<TrafficLightProps> = ({ state, className = '' }) => {
    return (
        <div className={`flex flex-col gap-2 p-3 bg-gray-800 rounded-lg border-2 border-gray-700 shadow-xl w-24 items-center ${className}`}>
            {/* RED Light */}
            <div
                className={`w-16 h-16 rounded-full border-4 border-gray-900 transition-all duration-300 ${state === 'RED'
                        ? 'bg-red-600 shadow-[0_0_30px_rgba(220,38,38,0.8)] scale-105'
                        : 'bg-red-950 opacity-40'
                    }`}
            />

            {/* YELLOW Light */}
            <div
                className={`w-16 h-16 rounded-full border-4 border-gray-900 transition-all duration-300 ${state === 'YELLOW'
                        ? 'bg-yellow-500 shadow-[0_0_30px_rgba(234,179,8,0.8)] scale-105'
                        : 'bg-yellow-950 opacity-40'
                    }`}
            />

            {/* GREEN Light */}
            <div
                className={`w-16 h-16 rounded-full border-4 border-gray-900 transition-all duration-300 ${state === 'GREEN'
                        ? 'bg-green-500 shadow-[0_0_30px_rgba(34,197,94,0.8)] scale-105'
                        : 'bg-green-950 opacity-40'
                    }`}
            />
        </div>
    );
};

export default TrafficLight;
