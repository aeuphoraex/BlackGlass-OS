import sys
import asyncio

# Critical Windows UDP Stability Fix (Prevents ProactorEventLoop Datagram Crash)
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import time
import threading
import json
import base64
import math
import random
import re
import uuid as _uuid
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

# Hippolyzer Core Imports
from hippolyzer.lib.base.message.message import Message, Block
from hippolyzer.lib.base.datatypes import Vector3, Quaternion, UUID
from hippolyzer.lib.base.templates import ChatType, ChatSourceType, IMDialogType
from hippolyzer.lib.client.hippo_client import HippoClient, StartLocation

# ==========================================
# SECTION 1: SMART INPUT PARSER
# ==========================================

class SmartParser:
    """Parses SLurls, Region Names, and Coordinate strings."""
    @staticmethod
    def parse_start_location(input_str):
        slurl_pattern = r"secondlife/([^/]+)(?:/(\d+))?(?:/(\d+))?(?:/(\d+))?"
        match = re.search(slurl_pattern, input_str)
        if match:
            region = urllib.parse.unquote(match.group(1))
            x = match.group(2) or "128"
            y = match.group(3) or "128"
            z = match.group(4) or "25"
            return f"uri:{region}&{x}&{y}&{z}"

        if "/" in input_str and not input_str.startswith("http"):
            parts = input_str.split('/')
            region = parts[0].strip()
            x = parts[1].strip() if len(parts) > 1 else "128"
            y = parts[2].strip() if len(parts) > 2 else "128"
            z = parts[3].strip() if len(parts) > 3 else "25"
            return f"uri:{region}&{x}&{y}&{z}"

        if input_str.lower() in ["home", "last"]:
            return getattr(StartLocation, input_str.upper())

        return f"uri:{input_str}&128&128&25"

# ==========================================
# SECTION 2: SHARED STATE & Q-LEARNING
# ==========================================

class LimitedList:
    """Thread-safe wrapped list (Prevents NoneType C-struct inheritance crashes)."""
    def __init__(self, limit=200):
        self.limit = limit
        self.data = []
    def append(self, item):
        self.data.append(item)
        if len(self.data) > self.limit:
            self.data.pop(0)
    def as_list(self):
        return list(self.data)

class SharedState:
    def __init__(self):
        self.lock = threading.Lock()
        self.messages = LimitedList(200)
        self.map_data = None
        self.current_region = "Unknown"
        self.nearby_avatars = []
        self.pos = {"x": 128.0, "y": 128.0, "z": 0.0}
        self.sim_fps = 45.0
        self.time_dilation = 1.0
        self.connected = False
        self.grid_x = 0
        self.grid_y = 0
        self.full_name = "User"

    def log(self, text, msg_type="info", meta=None):
        print(f"[{msg_type.upper()}] {text}")
        msg_obj = {"time": time.strftime("%H:%M:%S"), "text": text, "type": msg_type}
        if meta: msg_obj["meta"] = meta
        with self.lock: self.messages.append(msg_obj)

    def update_pos(self, x, y, z):
        with self.lock: self.pos = {"x": float(x), "y": float(y), "z": float(z)}

    def update_nearby(self, avatars):
        with self.lock: self.nearby_avatars = list(avatars)

    def update_region(self, name, grid_x=None, grid_y=None):
        with self.lock:
            if name and name != "Unknown":
                self.current_region = name
            if grid_x and grid_x > 0: self.grid_x = grid_x
            if grid_y and grid_y > 0: self.grid_y = grid_y

    def snapshot(self):
        with self.lock:
            return {
                "messages": self.messages.as_list(),
                "map": self.map_data,
                "region": self.current_region,
                "nearby": list(self.nearby_avatars),
                "stats": {"fps": self.sim_fps, "dilation": self.time_dilation, "pos": dict(self.pos)}
            }

class QLearningDrive:
    """Manual AgentDrive Neural Net (Continuous ControlFlag Movement)."""
    def __init__(self, state):
        self.state = state
        self.active = False
        self.target_pos = None

    def toggle(self):
        self.active = not self.active
        self.target_pos = None
        return self.active

    @property
    def pos(self):
        p = self.state.pos
        return type('V', (), {'x': p['x'], 'y': p['y'], 'z': p['z']})()

    def dist_xy(self, x1, y1, x2, y2): 
        return ((x1 - x2)**2 + (y1 - y2)**2)**0.5

    def decide(self):
        if not self.active: return 0, (0, 0, 0, 1)
        me = self.pos
        
        # Determine Waypoint
        if not self.target_pos or self.dist_xy(me.x, me.y, self.target_pos[0], self.target_pos[1]) < 2.0:
            self.target_pos = (random.randint(20, 236), random.randint(20, 236))
            self.state.log(f"AI AUTOPILOT: Routing to Sector <{self.target_pos[0]}, {self.target_pos[1]}>", "system")
        
        # Calculate Angular Rotation
        dx = self.target_pos[0] - me.x
        dy = self.target_pos[1] - me.y
        target_angle = math.atan2(dy, dx)
        
        qz = math.sin(target_angle / 2.0)
        qw = math.cos(target_angle / 2.0)
        
        # 1 = AT_FORWARD (Walk Control Flag)
        return 1, (0, 0, qz, qw)

# ==========================================
# SECTION 3: HIPPO CLIENT
# ==========================================

class HippoSLClient:
    def __init__(self):
        self.state = SharedState()
        self.neural = QLearningDrive(self.state)
        self._hippo = None
        self._loop = None

    def log(self, text, msg_type="info", meta=None):
        self.state.log(text, msg_type, meta)

    def login(self, first, last, password, start_input="last"):
        self.state.log(f"Resolving Location: {start_input}...", "system")
        start_loc = SmartParser.parse_start_location(start_input)
        self.state.log(f"Target URI: {start_loc}", "system")
        self.state.full_name = f"{first} {last}"

        # DEEP-FIX: Extract UI Region Name directly from URI
        if start_loc.startswith("uri:"):
            r_name = urllib.parse.unquote(start_loc[4:].split('&')[0])
            self.state.update_region(r_name)

        self._loop = asyncio.new_event_loop()
        login_done = threading.Event()
        login_result = [False]

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self._async_main(first, last, password, start_loc, login_done, login_result))

        threading.Thread(target=run_loop, daemon=True).start()
        login_done.wait(timeout=45)
        return login_result[0]

    async def _async_main(self, first, last, password, start_loc, login_done, login_result):
        self._hippo = HippoClient()
        try:
            await self._hippo.login(username=f"{first} {last}", password=password, start_location=start_loc, agree_to_tos=True)
            
            timeout = 15
            while not self._hippo.main_circuit and timeout > 0:
                await asyncio.sleep(0.5); timeout -= 0.5
            if not self._hippo.main_circuit: raise Exception("UDP Circuit Timeout")

            pres_msg = Message("CompleteAgentMovement", Block("AgentData", 
                AgentID=self._hippo.session.agent_id, SessionID=self._hippo.session.id, 
                CircuitCode=self._hippo.session.login_data['circuit_code']))
            self._hippo.main_circuit.send(pres_msg)

            login_data = self._hippo.session.login_data
            if "region_x" in login_data and "region_y" in login_data:
                gx = int(login_data["region_x"]) // 256
                gy = int(login_data["region_y"]) // 256
                self.state.update_region(self.state.current_region, gx, gy)
            
            self.state.connected = True
            login_result[0] = True
            login_done.set()

            h = self._hippo.session.message_handler
            h.subscribe("ChatFromSimulator", self._on_chat)
            h.subscribe("ImprovedInstantMessage", self._on_im)
            h.subscribe("RegionHandshake", self._on_region_handshake)
            h.subscribe("TeleportFinish", self._on_teleport_finish)
            h.subscribe("ObjectUpdate", self._on_object_update)

            self._fetch_map()

            while self.state.connected:
                try:
                    self._sync_state()
                    
                    if self.neural.active:
                        controls, rot = self.neural.decide()
                    else:
                        controls, rot = 0, (0, 0, 0, 1)

                    await self._send_agent_update(controls, rot)

                except Exception as e:
                    print(f"[LOOP_ERR] {e}")
                    import traceback; traceback.print_exc()
                
                # Poll faster (0.2s) to maintain AI walking fluidity
                await asyncio.sleep(0.2)

        except Exception as e:
            self.state.log(f"Login Fault: {e}", "error")
            login_result[0] = False
            login_done.set()

    def _sync_state(self):
        if self._hippo.position:
            p = self._hippo.position
            self.state.update_pos(p.X, p.Y, p.Z)
        
        if self._hippo.session and self._hippo.session.objects:
            nearby = []
            my_id = self._hippo.session.agent_id
            for av in self._hippo.session.objects.all_avatars:
                if av.FullID != my_id and av.RegionPosition:
                    p = av.RegionPosition
                    nearby.append({"x": float(p.X), "y": float(p.Y), "z": float(p.Z)})
            self.state.update_nearby(nearby)

    async def _send_agent_update(self, control_flags=0, rot_tuple=(0,0,0,1)):
        if not self._hippo.main_circuit or not self._hippo.session: return
        qx, qy, qz, qw = rot_tuple
        pos = self._hippo.position or Vector3(128, 128, 0)
        
        msg = Message("AgentUpdate", Block("AgentData",
            AgentID=self._hippo.session.agent_id, SessionID=self._hippo.session.id,
            BodyRotation=Quaternion(qx, qy, qz, qw), HeadRotation=Quaternion(qx, qy, qz, qw),
            State=0, CameraCenter=pos, CameraAtAxis=Vector3(1,0,0), CameraLeftAxis=Vector3(0,1,0),
            CameraUpAxis=Vector3(0,0,1), Far=128.0, ControlFlags=int(control_flags), Flags=0))
        self._hippo.main_circuit.send(msg)

    def _on_im(self, message):
        try:
            msg_block = message["MessageBlock"]
            
            try: msg_text = str(msg_block["Message"])
            except KeyError: msg_text = ""

            try: from_name = str(msg_block["FromAgentName"])
            except KeyError: from_name = "Unknown"
            
            try: from_id = str(msg_block["FromAgentID"])
            except KeyError:
                try: from_id = str(message["AgentData"]["AgentID"])
                except KeyError: from_id = "Unknown"

            try: dialog = msg_block["Dialog"]
            except KeyError: dialog = 0

            if dialog == 0:
                self.state.log(f"[IM] {from_name}: {msg_text}", "im", {"id": from_id})
        except Exception as e:
            self.state.log(f"IM Parse Exception: {e}", "error")

    def _on_chat(self, m):
        if m["ChatData"]["ChatType"] not in (ChatType.TYPING_START, ChatType.TYPING_STOP):
            self.state.log(f"{m['ChatData']['FromName']}: {m['ChatData']['Message']}", "chat")

    def _on_region_handshake(self, m):
        name = str(m["RegionInfo"]["SimName"])
        self.state.update_region(name)
        self.state.log(f"Welcome to {name}", "system")
        self._fetch_map()

    def _on_teleport_finish(self, m):
        handle = m["Info"]["RegionHandle"]
        if handle:
            gx = int((handle & 0xFFFFFFFF) / 256)
            gy = int((handle >> 32) / 256)
            self.state.update_region(self.state.current_region, gx, gy)
            self.state.log(f"Teleport Complete. Grid: <{gx}, {gy}>", "success")
            self._fetch_map()

    def _on_object_update(self, m):
        try:
            td = float(m["RegionData"]["TimeDilation"]) / 65535.0
            with self.state.lock:
                self.state.time_dilation = td
                self.state.sim_fps = td * 45.0
        except: pass

    def _fetch_map(self):
        def _fetch_thread():
            try:
                with self.state.lock:
                    gx, gy = self.state.grid_x, self.state.grid_y
                
                if gx == 0 or gy == 0: return

                urls = [
                    f"https://map.secondlife.com/map-1-{gx}-{gy}-objects.jpg",
                    f"https://map.secondlife.com/map-1-{gx}-{gy}-base.jpg"
                ]
                headers = {'User-Agent': 'Mozilla/5.0'}
                
                success = False
                for url in urls:
                    try:
                        req = urllib.request.Request(url, headers=headers)
                        with urllib.request.urlopen(req) as response:
                            data = response.read()
                            if len(data) > 1000:
                                with self.state.lock:
                                    self.state.map_data = base64.b64encode(data).decode('utf-8')
                                self.state.log("Map Visuals Acquired.", "success")
                                success = True
                                break
                    except urllib.error.HTTPError as e:
                        if e.code == 403: continue 
                        raise e
                    except Exception:
                        pass
                
                if not success:
                    self.state.log("Map Uplink Failed: Sim tiles are unrendered or void.", "error")

            except Exception as e:
                self.state.log(f"Map Uplink Fatal: {e}", "error")

        threading.Thread(target=_fetch_thread, daemon=True).start()

    def send_chat(self, message, chat_type=1, channel=0):
        if not self.state.connected or not self._loop: return
        if message.startswith("/im "):
            parts = message.split(' ', 2)
            if len(parts) >= 3:
                self.send_im(parts[1], parts[2])
                return
                
        ct = ChatType(chat_type) if isinstance(chat_type, int) else chat_type
        
        def _do_chat():
            try:
                self._hippo.send_chat(message, channel=channel, chat_type=ct)
            except Exception as e:
                self.state.log(f"Chat execution failed: {e}", "error")

        self._loop.call_soon_threadsafe(_do_chat)
        self.state.log(f"You: {message}", "chat_own")

    def send_im(self, to_id, message):
        async def _send():
            msg = Message("ImprovedInstantMessage",
                Block("AgentData", AgentID=self._hippo.session.agent_id, SessionID=self._hippo.session.id),
                Block("MessageBlock", FromAgentName=self.state.full_name, ToAgentID=UUID(to_id),
                    ParentEstateID=0, RegionID=UUID(), Position=self._hippo.position or Vector3(0,0,0),
                    Offline=0, Dialog=0, ID=UUID(str(_uuid.uuid4())), Timestamp=int(time.time()),
                    FromAgentID=self._hippo.session.agent_id, Message=message, BinaryBucket=b""))
            self._hippo.main_circuit.send(msg)
        asyncio.run_coroutine_threadsafe(_send(), self._loop)
        self.state.log(f"To {to_id}: {message}", "im")

    def teleport_local(self, x, y, z):
        if not self.state.connected or not self._loop: return
        with self.state.lock: gx, gy = self.state.grid_x, self.state.grid_y
        handle = (gy * 256 << 32) | (gx * 256)

        def _do_teleport():
            try:
                msg = Message("TeleportLocationRequest",
                    Block("AgentData", AgentID=self._hippo.session.agent_id, SessionID=self._hippo.session.id),
                    Block("Info", RegionHandle=handle, Position=Vector3(float(x), float(y), float(z)), LookAt=Vector3(float(x), float(y+1), float(z)))
                )
                self._hippo.main_circuit.send(msg)
                self.state.log(f"Teleport to <{x}, {y}, {z}> dispatched.", "success")
            except Exception as e:
                self.state.log(f"Teleport request failed: {e}", "error")

        self._loop.call_soon_threadsafe(_do_teleport)
        self.state.log(f"Initializing Teleport Sequence to <{x}, {y}, {z}>...", "system")

# ==========================================
# SECTION 4: WEB SERVER
# ==========================================

client = HippoSLClient()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BlackGlass OS v3.0</title>

    <script type="importmap">
      {
        "imports": {
          "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
          "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
        }
      }
    </script>

    <style>
        :root {
            --bg-color: #050505;
            --win-bg: #111116;
            --win-header: #1a1a20;
            --accent: #00d4ff;
            --text: #ececec;
            --success: #00ff9d;
            --err: #ff4757;
            --im-color: #d000ff;
            --taskbar-bg: #0a0a0a;
            --border: #333;
        }

        * { box-sizing: border-box; user-select: none; }

        body {
            margin: 0;
            font-family: 'Consolas', 'Monaco', monospace;
            background: var(--bg-color);
            color: var(--text);
            height: 100vh;
            overflow: hidden;
            background-image: radial-gradient(circle at center, #111 0%, #000 100%);
        }

        #boot-screen {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background: #000; z-index: 9999; padding: 40px;
            font-size: 14px; color: #aaa;
            display: flex; flex-direction: column;
        }
        .boot-line { margin-bottom: 5px; opacity: 0; animation: typeLine 0.1s forwards; }
        @keyframes typeLine { to { opacity: 1; } }

        #desktop {
            position: absolute; top: 0; left: 0; width: 100%; height: calc(100% - 40px);
            z-index: 1;
        }

        .window {
            position: absolute;
            background: var(--win-bg);
            border: 1px solid var(--border);
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
            display: flex; flex-direction: column;
            opacity: 0; transform: scale(0.95);
            transition: opacity 0.2s, transform 0.2s;
            min-width: 300px; min-height: 200px;
        }
        .window.visible { opacity: 1; transform: scale(1); }

        .window-header {
            background: var(--win-header);
            padding: 8px 10px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--border);
            cursor: grab;
        }
        .window-header:active { cursor: grabbing; }
        .win-title { font-weight: bold; color: var(--accent); font-size: 0.9rem; text-transform: uppercase; letter-spacing: 1px; }
        .win-controls span {
            display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-left: 6px; cursor: pointer;
        }
        .ctrl-min { background: #f1c40f; }
        .ctrl-max { background: #2ecc71; }
        .ctrl-close { background: #e74c3c; }

        .window-content { flex: 1; padding: 10px; overflow: hidden; position: relative; display: flex; flex-direction: column; }

        #taskbar {
            position: absolute; bottom: 0; left: 0; width: 100%; height: 40px;
            background: var(--taskbar-bg); border-top: 1px solid var(--border);
            display: flex; align-items: center; padding: 0 10px; z-index: 9000;
        }
        #start-btn {
            background: var(--accent); color: #000; padding: 5px 15px; font-weight: bold; cursor: pointer; margin-right: 20px;
        }
        #start-menu {
            position: absolute; bottom: 42px; left: 10px; width: 200px; background: var(--win-bg);
            border: 1px solid var(--border); display: none; z-index: 9001;
        }
        .menu-item { padding: 10px; border-bottom: 1px solid #222; cursor: pointer; color: #aaa; }
        .menu-item:hover { background: #222; color: #fff; }

        .task-item {
            padding: 5px 15px; background: #222; margin-right: 5px; cursor: pointer; border-bottom: 2px solid transparent; color: #888;
        }
        .task-item.active { border-bottom: 2px solid var(--accent); color: #fff; background: #333; }

        #term-log { flex: 1; overflow-y: auto; font-size: 0.85rem; font-family: monospace; color: #0f0; }
        .log-line { margin-bottom: 2px; }
        .log-sys { color: #888; }
        .log-err { color: var(--err); }
        .log-suc { color: var(--success); }

        #chat-history { flex: 1; overflow-y: auto; margin-bottom: 10px; background: #000; border: 1px solid #333; padding: 5px; }
        .msg { margin-bottom: 4px; font-size: 0.9rem; word-wrap: break-word; }
        .msg.chat { color: #ccc; }
        .msg.chat_own { color: var(--accent); text-align: right; }
        .msg.im { color: var(--im-color); border-left: 2px solid var(--im-color); padding-left: 5px; }
        .reply-link { cursor: pointer; text-decoration: underline; font-size: 0.75em; margin-left: 5px; color: #fff; }

        #chat-input-row { display: flex; gap: 5px; }
        #chat-input { flex: 1; background: #000; border: 1px solid #444; color: #fff; padding: 5px; }
        #chat-send { background: var(--accent); border: none; color: #000; font-weight: bold; cursor: pointer; padding: 0 15px; }

        .login-field { margin-bottom: 10px; }
        .login-field label { display: block; font-size: 0.8rem; color: #888; margin-bottom: 2px; }
        .login-field input { width: 100%; background: #000; border: 1px solid #444; color: #fff; padding: 8px; }
        #btn-login { width: 100%; padding: 10px; background: var(--accent); border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        #login-status { margin-top: 10px; font-size: 0.8rem; text-align: center; height: 20px; }

        #three-container { width: 100%; height: 100%; background: #000; display: block; overflow: hidden; position: relative; }
        #map-info { position: absolute; bottom: 5px; left: 5px; background: rgba(0,0,0,0.7); padding: 2px 5px; font-size: 0.8rem; z-index: 10; pointer-events: none; color: #fff; }

        .tp-controls {
            position: absolute; top: 10px; right: 10px; z-index: 20; display: flex; flex-direction: column; gap: 5px;
        }
        .tp-btn {
            background: rgba(0, 212, 255, 0.2); border: 1px solid var(--accent); color: var(--accent);
            font-weight: bold; cursor: pointer; padding: 5px 10px; font-size: 0.8rem; text-align: center;
        }
        .tp-btn:hover { background: var(--accent); color: #000; }

        #radar-canvas { background: #000; width: 100%; height: 100%; border: 1px solid #333; }

        .stat-row { display: flex; justify-content: space-between; border-bottom: 1px solid #222; padding: 5px 0; }
        .stat-val { color: var(--accent); font-weight: bold; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #111; }
        ::-webkit-scrollbar-thumb { background: #333; }
        ::-webkit-scrollbar-thumb:hover { background: #555; }
    </style>
</head>
<body>
    <div id="boot-screen">
        <div class="boot-line">BLACKGLASS BIOS v5.0 (HIPPOLYZER CORE)</div>
        <div class="boot-line">CPU: Virtual x86 @ 4.0GHz</div>
        <div class="boot-line">Initializing WebXR Subsystems...</div>
        <div class="boot-line">Loading Reinforcement Learning Module...</div>
        <div class="boot-line">System Ready.</div>
    </div>

    <div id="desktop" style="display:none;">
        <div id="win-login" class="window" style="width: 300px; height: 380px; left: 50px; top: 50px; z-index: 100;">
            <div class="window-header">
                <div class="win-title">ID_AUTH_MODULE</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content">
                <div class="login-field">
                    <label>FIRST NAME</label>
                    <input type="text" id="inp-first" value="">
                </div>
                <div class="login-field">
                    <label>LAST NAME</label>
                    <input type="text" id="inp-last" value="">
                </div>
                <div class="login-field">
                    <label>PASSPHRASE</label>
                    <input type="password" id="inp-pass" value="">
                </div>
                <div class="login-field">
                    <label>TARGET GRID LOC</label>
                    <input type="text" id="inp-loc" value="last" placeholder="Region Name">
                </div>
                <button id="btn-login" onclick="app.login()">INITIALIZE UPLINK</button>
                <div id="login-status">STANDBY</div>
            </div>
        </div>

        <div id="win-term" class="window" style="width: 500px; height: 300px; right: 20px; top: 20px; z-index: 90;">
            <div class="window-header">
                <div class="win-title">SYS_LOG_TERMINAL</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-max"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content">
                <div id="term-log"></div>
            </div>
        </div>

        <div id="win-comm" class="window" style="width: 400px; height: 500px; left: 380px; top: 100px; z-index: 95; display: none;">
            <div class="window-header">
                <div class="win-title">COMM_UPLINK_V2</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-max"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content">
                <div id="chat-history"></div>
                <div id="chat-input-row">
                    <input type="text" id="chat-input" placeholder="Transmit..." onkeypress="if(event.key==='Enter') app.sendChat()">
                    <button id="chat-send" onclick="app.sendChat()">TX</button>
                </div>
            </div>
        </div>

        <div id="win-map" class="window" style="width: 600px; height: 500px; right: 50px; bottom: 60px; z-index: 92; display: none;">
            <div class="window-header">
                <div class="win-title">CARTOGRAPHY_3D (AI)</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-max"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content" style="padding: 0;">
                <div id="three-container"></div>
                <div id="map-info">UNKNOWN SECTOR</div>
                <div class="tp-controls">
                    <div class="tp-btn" id="btn-neural" onclick="app.toggleNeural()">AI AUTOPILOT: OFF</div>
                    <div class="tp-btn" style="border-color: #f0f;">CLICK TO TELEPORT</div>
                </div>
            </div>
        </div>

        <div id="win-radar" class="window" style="width: 250px; height: 250px; left: 20px; bottom: 60px; z-index: 93; display: none;">
            <div class="window-header">
                <div class="win-title">PROXIMITY_RADAR</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-max"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content">
                <canvas id="radar-canvas"></canvas>
            </div>
        </div>

        <div id="win-mon" class="window" style="width: 200px; height: 200px; left: 50px; top: 100px; z-index: 94; display: none;">
            <div class="window-header">
                <div class="win-title">SYS_MONITOR</div>
                <div class="win-controls"><span class="ctrl-min"></span><span class="ctrl-close"></span></div>
            </div>
            <div class="window-content">
                <div class="stat-row"><span>SIM FPS</span><span class="stat-val" id="stat-fps">--</span></div>
                <div class="stat-row"><span>DILATION</span><span class="stat-val" id="stat-dil">--</span></div>
                <div class="stat-row"><span>PING</span><span class="stat-val" id="stat-ping">--</span></div>
                <div class="stat-row"><span>COORDS</span><span class="stat-val" id="stat-pos">--</span></div>
            </div>
        </div>
    </div>

    <div id="taskbar" style="display:none;">
        <div id="start-btn" onclick="wm.toggleStart()">:: SYSTEM</div>
        <div class="task-item active" id="task-auth" onclick="wm.focus('win-login')">AUTH</div>
        <div class="task-item" id="task-term" onclick="wm.focus('win-term')">TERMINAL</div>
        <div class="task-item" onclick="wm.focus('win-comm')" id="task-comm" style="display:none;">COMMS</div>
        <div class="task-item" onclick="wm.focus('win-map')" id="task-map" style="display:none;">MAP</div>
        <div class="task-item" onclick="wm.focus('win-radar')" id="task-radar" style="display:none;">RADAR</div>
        <div class="task-item" onclick="wm.focus('win-mon')" id="task-mon" style="display:none;">MON</div>
        <div style="margin-left: auto; font-size: 0.8rem; color: #666;" id="clock">00:00:00</div>
    </div>

    <div id="start-menu">
        <div class="menu-item" onclick="wm.open('win-term')">SYSTEM LOGS</div>
        <div class="menu-item" onclick="wm.open('win-comm')">COMMUNICATIONS</div>
        <div class="menu-item" onclick="wm.open('win-map')">CARTOGRAPHY (VR)</div>
        <div class="menu-item" onclick="wm.open('win-radar')">RADAR SCANNER</div>
        <div class="menu-item" onclick="wm.open('win-mon')">PERFORMANCE</div>
        <div class="menu-item" onclick="wm.open('win-login')">RE-AUTHENTICATE</div>
        <div class="menu-item" style="border-top: 1px solid #444; color: #ff4757;" onclick="location.reload()">SHUTDOWN</div>
    </div>

    <script type="module">
        import * as THREE from 'three';
        import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
        import { VRButton } from 'three/addons/webxr/VRButton.js';

        const wm = {
            zIndex: 100,
            windows: document.querySelectorAll('.window'),
            init() {
                this.windows.forEach(win => {
                    this.makeDraggable(win);
                    win.addEventListener('mousedown', () => this.focus(win.id));
                    win.querySelector('.ctrl-close').onclick = () => this.close(win.id);
                    win.querySelector('.ctrl-min').onclick = () => this.minimize(win.id);
                });
            },
            focus(id) {
                const win = document.getElementById(id);
                if(win.style.display === 'none' || win.style.display === '') {
                    win.style.display = 'flex';
                    setTimeout(() => win.classList.add('visible'), 10);
                }
                win.style.zIndex = ++this.zIndex;
                document.getElementById('start-menu').style.display = 'none';
                this.updateTaskbar(id);
            },
            updateTaskbar(winId) {
                document.querySelectorAll('.task-item').forEach(t => t.classList.remove('active'));
                const map = {'win-login':'task-auth','win-term':'task-term','win-comm':'task-comm','win-map':'task-map','win-radar':'task-radar','win-mon':'task-mon'};
                const taskId = map[winId];
                if(taskId) {
                    const taskEl = document.getElementById(taskId);
                    if(taskEl) taskEl.classList.add('active');
                }
            },
            open(id) {
                this.focus(id);
                const taskID = id.replace('win-', 'task-');
                const taskEl = document.getElementById(taskID);
                if(taskEl) taskEl.style.display = 'block';
            },
            close(id) {
                const win = document.getElementById(id);
                win.classList.remove('visible');
                setTimeout(() => win.style.display = 'none', 200);
            },
            minimize(id) { this.close(id); },
            toggleStart() {
                const menu = document.getElementById('start-menu');
                menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
            },
            makeDraggable(el) {
                let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
                const header = el.querySelector('.window-header');
                header.onmousedown = dragMouseDown;
                function dragMouseDown(e) {
                    e = e || window.event;
                    e.preventDefault();
                    pos3 = e.clientX;
                    pos4 = e.clientY;
                    document.onmouseup = closeDragElement;
                    document.onmousemove = elementDrag;
                    wm.focus(el.id);
                }
                function elementDrag(e) {
                    e = e || window.event;
                    e.preventDefault();
                    pos1 = pos3 - e.clientX;
                    pos2 = pos4 - e.clientY;
                    pos3 = e.clientX;
                    pos4 = e.clientY;
                    el.style.top = (el.offsetTop - pos2) + "px";
                    el.style.left = (el.offsetLeft - pos1) + "px";
                }
                function closeDragElement() {
                    document.onmouseup = null;
                    document.onmousemove = null;
                }
            }
        };

        const app = {
            msgCount: 0,
            controls: 0,
            scene: null,
            camera: null,
            renderer: null,
            mapPlane: null,
            avatars: [],
            lastMapData: null,
            raycaster: new THREE.Raycaster(),
            mouse: new THREE.Vector2(),
            neuralActive: false,

            async login() {
                const btn = document.getElementById('btn-login');
                const stat = document.getElementById('login-status');
                btn.disabled = true;
                stat.innerText = "HANDSHAKING...";
                stat.style.color = "#00d4ff";

                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        first: document.getElementById('inp-first').value,
                        last: document.getElementById('inp-last').value,
                        pass: document.getElementById('inp-pass').value,
                        start: document.getElementById('inp-loc').value
                    })
                });
                const data = await res.json();

                if(data.success) {
                    stat.innerText = "UPLINK ESTABLISHED";
                    stat.style.color = "#00ff9d";
                    setTimeout(() => {
                        wm.close('win-login');
                        this.openSession();
                    }, 1000);
                } else {
                    stat.innerText = "ACCESS DENIED";
                    stat.style.color = "#ff4757";
                    btn.disabled = false;
                }
            },

            openSession() {
                ['win-comm', 'win-map', 'win-radar', 'win-mon'].forEach(id => wm.open(id));
                setTimeout(() => this.initThree(), 100);
            },

            async sendChat() {
                const input = document.getElementById('chat-input');
                if(!input.value) return;
                await fetch('/api/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({msg: input.value})
                });
                input.value = "";
            },

            async teleportLocal(x, y, z) {
                await fetch('/api/teleport', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({region: "local", x: x, y: y, z: z})
                });
                wm.open('win-comm');
            },

            setReply(id) {
                const input = document.getElementById('chat-input');
                input.value = "/im " + id + " ";
                input.focus();
            },

            toggleNeural() {
                this.neuralActive = !this.neuralActive;
                fetch('/api/neural', { method: 'POST' });
                const btn = document.getElementById('btn-neural');
                if(this.neuralActive) {
                    btn.innerText = "AI AUTOPILOT: ON";
                    btn.style.background = "#00ff9d";
                    btn.style.color = "#000";
                } else {
                    btn.innerText = "AI AUTOPILOT: OFF";
                    btn.style.background = "";
                    btn.style.color = "";
                }
            },

            initThree() {
                if (this.renderer) return;
                const container = document.getElementById('three-container');
                const width = container.clientWidth || 600;
                const height = container.clientHeight || 500;

                this.scene = new THREE.Scene();
                this.scene.background = new THREE.Color(0x111116);
                this.scene.fog = new THREE.Fog(0x111116, 50, 200);

                this.camera = new THREE.PerspectiveCamera(60, width / height, 0.1, 500);
                this.camera.position.set(128, 100, 180);
                this.camera.lookAt(128, 0, 128);

                this.renderer = new THREE.WebGLRenderer({ antialias: true });
                this.renderer.setSize(width, height);
                this.renderer.xr.enabled = true;
                container.appendChild(this.renderer.domElement);
                container.appendChild(VRButton.createButton(this.renderer));

                const controls = new OrbitControls(this.camera, this.renderer.domElement);
                controls.target.set(128, 0, 128);
                controls.update();

                const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
                this.scene.add(ambientLight);
                const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
                dirLight.position.set(0, 100, 50);
                this.scene.add(dirLight);

                const geometry = new THREE.PlaneGeometry(256, 256);
                geometry.rotateX(-Math.PI / 2);
                geometry.translate(128, 0, 128);

                const material = new THREE.MeshStandardMaterial({
                    color: 0x444444,
                    roughness: 0.8,
                    metalness: 0.2
                });
                this.mapPlane = new THREE.Mesh(geometry, material);
                this.scene.add(this.mapPlane);

                const gridHelper = new THREE.GridHelper(256, 16, 0x00d4ff, 0x333333);
                gridHelper.position.set(128, 0.1, 128);
                this.scene.add(gridHelper);

                this.renderer.domElement.addEventListener('click', (event) => {
                    const rect = this.renderer.domElement.getBoundingClientRect();
                    this.mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
                    this.mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;

                    this.raycaster.setFromCamera(this.mouse, this.camera);
                    const intersects = this.raycaster.intersectObjects([this.mapPlane, ...this.avatars]);

                    if (intersects.length > 0) {
                        const pt = intersects[0].point;
                        console.log("Teleporting to", pt);
                        this.teleportLocal(pt.x, pt.z, 25);
                    }
                });

                new ResizeObserver(() => {
                    const w = container.clientWidth;
                    const h = container.clientHeight;
                    if (w > 0 && h > 0) {
                        this.renderer.setSize(w, h);
                        this.camera.aspect = w / h;
                        this.camera.updateProjectionMatrix();
                    }
                }).observe(container);

                this.animateThree();
            },

            updateMapTexture(base64Data) {
                if (!this.scene || base64Data === this.lastMapData) return;
                this.lastMapData = base64Data;

                const image = new Image();
                image.src = "data:image/jpeg;base64," + base64Data;
                image.onload = () => {
                    const texture = new THREE.Texture(image);
                    texture.needsUpdate = true;
                    this.mapPlane.material.map = texture;
                    this.mapPlane.material.needsUpdate = true;
                    this.mapPlane.material.color.setHex(0xffffff);
                };
            },

            updateAvatars(nearbyList) {
                if (!this.scene) return;
                this.avatars.forEach(m => this.scene.remove(m));
                this.avatars = [];

                nearbyList.forEach(av => {
                    const geometry = new THREE.CapsuleGeometry(1, 2, 4, 8);
                    const material = new THREE.MeshStandardMaterial({ color: 0xff00ff, emissive: 0x440044 });
                    const mesh = new THREE.Mesh(geometry, material);
                    mesh.position.set(av.x, av.z/2 + 2, av.y);
                    mesh.userData = { x: av.x, y: av.y };
                    this.scene.add(mesh);
                    this.avatars.push(mesh);
                });
            },

            animateThree() {
                this.renderer.setAnimationLoop(() => {
                    this.renderer.render(this.scene, this.camera);
                });
            },

            drawRadar(avatars) {
                const canvas = document.getElementById('radar-canvas');
                const ctx = canvas.getContext('2d');
                canvas.width = canvas.parentElement.clientWidth;
                canvas.height = canvas.parentElement.clientHeight;
                const cx = canvas.width / 2;
                const cy = canvas.height / 2;

                ctx.fillStyle = '#000';
                ctx.fillRect(0,0, canvas.width, canvas.height);

                ctx.strokeStyle = '#003300';
                ctx.beginPath(); ctx.arc(cx, cy, 30, 0, 7); ctx.stroke();
                ctx.beginPath(); ctx.arc(cx, cy, 60, 0, 7); ctx.stroke();
                ctx.beginPath(); ctx.arc(cx, cy, 90, 0, 7); ctx.stroke();

                ctx.fillStyle = '#00ff00';
                ctx.beginPath(); ctx.arc(cx, cy, 3, 0, 7); ctx.fill();

                avatars.forEach(av => {
                    const px = (av.x / 256) * canvas.width;
                    const py = ((256-av.y) / 256) * canvas.height;

                    ctx.fillStyle = '#ff00ff';
                    ctx.beginPath(); ctx.arc(px, py, 4, 0, 7); ctx.fill();
                });
            },

            poll: async function() {
                try {
                    const res = await fetch('/api/poll');
                    const data = await res.json();

                    const term = document.getElementById('term-log');
                    const chat = document.getElementById('chat-history');

                    if (data.messages.length > this.msgCount) {
                        for (let i = this.msgCount; i < data.messages.length; i++) {
                            const m = data.messages[i];
                            if (['system', 'error', 'success'].includes(m.type)) {
                                const div = document.createElement('div');
                                div.className = 'log-line';
                                if(m.type === 'error') div.className += ' log-err';
                                if(m.type === 'success') div.className += ' log-suc';
                                if(m.type === 'system') div.className += ' log-sys';
                                div.innerText = `[${m.time}] ${m.text}`;
                                term.appendChild(div);
                                term.scrollTop = term.scrollHeight;
                            }
                            if (['chat', 'chat_own', 'im'].includes(m.type)) {
                                const div = document.createElement('div');
                                div.className = `msg ${m.type}`;
                                let content = `[${m.time}] ${m.text}`;
                                if(m.type === 'im' && m.meta && m.meta.id) {
                                    content += ` <span class="reply-link" onclick="app.setReply('${m.meta.id}')">[REPLY]</span>`;
                                }
                                div.innerHTML = content;
                                chat.appendChild(div);
                                chat.scrollTop = chat.scrollHeight;
                            }
                        }
                        this.msgCount = data.messages.length;
                    }

                    if (data.map) this.updateMapTexture(data.map);
                    if (data.nearby) this.updateAvatars(data.nearby);

                    if(data.region && data.region !== "Unknown") {
                        document.getElementById('map-info').innerText = "SECTOR: " + data.region;
                    }

                    this.drawRadar(data.nearby);

                    document.getElementById('stat-fps').innerText = data.stats.fps.toFixed(1);
                    document.getElementById('stat-dil').innerText = data.stats.dilation.toFixed(2);
                    document.getElementById('stat-pos').innerText = `<${data.stats.pos.x.toFixed(0)}, ${data.stats.pos.y.toFixed(0)}>`;

                } catch (e) { console.error(e); }
            }
        };

        window.onload = () => {
            window.app = app;
            window.wm = wm;

            let lines = document.querySelectorAll('.boot-line');
            let delay = 0;
            lines.forEach((line) => {
                setTimeout(() => line.style.opacity = 1, delay);
                delay += (Math.random() * 500) + 200;
            });
            setTimeout(() => {
                document.getElementById('boot-screen').style.display = 'none';
                document.getElementById('desktop').style.display = 'block';
                document.getElementById('taskbar').style.display = 'flex';
                wm.init();
                setTimeout(() => wm.focus('win-login'), 100);
                setTimeout(() => wm.focus('win-term'), 300);

                setInterval(() => {
                    document.getElementById('clock').innerText = new Date().toLocaleTimeString();
                }, 1000);
                setInterval(() => app.poll(), 500);
            }, delay + 800);
        };
    </script>
</body>
</html>
"""

class WebHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        if length > 0:
            body = json.loads(self.rfile.read(length))
        else:
            body = {}
            
        res = {"success": False}
        if self.path == '/api/login':
            res["success"] = client.login(body['first'], body['last'], body['pass'], body['start'])
        elif self.path == '/api/chat':
            client.send_chat(body['msg']); res["success"] = True
        elif self.path == '/api/teleport':
            if body.get('region') == 'local':
                client.teleport_local(body['x'], body['y'], body['z'])
            else:
                client.log(f"Teleporting to {body['region']}...", "system")
            res["success"] = True
        elif self.path == '/api/neural':
            active = client.neural.toggle()
            client.log(f"NEURAL AUTOPILOT {'ACTIVE' if active else 'DISENGAGED'}", "system")
            res["success"] = True
            
        self.send_response(200); self.send_header('Content-type', 'application/json'); self.end_headers()
        self.wfile.write(json.dumps(res).encode('utf-8'))

    def do_GET(self):
        if self.path == '/api/poll':
            self.send_response(200); self.send_header('Content-type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps(client.state.snapshot()).encode('utf-8'))
        else:
            self.send_response(200); self.send_header('Content-type', 'text/html'); self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode('utf-8'))
    
    def log_message(self, format, *args): return

if __name__ == "__main__":
    print("HYPER-CORE [DEEP-FIX V6] LOADED. PORT 8080")
    HTTPServer(('0.0.0.0', 8080), WebHandler).serve_forever()
