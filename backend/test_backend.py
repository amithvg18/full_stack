#!/usr/bin/env python
import sys
import traceback

print("=== BACKEND DIAGNOSTIC TEST ===")

try:
    print("1. Testing imports...")
    from fastapi import FastAPI
    from traffic_control import TrafficController
    from detection import EmergencyDetector
    from stream import VideoManager
    print("✅ All imports successful")
    
    print("\n2. Testing TrafficController initialization...")
    tc = TrafficController()
    print(f"✅ TrafficController initialized: {tc}")
    
    print("\n3. Testing EmergencyDetector initialization...")
    detector = EmergencyDetector()
    print(f"✅ EmergencyDetector initialized: {detector}")
    
    print("\n4. Testing VideoManager initialization...")
    vm = VideoManager({})
    print(f"✅ VideoManager initialized: {vm}")
    
    print("\n5. Testing FastAPI app creation...")
    app = FastAPI()
    print(f"✅ FastAPI app created: {app}")
    
    print("\n=== ALL TESTS PASSED ===")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)
