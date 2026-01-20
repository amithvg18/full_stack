import asyncio
import time
from enum import Enum
from typing import List, Dict, Optional, Set

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
        
        # Emergency Logic
        self.emergency_mode = False
        self.active_emergency_lanes: List[int] = [] # List of lanes demanding priority
        self.emergency_lane_id: Optional[int] = None # The specific lane currently given Green (for compatibility & focus)
        
        self.yellow_duration = 2 # Safety transition time
        self.green_duration = 10 # seconds for normal cycle & priority round robin
        
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

    def update_emergency_state(self, lane_ids: List[int]):
        """
        Update the list of lanes checking for emergencies.
        Handle state transitions (Normal -> Emergency) here if needed,
        but main logic is in the control loop.
        """
        self.active_emergency_lanes = lane_ids
        
        if len(self.active_emergency_lanes) > 0:
            if not self.emergency_mode:
                print(f"🚨 Emergency detected in Lanes {self.active_emergency_lanes}. Entering Emergency Mode.")
                self.emergency_mode = True
                # Reset switch time to valid immediate action
                self.last_switch_time = 0 
        else:
            if self.emergency_mode:
                print("✅ Emergency cleared. Resuming normal operation.")
                self.emergency_mode = False
                self.emergency_lane_id = None
                self.last_switch_time = time.time() # Reset for normal cycle

    async def _control_loop(self):
        while self.running:
            try:
                async with self._lock:
                    now = time.time()
                    
                    # --- STATE 0: No Emergency ---
                    if not self.emergency_mode:
                        # Normal Cycle
                        if now - self.last_switch_time >= self.green_duration:
                            await self._cycle_next_lane()

                    # --- Emergency Handling ---
                    else:
                        count = len(self.active_emergency_lanes)
                        
                        # --- STATE 1: Single Emergency ---
                        if count == 1:
                            target = self.active_emergency_lanes[0]
                            # Create sticky behavior
                            if self.emergency_lane_id != target:
                                self.emergency_lane_id = target
                                await self._ensure_lane_green(target)
                            else:
                                # Ensure it stays green (refresh if needed, though _ensure handles checks)
                                await self._ensure_lane_green(target)
                        
                        # --- STATE 2: Multi-Emergency Conflict (Round-Robin) ---
                        elif count > 1:
                            sorted_lanes = sorted(self.active_emergency_lanes)
                            
                            # If we don't have a valid emergency target yet (or it disappeared)
                            if self.emergency_lane_id not in sorted_lanes:
                                # Pick the first available
                                self.emergency_lane_id = sorted_lanes[0]
                                print(f"🚨 Multi-Emergency: Starting Round Robin with Lane {self.emergency_lane_id}")
                                await self._ensure_lane_green(self.emergency_lane_id)
                                self.last_switch_time = time.time()
                            
                            # If we have a target, check if its time is up
                            elif now - self.last_switch_time >= self.green_duration:
                                # Switch to next
                                current_idx = sorted_lanes.index(self.emergency_lane_id)
                                next_idx = (current_idx + 1) % len(sorted_lanes)
                                next_lane = sorted_lanes[next_idx]
                                
                                print(f"🚨 Multi-Emergency: Time up. Switching to Lane {next_lane}")
                                self.emergency_lane_id = next_lane
                                await self._ensure_lane_green(next_lane)
                                self.last_switch_time = time.time()
                            
                            else:
                                # Keep current green
                                await self._ensure_lane_green(self.emergency_lane_id)

            except Exception as e:
                print(f"Error in traffic control loop: {e}")
                
            await asyncio.sleep(0.1)

    async def _ensure_lane_green(self, target_lane_id: int):
        """
        Safely switches signals to make target_lane_id GREEN.
        Includes Yellow clearance if switching from another Green lane.
        """
        target_lane = next((l for l in self.lanes if l.lane_id == target_lane_id), None)
        if not target_lane: return

        # If already Green, ensure others are Red (sanity check)
        if target_lane.state == SignalState.GREEN:
            for lane in self.lanes:
                if lane.lane_id != target_lane_id and lane.state != SignalState.RED:
                    lane.state = SignalState.RED
                    self.hardware.send_update(lane.lane_id, lane.state)
            return

        # Perform Switch
        print(f"🚦 Switching Signal Priority to Lane {target_lane_id}...")
        
        # 1. Turn active GREEN lane to YELLOW -> wait -> RED
        for lane in self.lanes:
            if lane.state == SignalState.GREEN:
                lane.state = SignalState.YELLOW
                self.hardware.send_update(lane.lane_id, lane.state)
                # We are holding the lock, so this pause is safe for state consistency
                await asyncio.sleep(self.yellow_duration)
                
                lane.state = SignalState.RED
                self.hardware.send_update(lane.lane_id, lane.state)
        
        # 2. Turn Target to GREEN
        target_lane.state = SignalState.GREEN
        self.hardware.send_update(target_lane.lane_id, target_lane.state)
        
        # Sync index for normal cycle restoration logic
        self.current_green_lane_index = target_lane_id - 1

    async def _cycle_next_lane(self):
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
        # Synchronous override
        for i, lane in enumerate(self.lanes):
            if lane.lane_id == lane_id:
                lane.state = SignalState.GREEN
                self.current_green_lane_index = i
            else:
                lane.state = SignalState.RED
            self.hardware.send_update(lane.lane_id, lane.state)
        self.last_switch_time = time.time()

    async def force_green(self, lane_id: int):
        """Manually force a lane to green (User override)."""
        async with self._lock:
            await self._ensure_lane_green(lane_id)
            self.last_switch_time = time.time()
