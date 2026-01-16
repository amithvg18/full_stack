from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
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

# Load Sources from JSON
try:
    with open("sources.json", "r") as f:
        config = json.load(f)
        video_sources = {}
        # Only add lanes that are explicitly configured
        for lane_num in [1, 2, 3, 4]:
            lane_key = f"lane{lane_num}"
            if lane_key in config:
                video_sources[lane_num] = config[lane_key]
except Exception as e:
    print(f"Error loading sources.json: {e}. Starting with no videos.")
    video_sources = {}

video_manager = VideoManager(video_sources)
traffic_controller = TrafficController()
detector = EmergencyDetector() # Loads best.pt

latest_processed_frames = {}
latest_detections = {}  # Store detection info per lane

# Video initialization tracking
processing_started = False
system_started = False  # Track if entire system (video_manager + traffic_controller + processing) has started
lanes_with_videos = set()  # Track which lanes have videos loaded
processing_task = None  # Store the processing task reference

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
    # Startup
    # Check if all lanes already have videos from sources.json
    for lane_id in [1, 2, 3, 4]:
        if lane_id in video_sources:
            lanes_with_videos.add(lane_id)
    
    # If all 4 lanes have videos, start the entire system
    if len(lanes_with_videos) == 4:
        await start_system()
    else:
        print(f"⏳ Waiting for all videos to be uploaded. Currently have {len(lanes_with_videos)}/4 lanes ready.")
    
    yield
    
    # Shutdown - only stop if system was started
    if system_started:
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
    global lanes_with_videos
    
    file_path = os.path.join(UPLOAD_DIR, f"lane{lane_id}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    # Update video manager with new file source
    video_manager.update_source(lane_id, file_path)
    
    # Track this lane as having a video
    lanes_with_videos.add(lane_id)
    print(f"✅ Video uploaded for Lane {lane_id}. Total lanes ready: {len(lanes_with_videos)}/4")
    
    # Update sources.json so it persists (optional but good)
    try:
        with open("sources.json", "r") as f:
            config = json.load(f)
        config[f"lane{lane_id}"] = file_path
        with open("sources.json", "w") as f:
            json.dump(config, f)
    except:
        pass
    
    # Auto-start entire system when all 4 lanes have videos
    if len(lanes_with_videos) == 4 and not system_started:
        await start_system()

    return {
        "status": "success", 
        "file_path": file_path,
        "lanes_ready": len(lanes_with_videos),
        "processing_started": processing_started,
        "system_started": system_started
    }

@app.post("/start_processing")
async def manual_start_processing():
    """Manually start the entire system (useful for testing or if auto-start fails)"""
    if system_started:
        return {"status": "already_running", "message": "System is already running"}
    
    if len(lanes_with_videos) < 4:
        return {
            "status": "error", 
            "message": f"Cannot start system. Need all 4 videos. Currently have {len(lanes_with_videos)}/4 lanes ready."
        }
    
    await start_system()
    return {"status": "success", "message": "System started successfully"}

@app.get("/status")
async def get_status():
    """Get current backend status"""
    return {
        "system_started": system_started,
        "processing_started": processing_started,
        "lanes_ready": len(lanes_with_videos),
        "lanes_with_videos": list(lanes_with_videos)
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
