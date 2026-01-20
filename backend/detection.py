from ultralytics import YOLO
import cv2
import numpy as np

class EmergencyDetector:
    def __init__(self, model_path: str = "best.pt"):
        self.model = YOLO(model_path)
        # Target classes (names as per the custom model)
        # Target classes as per best.pt labels
        self.target_classes = {
            'amb_body_all', 'amb_logo', 'amb_plus', 'amb_text',
            'fire_ladder', 'fire_symbol', 'fire_text', 'fire_truck', 'siren'
        }

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.5):
        """
        Run inference on a frame.
        Returns:
            has_emergency (bool): True if emergency vehicle detected.
            annotated_frame (np.ndarray): Frame with bounding boxes drawn.
        """
        # Resize for performance (optional, YOLOv8 handles it, but explicit consistency is good)
        # frame_resized = cv2.resize(frame, (640, 480)) 
        
        results = self.model(frame, conf=conf_threshold, verbose=False)
        result = results[0]
        
        has_emergency = False
        detections = []
        
        # Check detections
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = result.names[cls_id].lower()
            
            # Store all detections for display
            detections.append({
                "class": class_name,
                "confidence": round(conf, 2)
            })
            
            print(f"Detected: {class_name} with confidence {conf:.2f}")
            
            if class_name in self.target_classes:
                has_emergency = True
                print(f"ALERT: Emergency vehicle ({class_name}) confirmed!")
        
        if has_emergency:
            # Draw custom GREEN boxes for emergency vehicles
            annotated_frame = frame.copy()
            for box in result.boxes:
                cls_id = int(box.cls[0])
                class_name = result.names[cls_id].lower()
                
                if class_name in self.target_classes:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    # Draw Green Rectangle (BGR: 0, 255, 0)
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                    
                    # Add Label
                    label = f"{class_name.upper()} {float(box.conf[0]):.2f}"
                    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(annotated_frame, (x1, y1 - 20), (x1 + w, y1), (0, 255, 0), -1)
                    cv2.putText(annotated_frame, label, (x1, y1 - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
        else:
            # If no emergency, just use default plot or raw frame?
            # Default plot is fine for other objects, but user cares about emergency
            annotated_frame = result.plot()
        
        return has_emergency, annotated_frame, detections

class AccidentDetector:
    def __init__(self, model_path: str = "accident.pt"):
        # Load model if it exists, otherwise we'll handle gracefully
        try:
            self.model = YOLO(model_path)
            self.model_loaded = True
            print(f"✅ Accident Detection Model ({model_path}) loaded successfully!")
        except Exception as e:
            print(f"⚠️ Warning: Could not load accident model ({model_path}): {e}")
            print("   Accident detection will be simulated or disabled.")
            self.model = None
            self.model_loaded = False

        # Target classes for accidents
        self.target_classes = {
            'accident', 'crash', 'fire', 'overturned vehicle', 'collision', 'car_crash'
        }

    def detect(self, frame: np.ndarray, conf_threshold: float = 0.5):
        """
        Run accident detection on a frame.
        """
        if not self.model_loaded:
            return False, frame, []
            
        results = self.model(frame, conf=conf_threshold, verbose=False)
        result = results[0]
        
        has_accident = False
        detections = []
        
        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            class_name = result.names[cls_id].lower()
            
            # Filter for specific accident classes in case the model detects other things too
            if class_name in self.target_classes or 'accident' in class_name:
                detections.append({
                    "class": class_name,
                    "confidence": round(conf, 2)
                })
                
                print(f"🚨 DETECTED ACCIDENT: {class_name} ({conf:.2f})")
                has_accident = True
        
        annotated_frame = frame
        if has_accident:
            # Draw RED/ORANGE boxes for accidents
            annotated_frame = frame.copy()
            for box in result.boxes:
                cls_id = int(box.cls[0])
                class_name = result.names[cls_id].lower()
                
                if class_name in self.target_classes or 'accident' in class_name:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    # Draw Orange Rectangle (BGR: 0, 165, 255)
                    cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 165, 255), 3)
                    
                    label = f"ACCIDENT: {class_name.upper()} {float(box.conf[0]):.2f}"
                    (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                    cv2.rectangle(annotated_frame, (x1, y1 - 20), (x1 + w, y1), (0, 165, 255), -1)
                    cv2.putText(annotated_frame, label, (x1, y1 - 5), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                                
        return has_accident, annotated_frame, detections
