from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import cv2
import asyncio
import json
import time
import os
import shutil
import numpy as np
from typing import List, Dict

from traffic_control import TrafficController
from detection import EmergencyDetector
from stream import VideoManager

app = FastAPI()

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Sources from JSON
try:
    with open("sources.json", "r") as f:
        config = json.load(f)
        video_sources = {
            1: config.get("lane1", 0),
            2: config.get("lane2", "video2.mp4"),
            3: config.get("lane3", "video3.mp4"),
            4: config.get("lane4", "video4.mp4")
        }
except Exception as e:
    print(f"Error loading sources.json: {e}. Using defaults.")
    video_sources = {1: 0, 2: "video2.mp4", 3: "video3.mp4", 4: "video4.mp4"}

video_manager = VideoManager(video_sources)
traffic_controller = TrafficController()
detector = EmergencyDetector() # Loads best.pt

latest_processed_frames = {}
latest_detections = {}  # Store detection info per lane

@app.on_event("startup")
async def startup_event():
    video_manager.start_all()
    await traffic_controller.start()
    asyncio.create_task(processing_loop())

@app.on_event("shutdown")
async def shutdown_event():
    video_manager.stop_all()
    await traffic_controller.stop()

async def processing_loop():
    frame_count = 0
    while True:
        start_time = time.time()
        
        # Run detection every 3 frames to save CPU
        run_inference = (frame_count % 3 == 0)
        
        for lane_id in [1, 2, 3, 4]:
            frame = video_manager.get_frame(lane_id)
            if frame is None:
                continue
            
            # 1. Run inference if it's an inference frame
            if run_inference:
                has_emergency, annotated, detections = detector.detect(frame)
                
                # Store detections for WebSocket
                latest_detections[lane_id] = detections
                
                # Update controller
                traffic_controller.set_emergency(lane_id, has_emergency)
                
                # Use annotated frame for the stream
                display_frame = annotated
            else:
                # Use raw frame or previous annotated frame? 
                # To keep it simple and responsive, use raw frame for non-inference loops
                display_frame = frame

            # 2. ALWAYS update the latest frame for streaming
            try:
                _, buffer = cv2.imencode('.jpg', display_frame)
                latest_processed_frames[lane_id] = buffer.tobytes()
            except Exception as e:
                print(f"Error encoding frame for Lane {lane_id}: {e}")

        frame_count += 1
        # Sleep slightly to maintain ~30FPS and yield control
        await asyncio.sleep(0.01)

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"New client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                pass

manager = ConnectionManager()

@app.websocket("/ws/emergency")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Send updates every 100ms
            state = {
                "signals": traffic_controller.get_states(),
                "emergency": {
                    "is_active": traffic_controller.emergency_mode,
                    "lane_id": traffic_controller.emergency_lane_id
                },
                "detections": {
                    f"lane{lane_id}": latest_detections.get(lane_id, [])
                    for lane_id in [1, 2, 3, 4]
                }
            }
            await websocket.send_text(json.dumps(state))
            await asyncio.sleep(0.1)
            # Check for client disconnect
            # await websocket.receive_text() # This blocks, so we depend on send failing
    except WebSocketDisconnect:
        manager.disconnect(websocket)

def generate_mjpeg(lane_id):
    blank_frame = np.zeros((360, 640, 3), dtype=np.uint8)
    _, blank_buffer = cv2.imencode('.jpg', blank_frame)
    blank_bytes = blank_buffer.tobytes()
    
    while True:
        if lane_id in latest_processed_frames:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_processed_frames[lane_id] + b'\r\n')
        else:
            # Return black frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + blank_bytes + b'\r\n')
        time.sleep(0.05)

@app.get("/video/{lane_id}")
async def video_feed(lane_id: int):
    return StreamingResponse(generate_mjpeg(lane_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.post("/signal/{lane_id}/force")
async def force_signal(lane_id: int):
    asyncio.create_task(traffic_controller.force_green(lane_id))
    return {"status": "success", "message": f"Lane {lane_id} forced to Green"}

@app.post("/signal/{lane_id}/simulate_emergency")
async def simulate_emergency(lane_id: int, active: bool):
    traffic_controller.set_emergency(lane_id, active)
    return {"status": "success", "emergency": active}

@app.post("/upload/{lane_id}")
async def upload_video(lane_id: int, file: UploadFile = File(...)):
    file_path = os.path.join(UPLOAD_DIR, f"lane{lane_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update video manager with new file source
    video_manager.update_source(lane_id, file_path)
    
    # Update sources.json so it persists (optional but good)
    try:
        with open("sources.json", "r") as f:
            config = json.load(f)
        config[f"lane{lane_id}"] = file_path
        with open("sources.json", "w") as f:
            json.dump(config, f)
    except:
        pass

    return {"status": "success", "file_path": file_path}

@app.delete("/video/{lane_id}")
async def clear_video(lane_id: int):
    # Stop the stream for this lane
    video_manager.stop(lane_id)
    
    # Remove from processed frames so it shows blank
    if lane_id in latest_processed_frames:
        del latest_processed_frames[lane_id]
        
    # Remove from detections
    if lane_id in latest_detections:
        del latest_detections[lane_id]

    print(f"Lane {lane_id}: Video cleared.")
    return {"status": "success", "message": f"Video cleared for Lane {lane_id}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
