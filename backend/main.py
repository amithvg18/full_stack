from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
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

# Ensure uploads directory exists
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# === STAGING SYSTEM ===
# Videos are staged here before system start
video_staging = {1: None, 2: None, 3: None, 4: None}

# Global instances (initialized as None, created on /simulation/start)
video_manager = None
traffic_controller = None
detector = EmergencyDetector()  # Loads best.pt

latest_processed_frames = {}
latest_detections = {}  # Store detection info per lane

# System state tracking
processing_started = False
system_started = False
processing_task = None

async def start_processing():
    """Start the processing loop if not already started"""
    global processing_started, processing_task
    if not processing_started:
        processing_started = True
        processing_task = asyncio.create_task(processing_loop())
        print("✅ Processing loop started!")

async def start_system():
    """Start the entire system: video manager, traffic controller, and processing loop"""
    global system_started
    if system_started:
        print("ℹ️ System already started.")
        return
    
    print("🚀 Starting entire system with all 4 videos...")
    system_started = True
    
    # Start video streams for all lanes
    video_manager.start_all()
    print("✅ Video manager started for all lanes")
    
    # Start traffic controller
    await traffic_controller.start()
    print("✅ Traffic controller started")
    
    # Start processing loop
    await start_processing()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - No auto-start, wait for user to upload and start
    print("🚦 Backend ready. Upload videos to all 4 lanes, then hit /simulation/start")
    
    yield
    
    # Shutdown - stop if system was started
    global video_manager, traffic_controller
    if system_started and video_manager and traffic_controller:
        video_manager.stop_all()
        await traffic_controller.stop()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def processing_loop():
    frame_count = 0
    while True:
        # Check if system is ready
        if not video_manager or not traffic_controller:
            await asyncio.sleep(0.1)
            continue
            
        start_time = time.time()
        
        # Run detection every 3 frames to save CPU
        run_inference = (frame_count % 3 == 0)
        current_emergency_lanes = []
        
        for lane_id in [1, 2, 3, 4]:
            frame = video_manager.get_frame(lane_id)
            if frame is None:
                continue
            
            # 1. Run inference if it's an inference frame
            if run_inference:
                # Emergency Detection
                has_emergency, annotated, detections = detector.detect(frame)
                
                # Determine display frame
                if has_emergency:
                    display_frame = annotated
                    current_emergency_lanes.append(lane_id)
                else:
                    display_frame = frame

                # Store detections
                latest_detections[lane_id] = detections
                
            else:
                display_frame = frame

            # 2. ALWAYS update the latest frame for streaming
            try:
                _, buffer = cv2.imencode('.jpg', display_frame)
                latest_processed_frames[lane_id] = buffer.tobytes()
            except Exception as e:
                pass

        # Batch Update the Controller after checking all lanes
        if run_inference:
            traffic_controller.update_emergency_state(current_emergency_lanes)

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
    # traffic_controller.set_emergency(lane_id, active)
    # NOTE: Simulation disabled as it conflicts with the continuous detection loop in this version.
    return {"status": "ignored", "message": "Simulation disabled in active loop mode"}

@app.post("/upload/{lane_id}")
async def upload_video(lane_id: int, file: UploadFile = File(...)):
    """Stage a video for a lane without starting system"""
    if lane_id not in [1, 2, 3, 4]:
        return {"status": "error", "message": "Lane ID must be 1-4"}
    
    file_path = os.path.join(UPLOAD_DIR, f"lane{lane_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Stage the video
    video_staging[lane_id] = file_path
    
    # Count how many lanes are ready
    staged_count = sum(1 for v in video_staging.values() if v is not None)
    
    print(f"✅ Video staged for Lane {lane_id}. Total staged: {staged_count}/4")
    
    return {
        "status": "staged",
        "lane_id": lane_id,
        "file_path": file_path,
        "staged_count": staged_count,
        "all_ready": staged_count == 4
    }

@app.post("/simulation/start")
async def start_simulation(background_tasks: BackgroundTasks):
    """Start the simulation with all staged videos"""
    global video_manager, traffic_controller, system_started, processing_started
    
    # Validate all 4 lanes have videos
    if any(v is None for v in video_staging.values()):
        missing = [k for k, v in video_staging.items() if v is None]
        return {
            "status": "error",
            "message": f"Missing videos for lanes: {missing}. Please upload all 4 videos first."
        }, 400
    
    if system_started:
        return {"status": "already_running", "message": "System is already running"}
    
    # Initialize video manager with staged videos
    video_manager = VideoManager(video_staging)
    traffic_controller = TrafficController()
    
    # Start system in background
    background_tasks.add_task(start_system)
    
    print("🚀 Simulation starting with all 4 videos synchronized...")
    
    return {
        "status": "started",
        "message": "Simulation started successfully",
        "lanes": list(video_staging.keys())
    }

@app.post("/simulation/reset")
async def reset_simulation():
    """Reset the simulation and clear all staged videos"""
    global video_manager, traffic_controller, system_started, processing_started, processing_task, video_staging
    
    # Stop system if running
    if system_started:
        if video_manager:
            video_manager.stop_all()
        if traffic_controller:
            await traffic_controller.stop()
        if processing_task:
            processing_task.cancel()
            try:
                await processing_task
            except asyncio.CancelledError:
                pass
    
    # Reset state
    system_started = False
    processing_started = False
    processing_task = None
    video_manager = None
    traffic_controller = None
    video_staging = {1: None, 2: None, 3: None, 4: None}
    latest_processed_frames.clear()
    latest_detections.clear()
    
    print("♻️ Simulation reset complete")
    
    return {
        "status": "reset",
        "message": "Simulation reset successfully. Upload new videos to start again."
    }

@app.get("/status")
async def get_status():
    """Get current backend status"""
    staged_count = sum(1 for v in video_staging.values() if v is not None)
    return {
        "system_started": system_started,
        "processing_started": processing_started,
        "staged_count": staged_count,
        "all_ready": staged_count == 4,
        "video_staging": {k: (v is not None) for k, v in video_staging.items()}
    }

@app.delete("/videos")
async def clear_all_videos():
    """Clear all videos and reset system state"""
    global system_started, processing_started, lanes_with_videos, latest_processed_frames, latest_detections
    
    # Stop everything
    video_manager.stop_all()
    await traffic_controller.stop()
    
    # Reset traffic controller emergency state
    traffic_controller.emergency_mode = False
    traffic_controller.emergency_lane_id = None
    
    # Reset globals
    system_started = False
    processing_started = False
    lanes_with_videos.clear()
    latest_processed_frames.clear()
    latest_detections.clear()
    
    # Clear sources.json
    try:
        with open("sources.json", "w") as f:
            json.dump({}, f)
    except:
        pass

    # Clear VideoManager streams
    # We need to access the internal streams dict to clear it or define a clear method
    # For now, we'll manually clear it by iterating
    # Note: stop_all() just stops threads, doesn't remove objects.
    # We should add a clear_all to VideoManager ideally, but we can't edit that file concurrently.
    # Wait, strict checking says we can't edit multiple files in parallel safely in one turn cleanly 
    # without tool ordering issues sometimes? No, I will rely on Python object reference.
    video_manager.streams.clear()

    print("♻️ System fully reset and all videos cleared.")
    return {"status": "success", "message": "All videos cleared and system reset"}

@app.delete("/video/{lane_id}")
async def clear_video(lane_id: int):
    global lanes_with_videos
    
    # Stop the stream for this lane
    video_manager.stop(lane_id)
    
    # Remove from processed frames so it shows blank
    if lane_id in latest_processed_frames:
        del latest_processed_frames[lane_id]
        
    # Remove from detections
    if lane_id in latest_detections:
        del latest_detections[lane_id]
    
    # Remove from lanes_with_videos
    if lane_id in lanes_with_videos:
        lanes_with_videos.remove(lane_id)

    print(f"Lane {lane_id}: Video cleared.")
    return {"status": "success", "message": f"Video cleared for Lane {lane_id}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
