import asyncio
import time
from enum import Enum
from typing import List, Dict, Optional

class SignalState(Enum):
    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"

class LaneState:
    def __init__(self, lane_id: int):
        self.lane_id = lane_id
        self.state = SignalState.RED

# --- HARDWARE INTERFACE ---
class HardwareInterface:
    def __init__(self):
        # Initialize Serial or GPIO here
        # import serial
        # self.ser = serial.Serial('COM3', 9600)
        pass

    def send_update(self, lane_id: int, state: SignalState):
        """
        Send signal change to physical hardware.
        """
        # Example Serial Command:
        # command = f"L{lane_id}:{state.value}\n"
        # self.ser.write(command.encode())
        
        # For now, we simulate it by printing
        print(f"🔌 [HARDWARE OUT] Lane {lane_id} switched to {state.value}")
# --------------------------

class TrafficController:
    def __init__(self, num_lanes: int = 4):
        self.lanes = [LaneState(i) for i in range(1, num_lanes + 1)]
        self.hardware = HardwareInterface() # Initialize hardware
        self.current_green_lane_index = 0
        self.emergency_mode = False
        self.emergency_lane_id: Optional[int] = None
        self.yellow_duration = 1  # Reduced to 1s for faster response
        self.green_duration = 10 # seconds for normal cycle
        self.running = False
        self.last_switch_time = 0.0
        self.loop_task = None
        self._lock = asyncio.Lock()

    async def start(self):
        self.running = True
        # Start with lane 1 Green
        self.set_lane_green(1)
        self.last_switch_time = time.time()
        self.loop_task = asyncio.create_task(self._control_loop())

    async def stop(self):
        self.running = False
        if self.loop_task:
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass

    def get_states(self) -> Dict[str, str]:
        return {f"lane{lane.lane_id}": lane.state.value for lane in self.lanes}

    def set_emergency(self, lane_id: int, detected: bool):
        if detected:
            if not self.emergency_mode or self.emergency_lane_id != lane_id:
                # New emergency or different lane
                print(f"Emergency detected in Lane {lane_id}. Initiating pre-emption.")
                asyncio.create_task(self._handle_emergency_preemption(lane_id))
        else:
            if self.emergency_mode and self.emergency_lane_id == lane_id:
                # Emergency cleared
                print(f"Emergency cleared in Lane {lane_id}. Resuming normal operation.")
                self.emergency_mode = False
                self.emergency_lane_id = None
                self.last_switch_time = time.time() # Reset timer for normal cycle

    async def _handle_emergency_preemption(self, lane_id: int):
        async with self._lock:
            self.emergency_mode = True
            self.emergency_lane_id = lane_id

            # 1. Identify currently GREEN lanes that are NOT the emergency lane
            active_lane_idx = -1
            for i, lane in enumerate(self.lanes):
                if lane.state == SignalState.GREEN and lane.lane_id != lane_id:
                    active_lane_idx = i
                    break
            
            # 2. If there is a conflicting GREEN lane, switch to YELLOW first
            if active_lane_idx != -1:
                lane = self.lanes[active_lane_idx]
                print(f"Switching Lane {lane.lane_id} to YELLOW (Clearance).")
                lane.state = SignalState.YELLOW
                self.hardware.send_update(lane.lane_id, lane.state)
                
                await asyncio.sleep(self.yellow_duration)
                
                lane.state = SignalState.RED
                self.hardware.send_update(lane.lane_id, lane.state)
                print(f"Switching Lane {lane.lane_id} to RED.")

            # 3. Ensure all others are RED
            for i, lane in enumerate(self.lanes):
                if lane.lane_id != lane_id:
                    if lane.state != SignalState.RED:
                        lane.state = SignalState.RED
                        self.hardware.send_update(lane.lane_id, lane.state)
                else:
                    # 4. Set Emergency Lane to GREEN and update index
                    if lane.state != SignalState.GREEN:
                        print(f"Switching Emergency Lane {lane_id} to GREEN.")
                        lane.state = SignalState.GREEN
                        self.hardware.send_update(lane.lane_id, lane.state)
                    self.current_green_lane_index = i
            
            self.last_switch_time = time.time()

    async def _control_loop(self):
        while self.running:
            if not self.emergency_mode:
                now = time.time()
                if now - self.last_switch_time >= self.green_duration:
                    await self._cycle_next_lane()
            await asyncio.sleep(0.1)

    async def _cycle_next_lane(self):
        async with self._lock:
            # Re-check emergency mode inside lock to prevent race conditions
            if self.emergency_mode:
                return

            # Current Green -> Yellow -> Red
            current_lane = self.lanes[self.current_green_lane_index]
            if current_lane.state == SignalState.GREEN:
                current_lane.state = SignalState.YELLOW
                self.hardware.send_update(current_lane.lane_id, current_lane.state)
                
                await asyncio.sleep(self.yellow_duration)
                
                current_lane.state = SignalState.RED
                self.hardware.send_update(current_lane.lane_id, current_lane.state)
            
            # Next Lane
            self.current_green_lane_index = (self.current_green_lane_index + 1) % len(self.lanes)
            next_lane = self.lanes[self.current_green_lane_index]
            next_lane.state = SignalState.GREEN
            self.hardware.send_update(next_lane.lane_id, next_lane.state)
            
            self.last_switch_time = time.time()
            
    def set_lane_green(self, lane_id: int):
        # Synchronous override, usually called from start() or non-async context
        for i, lane in enumerate(self.lanes):
            if lane.lane_id == lane_id:
                lane.state = SignalState.GREEN
                self.current_green_lane_index = i
            else:
                lane.state = SignalState.RED
            # Initial hardware sync
            self.hardware.send_update(lane.lane_id, lane.state)
        self.last_switch_time = time.time()

    async def force_green(self, lane_id: int):
        """Manually force a lane to green with yellow clearance for others."""
        async with self._lock:
            # Similar logic to emergency preemption but without setting emergency_mode permanent
            active_lane_idx = -1
            for i, lane in enumerate(self.lanes):
                if lane.state == SignalState.GREEN and lane.lane_id != lane_id:
                    active_lane_idx = i
                    break
            
            if active_lane_idx != -1:
                lane = self.lanes[active_lane_idx]
                lane.state = SignalState.YELLOW
                self.hardware.send_update(lane.lane_id, lane.state)
                
                await asyncio.sleep(self.yellow_duration)
                
                lane.state = SignalState.RED
                self.hardware.send_update(lane.lane_id, lane.state)

            self.set_lane_green(lane_id)

