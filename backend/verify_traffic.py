import asyncio
import sys
import os

# Ensure we can import from local directory
sys.path.append(os.getcwd())

from traffic_control import TrafficController, SignalState

async def test():
    print("🚦 STARTING TRAFFIC CONTROLLER VERIFICATION 🚦")
    tc = TrafficController()
    # Speed up for testing
    tc.yellow_duration = 2
    tc.green_duration = 10 
    
    await tc.start()
    
    # --- TEST 1: Initial State ---
    print("\n[TEST 1] Checking Initial State (Lane 1 Green)")
    await asyncio.sleep(0.5)
    states = tc.get_states()
    print(f"States: {states}")
    if states["lane1"] == "GREEN" and states["lane2"] == "RED":
        print("✅ PASS")
    else:
        print("❌ FAIL")

    # --- TEST 2: Single Emergency ---
    print("\n[TEST 2] Single Emergency Lane 3")
    tc.update_emergency_state([3])
    # Wait for Yellow(1s) + Buffer
    await asyncio.sleep(2)
    states = tc.get_states()
    print(f"States: {states}")
    if states["lane3"] == "GREEN" and tc.emergency_mode:
        print("✅ PASS")
    else:
        print("❌ FAIL - Lane 3 should be GREEN")

    # --- TEST 3: Multi Emergency Round Robin (Loop Test) ---
    print("\n[TEST 3] Multi Emergency (Lane 1 & 2) - 30 Second Loop")
    print("Setting active lanes to [1, 2]")
    tc.update_emergency_state([1, 2])
    
    # User requested a 30s loop printing status every second
    start_time = asyncio.get_event_loop().time()
    for i in range(30):
        await asyncio.sleep(1)
        states = tc.get_states()
        
        # Determine active green lane for reporting
        green_lane = "NONE"
        for k, v in states.items():
            if v == "GREEN":
                green_lane = k
                break
        
        print(f"T+{i+1}s | Active Green: {green_lane} | Full State: {states}")
    
    print("✅ Loop Test Completed (Check logs for switching behavior)")

    # --- TEST 4: Clear ---
    print("\n[TEST 4] Clear Emergency")
    tc.update_emergency_state([])
    await asyncio.sleep(2)
    states_end = tc.get_states()
    print(f"Final States: {states_end}")
    if not tc.emergency_mode:
        print("✅ PASS - Emergency Mode Cleared")
    else:
        print("❌ FAIL - Still in Emergency Mode")

    await tc.stop()

if __name__ == "__main__":
    asyncio.run(test())
