# AetherControl-FRIDAY
# AetherControl - Mark XXI (F.R.I.D.A.Y.)

An advanced, gesture-controlled desktop automation interface featuring a clean, cinematic holographic HUD inspired by sci-fi heads-up displays. Built using Python, OpenCV, and MediaPipe, this project explores touchless human-computer interaction by mapping natural hand and face movements to standard operating system controls.

## Core Features

* **Cinematic Facial HUD:** Tracks your face using eye-triangulation metrics and handles alignment via a precise nose-focal anchor point. This projects an ultra-wide, minimalist tactical visor over the user window that scales dynamically.
* **Desktop Automation:** Replaces traditional mouse inputs with computer vision pipelines for smooth navigation, clicking, dragging, and real-time hardware adjustments.
* **Contextual Operation Modes:** Includes custom state-machine toggles to switch seamlessly between standard mouse emulation, a specialized Read/Scroll Mode for text navigation, and a low-latency Game Mode.
* **Asynchronous Voice Engine:** Uses a multithreaded Text-to-Speech queuing system to handle status telemetry and voice updates without introducing frame-rate latency to the primary vision matrix.

## Tech Stack

* **Language:** Python 3.10+
* **Computer Vision:** MediaPipe (Face Mesh, Hands tracking), OpenCV
* **OS Automation:** PyAutoGUI, Screen-Brightness-Control
* **Audio Engine:** PyTTSx3 (Multithreaded queueing setup)

## Detailed Architectural Breakdown

The system framework operates via three concurrent layers to ensure low-latency performance:

1. **The Vision Pipeline:** Processes individual frames from the webcam utilizing MediaPipe sub-pipelines. The Face Mesh model dynamically extracts landmarks to anchor the spatial alignment of the graphical visor, while the Hands model interprets coordinate matrices to calculate absolute finger extensions.
2. **The State Machine Engine:** Intercepts spatial coordinates and tracks time thresholds. It evaluates whether gesture sequences match standard navigation profiles or trigger temporal switches (such as holding a specific pose for three consecutive seconds to change operating states).
3. **The Multi-Threaded Audio Pipeline:** Isolates the Text-to-Speech (TTS) processor on a dedicated background worker thread. Because native speech synthesis engines block execution until an audio phrase finishes playing, offloading this task to a standard queue prevents the primary vision loop from dropping frames during voice status telemetry updates.

## Comprehensive Installation and Environment Setup

### Prerequisites
* Python 3.10 or higher installed on your system.
* A functional web camera.

### 1. Project Initialization
Clone the repository and navigate into the source directory:
```bash
git clone [https://github.com/YOUR_USERNAME/AetherControl-FRIDAY.git](https://github.com/YOUR_USERNAME/AetherControl-FRIDAY.git)
cd AetherControl-FRIDAY
