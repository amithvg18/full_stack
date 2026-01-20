import { useState, useEffect, useRef } from 'react';

type SignalState = 'RED' | 'YELLOW' | 'GREEN';

interface LaneState {
  lane_id: number;
  signal_state: SignalState;
  has_emergency: boolean;
}

interface SocketData {
  signals: Record<string, 'RED' | 'YELLOW' | 'GREEN'>;
  emergency: {
    is_active: boolean;
    lane_id: number | null;
  };
  accident?: {
    is_active: boolean;
    lane_id: number | null;
  };
  detections: Record<string, Array<{ class: string; confidence: number }>>;
}

export const useSocket = (url: string) => {
  const [data, setData] = useState<SocketData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const connect = () => {
      const socket = new WebSocket(url);
      socketRef.current = socket;

      socket.onopen = () => {
        console.log('Connected to WebSocket');
        setIsConnected(true);
      };

      socket.onmessage = (event) => {
        try {
          const parsedData = JSON.parse(event.data);
          setData(parsedData);
        } catch (err) {
          console.error('Failed to parse WS message', err);
        }
      };

      socket.onclose = () => {
        console.log('WebSocket disconnected. Retrying...');
        setIsConnected(false);
        setTimeout(connect, 3000);
      };

      socket.onerror = (error) => {
        console.error('WebSocket Error', error);
      };
    };

    connect();

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
      }
    };
  }, [url]);

  return { data, isConnected };
};
