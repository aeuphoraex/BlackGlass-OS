# BlackGlass OS (Hyper-Core)

<img width="256" height="256" alt="image" src="https://github.com/user-attachments/assets/0bfe5e2b-0043-466c-afc4-141d5138b68d" />

BlackGlass is an advanced, high-performance headless Second Life client and multi-agent controller. Evolving from a legacy desktop application, BlackGlass now operates as a sleek, browser-based virtual operating system (BlackGlass OS). It is specifically engineered for multi-client chat management, WebXR cartography, and autonomous agent routing, making it the perfect backbone for managing automated bot fleets and immersive experiences like DUBWARZ.

Download the source or compile to help test and improve this framework!

# 🚀 Features

## 🌐 BlackGlass Web OS Interface

* **Browser-Based Desktop:** Access your Second Life agents via a responsive, windowed virtual OS at `localhost:8080`.
* **Window Manager:** Draggable, minimizable modules including ID Auth, System Terminal, Comm Uplink, Cartography, Radar, and System Monitor.
* **RESTful API Uplink:** Fully asynchronous backend communicating bridging sync HTTP requests with the asynchronous UDP protocol.

## 🧠 Q-Learning AI Autopilot

* **Neural Navigation:** Integrated reinforcement learning module that calculates continuous Z-axis quaternions to autonomously drive avatars.
* **Simulator-Native Routing:** Dispatches robust `AutoPilotLocal` and continuous `AgentUpdate` packets to natively utilize the simulator's NavMesh for smooth obstacle avoidance.

## 🗺️ 3D Cartography & WebXR

* **Three.js Virtual Reality:** Replaces legacy 2D canvases with a fully interactable 3D WebGL scene.
* **Smart Map Fetching:** Bypasses AWS S3 403 Forbidden errors by dynamically testing multiple fallback tile layers (`-objects.jpg`, `-base.jpg`) for seamless region rendering.
* **Click-to-Teleport:** Click directly on the 3D map plane to initiate local coordinate teleportation instantly.
* **Proximity Radar:** A dedicated 2D radar canvas for rapid, top-down tactical awareness of nearby avatars.

## 📨 Advanced Communications & Networking

* **Hippolyzer Core:** Built on the robust `hippolyzer` library (a modern PyOGP revival), abandoning unreliable manual UDP byte-packing for a highly stable network stack.
* **Windows UDP Stabilized:** Implements the `WindowsSelectorEventLoopPolicy` to prevent datagram proactor crashes under heavy simulator network loads.
* **Smart Location Parser:** Paste raw SLurls, region names, or grid coordinates directly into the auth module; the parser automatically resolves them to valid connection URIs.
* **Thread-Safe Dispatch:** Employs precise asynchronous event loops to prevent thread collisions during intensive chat or teleport routines.
