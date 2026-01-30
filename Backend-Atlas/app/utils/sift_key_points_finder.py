import cv2  
import numpy as np
import os

NUMBER_OF_KEYPOINTS = 5

def find_key_points(file_content: bytes):
    """Detect SIFT key points and descriptors in the given image."""
    print("Finding SIFT key points...")
    # Transforming bytes to numpy array 
    nparr = np.frombuffer(file_content, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape

    # Apply blur to reduce noise before edge detection
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    
    # Create edge mask with lower thresholds (less harsh, detects more edges)
    edges = cv2.Canny(blurred, 75, 175)
    print(f"Edge mask: {np.count_nonzero(edges)} edge pixels")

    # Detect ALL keypoints on edges (no limit)
    sift = cv2.SIFT_create()
    all_keypoints, _ = sift.detectAndCompute(gray, mask=edges)
    
    print(f"Total keypoints detected on edges: {len(all_keypoints)}")
    
    # Filter out keypoints too close to image borders
    border_margin = 20  # pixels from edge
    filtered_keypoints = []
    for kp in all_keypoints:
        x, y = kp.pt
        if (border_margin < x < width - border_margin and 
            border_margin < y < height - border_margin):
            filtered_keypoints.append(kp)
    
    print(f"After border filtering: {len(filtered_keypoints)} keypoints")
    
    # Sort by response (strength) first
    filtered_keypoints = sorted(filtered_keypoints, key=lambda x: x.response, reverse=True)
    
    # Filter out keypoints too close to each other
    min_distance = 10  # minimum pixels between keypoints
    spaced_keypoints = []
    
    for kp in filtered_keypoints:
        # Check distance to all already selected keypoints
        too_close = False
        for selected_kp in spaced_keypoints:
            dx = kp.pt[0] - selected_kp.pt[0]
            dy = kp.pt[1] - selected_kp.pt[1]
            distance = (dx**2 + dy**2)**0.5
            
            if distance < min_distance:
                too_close = True
                break
        
        if not too_close:
            spaced_keypoints.append(kp)
            
        # Stop when we have enough keypoints
        if len(spaced_keypoints) >= NUMBER_OF_KEYPOINTS:
            break
    
    key_points = spaced_keypoints
    print(f"After spacing filter: {len(key_points)} keypoints (min distance: {min_distance}px)")
    
    print(f"Selected top {len(key_points)} keypoints")
    
    # Print keypoint locations for debugging
    for i, kp in enumerate(key_points):
        print(f"  Keypoint {i+1}: ({kp.pt[0]:.1f}, {kp.pt[1]:.1f}), size: {kp.size:.1f}, response: {kp.response:.3f}")

    # Convert to color image to draw colored circles
    img_with_keypoints = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    
    # Draw large, visible circles for each keypoint
    for i, kp in enumerate(key_points):
        x, y = int(kp.pt[0]), int(kp.pt[1])
        # Draw outer circle in green
        cv2.circle(img_with_keypoints, (x, y), 15, (0, 255, 0), 2)
        # Draw center dot in red
        cv2.circle(img_with_keypoints, (x, y), 3, (0, 0, 255), -1)
        # Add number label
        cv2.putText(img_with_keypoints, str(i+1), (x+20, y-10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.join(current_dir, "extracted_texts")
    os.makedirs(output_dir, exist_ok=True)

    # Save edge mask so you can see it
    edge_path = os.path.join(output_dir, "edge_mask.png")
    cv2.imwrite(edge_path, edges)
    print(f"✓ Saved edge mask to: {edge_path}")

    output_path = os.path.join(output_dir, "sift_keypoints.png")
    success = cv2.imwrite(output_path, img_with_keypoints)
    
    if success:
        print(f"✓ Successfully saved keypoints image to: {output_path}")
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"✓ File exists and is {file_size} bytes")
        else:
            print(f"✗ File does not exist after write: {output_path}")
    else:
        print(f"✗ cv2.imwrite() failed for: {output_path}")
    
    return output_path