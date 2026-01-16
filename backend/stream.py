import cv2
import threading
import time
from typing import Dict, Tuple, Optional
import numpy as np

class VideoStream:
    def __init__(self, source: str, lane_id: int):
        self.source = source
        self.lane_id = lane_id
        self.cap = None
        self.current_frame: Optional[np.ndarray] = None
        self.running = False
        self.lock = threading.Lock()
        # Don't initialize capture here - wait until start() is called
        
    def _initialize_capture(self):
        """Initialize video capture with error handling"""
        try:
            self.cap = cv2.VideoCapture(self.source)
            if not self.cap.isOpened():
                print(f"Lane {self.lane_id}: Failed to open video source: {self.source}")
                # Create blank frame as fallback
                self.current_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        except Exception as e:
            print(f"Lane {self.lane_id}: Error initializing capture: {e}")
            self.cap = None
            self.current_frame = np.zeros((360, 640, 3), dtype=np.uint8)
        
    def start(self):
        if self.running:
            return
        # Initialize capture before starting the thread
        if self.cap is None:
            self._initialize_capture()
        self.running = True
        threading.Thread(target=self._update, daemon=True).start()
    
    def stop(self):
        self.running = False
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def _update(self):
        while self.running:
            if not self.cap or not self.cap.isOpened():
                # Try to reconnect or loop video if it's a file
                try:
                    self.cap = cv2.VideoCapture(self.source)
                    if not self.cap.isOpened():
                        print(f"Lane {self.lane_id}: Cannot open source {self.source}, using blank frame")
                        # Use blank frame
                        with self.lock:
                            self.current_frame = np.zeros((360, 640, 3), dtype=np.uint8)
                        time.sleep(2)
                        continue
                except Exception as e:
                    print(f"Lane {self.lane_id}: Error opening capture: {e}")
                    time.sleep(2)
                    continue
                
            ret, frame = self.cap.read()
            if not ret:
                if self.source == 0: # Webcam
                     print(f"Lane {self.lane_id}: Failed to read from Webcam.")
                     time.sleep(2)
                     continue
                # End of file, loop
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                continue
            
            # Resize frame here to save bandwidth and processing
            try:
                if frame is not None and frame.size > 0:
                    frame = cv2.resize(frame, (640, 360))
                    with self.lock:
                        self.current_frame = frame
            except Exception as e:
                print(f"Error processing frame for Lane {self.lane_id}: {e}")
            
            time.sleep(0.03) # ~30 FPS

    def read(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.current_frame.copy() if self.current_frame is not None else None

class VideoManager:
    def __init__(self, sources: Dict[int, str]):
        self.streams = {}
        for lane_id, source in sources.items():
            stream = VideoStream(source, lane_id)
            self.streams[lane_id] = stream
            
    def start_all(self):
        for stream in self.streams.values():
            stream.start()
            
    def stop_all(self):
        for stream in self.streams.values():
            stream.stop()
            
    def stop(self, lane_id: int):
        if lane_id in self.streams:
            self.streams[lane_id].stop()
            del self.streams[lane_id]
            print(f"Stopped stream for Lane {lane_id}")

    def update_source(self, lane_id: int, new_source: str):
        if lane_id in self.streams:
            self.streams[lane_id].stop()
        
        # Create and start new stream for this lane (whether it existed or not)
        new_stream = VideoStream(new_source, lane_id)
        self.streams[lane_id] = new_stream
        
        # Only start if supposed to be running? 
        # For now, we always start it because individual streams handle their own state
        # But wait, if system hasn't started, maybe we shouldn't start the stream thread?
        # Actually, VideoStream.start() handles the capture init.
        # Let's just create it. The main system start will call start_all(), 
        # OR if we are doing a live swap, we should start it.
        new_stream.start()
        print(f"Updated Lane {lane_id} source to: {new_source}")
            
    def get_frame(self, lane_id: int) -> Optional[np.ndarray]:
        if lane_id in self.streams:
            return self.streams[lane_id].read()
        return None
