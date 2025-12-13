import tkinter as tk
from tkinter import scrolledtext, messagebox, simpledialog
import threading
import time
import sys
import struct
import socket
import uuid as __uuid__
import xmlrpc.client
import hashlib
import traceback
import random
import ssl
from uuid import UUID, getnode as get_mac

# ==========================================
# SECTION 1: CORE TYPES (llTypes.py)
# ==========================================
class null:
    def __bytes__(self):
        return b""
    def __str__(self):
        return "<NULL>"

class fixed:
    data = b""
    def __init__(self, data):
        if type(data) == bytes:
            self.data = data
        elif type(data) == str:
            # Improvement: Use latin-1 for protocol strings
            self.data = data.encode("latin-1")
        elif hasattr(data, "__bytes__"):
            self.data = bytes(data)
        else:
            self.data = type(data).encode("utf-8")
    def __bytes__(self):
        return self.data
    def __len__(self):
        return len(self.data)
    def __str__(self):
        try:
            return self.data.decode("latin-1") # Decoded with latin-1
        except:
            return "<FIXED: %i>"%len(self.data)

class variable:
    data = b""
    type = 0
    def __init__(self, ty = 1, data = b""):
        # Corrected for explicit bytes passing from sender (e.g., chat message with null-terminator)
        if type(data) == bytes:
            self.data = data
        elif type(data) == str:
            # Improvement: Use latin-1 for protocol strings, strip null terminator if present
            # The sender is responsible for adding the null terminator.
            self.data = data.encode("latin-1")
        elif hasattr(data, "__bytes__"):
            self.data = bytes(data)
        else:
            self.data = type(data).encode("utf-8")
        self.type = ty
        if ty == 1:
            if len(self.data) >= 255:
                # Should raise error or truncate
                pass 
        elif ty == 2:
            if len(self.data) >= 65535:
                # Should raise error or truncate
                pass
    def __bytes__(self):
        if self.type == 1:
            return struct.pack("<B", len(self.data)) + self.data
        elif self.type == 2:
            return struct.pack("<H", len(self.data)) + self.data
        return struct.pack("<B", len(self.data)) + self.data
    def __len__(self):
        return len(self.data)
    def __str__(self):
        try:
            return self.data.decode("latin-1") # Decoded with latin-1
        except:
            return "<VARIABLE %i: %i>"%(self.type,len(self.data))
    def __repr__(self):
        return "<VARIABLE %i: %i>"%(self.type,len(self.data))

class vector3:
    x = 0; y = 0; z = 0
    def __init__(self, x=0, y=0, z=0):
        self.x = x; self.y = y; self.z = z
    def __bytes__(self):
        return struct.pack("<fff", self.x, self.y, self.z)
    def __str__(self):
        return "<%f, %f, %f>"%(self.x, self.y, self.z)
    def __eq__(self, cmp):
        if type(cmp) != vector3: return False
        return self.x == cmp.x and self.y == cmp.y and self.z == cmp.z

class vector3d(vector3):
    def __bytes__(self):
        return struct.pack("<ddd", self.x, self.y, self.z)
    def __eq__(self, cmp):
        if type(cmp) != vector3d: return False
        return self.x == cmp.x and self.y == cmp.y and self.z == cmp.z

class vector4:
    x = 0; y = 0; z = 0; s = 0
    def __init__(self, x=0, y=0, z=0, s=0):
        self.x = x; self.y = y; self.z = z; self.s = s
    def __bytes__(self):
        return struct.pack("<ffff", self.x, self.y, self.z, self.s)
    def __str__(self):
        return "<%f, %f, %f, %f>"%(self.x, self.y, self.z, self.s)

class quaternion:
    x = 0; y = 0; z = 0; s = 0
    def __init__(self, s=0, x=0, y=0, z=0):
        self.s = s; self.x = x; self.y = y; self.z = z
    def __bytes__(self):
        return struct.pack("<ffff", self.s, self.x, self.y, self.z) # Corrected to 4 floats for quaternion
    def __str__(self):
        return "<%f, %f, %f, %f>"%(self.s, self.x, self.y, self.z)

rotation = quaternion

class color4U:
    r = 0; g = 0; b = 0; a = 0
    def __init__(self, r=0, g=0, b=0, a=0):
        self.r = r; self.g = g; self.b = b; self.a = a
    def __bytes__(self):
        return struct.pack("<BBBB", self.r, self.g, self.b, self.a)

class LLUUID:
    UUID = __uuid__.UUID("00000000-0000-0000-0000-000000000000")
    def __init__(self, key = "00000000-0000-0000-0000-000000000000"):
        if type(key) == bytes:
            if len(key) == 16:
                self.UUID = __uuid__.UUID(bytes=key)
        elif type(key) == str:
            self.UUID = __uuid__.UUID(key)
        elif isinstance(key, __uuid__.UUID):
            self.UUID = key
    def __bytes__(self):
        return self.UUID.bytes
    def __str__(self):
        return str(self.UUID)
    def __len__(self):
        return 16
    @property
    def bytes(self): 
        return self.UUID.bytes
    def __eq__(self, other):
        if not isinstance(other, LLUUID): return False
        return self.UUID == other.UUID

class IPAddr:
    addr = [0,0,0,0]
    def __init__(self, a=0,b=0,c=0,d=0):
        if type(a) == str:
            a = a.split(".")
            if len(a) == 4:
                b = int(a[1]); c = int(a[2]); d = int(a[3]); a = int(a[0])
        self.addr = [a,b,c,d]
    def __bytes__(self):
        return struct.pack("BBBB", self.addr[0], self.addr[1], self.addr[2], self.addr[3])
    def __str__(self):
        return "%i.%i.%i.%i"%(self.addr[0], self.addr[1], self.addr[2], self.addr[3])

class IPPort:
    port = 0
    def __init__(self, a=0):
        if type(a) == str: a = int(a)
        self.port = a
    def __bytes__(self):
        return struct.pack("<H", self.port)
    def __str__(self):
        return str(self.port)

def llDecodeType(t, ty = None):
    a = type(t)
    if a == null or a == fixed or a == variable or a == vector3 or \
        a == vector3d or a == vector4 or a == quaternion or a == LLUUID or \
        a == IPAddr or a == IPPort:
        return bytes(t)
    elif a == bytes:
        return t
    elif ty == "U8": return struct.pack("<B", t)
    elif ty == "U16": return struct.pack("<H", t)
    elif ty == "U32": return struct.pack("<I", t)
    elif ty == "U64": return struct.pack("<Q", t)
    elif ty == "S8": return struct.pack("<b", t)
    elif ty == "S16": return struct.pack("<h", t)
    elif ty == "S32": return struct.pack("<i", t)
    elif ty == "S64": return struct.pack("<q", t)
    elif ty == "F32": return struct.pack("<f", t)
    elif ty == "F64": return struct.pack("<d", t)
    elif ty == "BOOL" or t == bool: return struct.pack(">B", 1 if t == True else 0)
    return b""

def llEncodeType(t, ty = None, vlen = None):
    if ty == "Null": return null()
    # If t is already a Variable or Fixed object, this returns the object
    # If t is bytes, it creates the object from the bytes
    elif ty == "Fixed": return fixed(t)
    elif ty == "Variable": return variable(vlen, t) 
    elif ty == "U8": return struct.unpack("<B", t)[0]
    elif ty == "U16": return struct.unpack("<H", t)[0]
    elif ty == "U32": return struct.unpack("<I", t)[0]
    elif ty == "U64": return struct.unpack("<Q", t)[0]
    elif ty == "S8": return struct.unpack("<b", t)[0]
    elif ty == "S16": return struct.unpack("<h", t)[0]
    elif ty == "S32": return struct.unpack("<i", t)[0]
    elif ty == "S64": return struct.unpack("<q", t)[0]
    elif ty == "F32": return struct.unpack("<f", t)[0]
    elif ty == "F64": return struct.unpack("<d", t)[0]
    elif ty == "LLVector3":
        tmp = struct.unpack("<fff", t)
        return vector3(tmp[0],tmp[1],tmp[2])
    elif ty == "LLVector3d":
        tmp = struct.unpack("<ddd", t)
        return vector3d(tmp[0],tmp[1],tmp[2])
    elif ty == "LLVector4":
        tmp = struct.unpack("<ffff", t)
        return vector4(tmp[0],tmp[1],tmp[2],tmp[3])
    elif ty == "LLQuaternion":
        tmp = struct.unpack("<ffff", t) # Corrected to 4 floats
        return quaternion(tmp[0],tmp[1],tmp[2],tmp[3])
    elif ty == "IPAddr":
        tmp = struct.unpack("BBBB", t)
        return IPAddr(tmp[0],tmp[1],tmp[2],tmp[3])
    elif ty == "IPPort":
        return IPPort(struct.unpack("<H", t)[0])
    elif ty == "BOOL":
        return struct.unpack("B", t)[0] != 0
    elif ty == "LLUUID":
        return LLUUID(t)
    return t

# ==========================================
# SECTION 2: UTILITIES (zerocode, errorHandler, constraints)
# ==========================================

def zerocode_decode(bytedata):
    i = 0
    l = len(bytedata)
    while i < l:
        if bytedata[i] == 0:
            c = bytedata[i+1] - 1
            bytedata = bytedata[:i+1] + (b"\x00"*c) + bytedata[i+2:]
            i = i + c 
            l = l + c - 1
        i = i + 1
    return bytedata

def zerocode_encode(bytedata):
    i = 0
    l = len(bytedata)
    c = 0
    start = 0
    while i < l:
        if c > 253 or (bytedata[i] != 0 and c != 0):
            bytedata = bytedata[:start+1] + bytes((c,)) + bytedata[i:]
            i = i - c + 1
            l = l - c + 2
            c = 0
        elif bytedata[i] == 0:
            if c == 0:
                start = i
            c = c + 1
        i = i + 1
    if c != 0:
        bytedata = bytedata[:start+1] + bytes((c,)) + bytedata[i:]
    return bytedata

def printsafe(data):
    result = ""
    for i in data:
        if 0x20 <= i <= 0x7E:
            result = result + chr(i)
        else:
            result = result + "."
    return result

def hexdump(data):
    info = ""
    l = len(data)
    for i in range(0, l, 0x10):
        hexdump = ""
        for x in range(i, i+0x8 if i+0x8 <= l else l):
            hexdump = hexdump + "{0:02X} ".format(data[x])
        hexdump = hexdump + " "
        for x in range(i+0x8, i+0x10 if i+0x10 <= l else l):
            hexdump = hexdump + "{0:02X} ".format(data[x])
        info = info + "{0:04X}     {1: <49s}     {2:s}\n".format(i, hexdump, printsafe(data[i:i+0x10]))
    return info

def packetErrorTrace(data):
    a = traceback.format_exc()
    if not a: return "Error: No error"
    try:
        flags, seq, exlen = struct.unpack_from(">BIB", data, 0)
        mid = struct.unpack_from(">I", data, 6+exlen)[0]
        return "%s\nMID:%s\n%s"%(a, mid, ("-"*79)+"\n"+hexdump(data)+"\n"+("-"*79))
    except:
        return "%s\n%s"%(a, ("-"*79)+"\n"+hexdump(data)+"\n"+("-"*79))


class Constraints:
    def __init__(self):
        # Only essential ones for this script's functionality are defined here for brevity
        self.CHAT_NORMAL = 1
        self.AGENT_CONTROL_AT_POS = 1
        self.AGENT_CONTROL_AT_NEG = 2
        # Full list from constraints.py would go here...

const = Constraints()

# ==========================================
# SECTION 3: AUTHENTICATION
# ==========================================

def getMacAddress():
    mac = get_mac()
    return ':'.join(("%012X" % mac)[i:i+2] for i in range(0, 12, 2))

__PLATFORM_STRING__ = "Win"
if sys.platform == "linux": __PLATFORM_STRING__ = "Lnx"
elif sys.platform == "darwin": __PLATFORM_STRING__ = "Mac"

# This is the correct, default login URI from the pyverse authentication.py file
LOGIN_URI = "https://login.agni.lindenlab.com/cgi-bin/login.cgi" 

def login_to_simulator(firstname, lastname, password, mac=None, start="last", grid=None):
    if grid is None: grid = LOGIN_URI
    if mac == None: mac = getMacAddress()
    
    # Use default SSL context for verification
    proxy = xmlrpc.client.ServerProxy(grid, verbose=False, use_datetime=True)
    
    # NOTE: The original pyverse code used CZ_Python channel, adjusting to SLViewer_Py as per the original SLViewer.py
    result = proxy.login_to_simulator({
        "first": firstname,
        "last": lastname,
        "passwd": "$1$"+hashlib.md5(password.encode("latin")).hexdigest(),
        "start": start, # This is the critical parameter
        "channel": "SLViewer_Py", 
        "version": "Python "+sys.version,
        "platform": __PLATFORM_STRING__,
        "mac": mac,
        "id0": hashlib.md5(("%s:%s:%s"%(__PLATFORM_STRING__,mac,sys.version)).encode("latin")).hexdigest(),
        "agree_to_tos": True,
        "last_exec_event": 0,
        "options": ["inventory-root", "buddy-list", "login-flags", "global-textures"]
    })
    if result["login"] != "true":
        raise ConnectionError("Unable to log in:\n    %s"%(result["message"] if "message" in result else "Unknown error"))
    return result

# ==========================================
# SECTION 4: MESSAGE DEFINITIONS (message.py & messages.py)
# ==========================================

baseTypes = {
    "Null": null(), "Fixed": fixed(b""), "Variable": [None, variable(1, b""), variable(2, b"")],
    "U8": 0, "U16": 0, "U32": 0, "U64": 0, "S8": 0, "S16": 0, "S32": 0, "S64": 0, "F32": 0.0, "F64": 0.0,
    "LLVector3": vector3(), "LLVector3d": vector3d(), "LLVector4": vector4(),
    "LLQuaternion": quaternion(), "LLUUID": LLUUID(), "BOOL": False,
    "IPADDR": IPAddr(), "IPPORT": IPPort()
}
typeLengths = {
    "Null": 0, "Fixed": 0, "Variable": 0, "Color4U": 4, "U8": 1, "U16": 2, "U32": 4, "U64": 8,
    "S8": 1, "S16": 2, "S32": 4, "S64": 8, "F32": 4, "F64": 8,
    "LLVector3": 12, "LLVector3d": 24, "LLVector4": 16, "LLQuaternion": 16,
    "LLUUID": 16, "BOOL": 1, "IPADDR": 4, "IPPORT": 2
}

class BaseMessage:
    name = "TestMessage"; id = 1; freq = 2; trusted = False; zero_coded = True
    blocks = []; structure = {}
    def __init__(self, data=None):
        if not data:
            for key in self.blocks:
                if key[1] == 1: # Single block
                    tmp = {}
                    for value in self.structure[key[0]]:
                        if value[1] == "Variable": tmp[value[0]] = baseTypes[value[1]][value[2]]
                        else: tmp[value[0]] = baseTypes[value[1]]
                    setattr(self, key[0], tmp)
                else: # Multi block (Variable or Fixed count)
                    setattr(self, key[0], [])
        else:
            self.load(data)
    
    def load(self, data):
        offset = 0
        for key in self.blocks:
            if key[1] == 1:
                tmp = {}
                for value in self.structure[key[0]]:
                    tlen = 0
                    if value[1] == "Variable":
                        if value[2] == 1:
                            tlen = struct.unpack_from("<B", data, offset)[0]; offset += 1
                        elif value[2] == 2:
                            tlen = struct.unpack_from("<H", data, offset)[0]; offset += 2
                    elif value[1] == "Fixed": tlen = value[2]
                    else: tlen = typeLengths[value[1]]
                    
                    val_data = data[offset:offset+tlen]
                    tmp[value[0]] = llEncodeType(val_data, value[1], value[2] if value[1]=="Variable" else None)
                    offset += tlen
                setattr(self, key[0], tmp)
            else: # Variable count blocks (key[1] == 0) or Fixed count blocks (key[1] > 1)
                count = key[1]
                if count == 0: # Variable count (always U8)
                    count = struct.unpack_from(">B", data, offset)[0]; offset += 1
                
                outblock = []
                for i in range(count):
                    tmp = {}
                    for value in self.structure[key[0]]:
                        tlen = 0
                        if value[1] == "Variable":
                            if value[2] == 1:
                                tlen = struct.unpack_from("<B", data, offset)[0]; offset += 1
                            elif value[2] == 2:
                                tlen = struct.unpack_from("<H", data, offset)[0]; offset += 2
                        elif value[1] == "Fixed": tlen = value[2]
                        else: tlen = typeLengths[value[1]]
                        
                        val_data = data[offset:offset+tlen]
                        tmp[value[0]] = llEncodeType(val_data, value[1], value[2] if value[1]=="Variable" else None)
                        offset += tlen
                    outblock.append(tmp)
                setattr(self, key[0], outblock)

    def __bytes__(self):
        result = b""
        for key in self.blocks:
            if key[1] == 1:
                tmp = getattr(self, key[0])
                for value in self.structure[key[0]]:
                    result += llDecodeType(tmp[value[0]], value[1])
            else:
                tmp = getattr(self, key[0])
                if key[1] == 0: result += struct.pack("B", len(tmp))
                for item in tmp:
                    for value in self.structure[key[0]]:
                        result += llDecodeType(item[value[0]], value[1])
        return result

message_lookup = {}
def registerMessage(msg):
    id = msg.id
    if msg.freq == 1: id = id + 0xFF00
    elif msg.freq == 2: id = id + 0xFFFF0000
    message_lookup[id] = msg
    message_lookup[msg.name.lower()] = msg

def getMessageByID(key, data = None):
    if key in message_lookup: return message_lookup[key](data=data)
    else: return None

def getMessageByName(key, data = None):
    key = key.lower()
    if key in message_lookup: return message_lookup[key](data=data)
    else: return None

# --- ESSENTIAL MESSAGES FOR CHAT/LOGIN/TELEPORT ---

class UseCircuitCode(BaseMessage):
    name = "UseCircuitCode"; id = 3; freq = 2; trusted = False; zero_coded = False
    blocks = [("CircuitCode", 1)]
    structure = {"CircuitCode": [("Code", "U32"), ("SessionID", "LLUUID"), ("ID", "LLUUID")]}
registerMessage(UseCircuitCode)

class CompleteAgentMovement(BaseMessage):
    name = "CompleteAgentMovement"; id = 249; freq = 2; trusted = False; zero_coded = False
    blocks = [("AgentData", 1)]
    structure = {"AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID"), ("CircuitCode", "U32")]}
registerMessage(CompleteAgentMovement)

class RegionHandshake(BaseMessage):
    name = "RegionHandshake"; id = 148; freq = 2; trusted = True; zero_coded = True
    blocks = [("RegionInfo", 1), ("RegionInfo2", 1), ("RegionInfo3", 1), ("RegionInfo4", 0)]
    structure = {
        "RegionInfo": [("RegionFlags", "U32"), ("SimAccess", "U8"), ("SimName", "Variable", 1), ("SimOwner", "LLUUID"), ("IsEstateManager", "BOOL"), ("WaterHeight", "F32"), ("BillableFactor", "F32"), ("CacheID", "LLUUID"), ("TerrainBase0", "LLUUID"), ("TerrainBase1", "LLUUID"), ("TerrainBase2", "LLUUID"), ("TerrainBase3", "LLUUID"), ("TerrainDetail0", "LLUUID"), ("TerrainDetail1", "LLUUID"), ("TerrainDetail2", "LLUUID"), ("TerrainDetail3", "LLUUID"), ("TerrainStartHeight00", "F32"), ("TerrainStartHeight01", "F32"), ("TerrainStartHeight10", "F32"), ("TerrainStartHeight11", "F32"), ("TerrainHeightRange00", "F32"), ("TerrainHeightRange01", "F32"), ("TerrainHeightRange10", "F32"), ("TerrainHeightRange11", "F32")],
        "RegionInfo2": [("RegionID", "LLUUID")],
        "RegionInfo3": [("CPUClassID", "S32"), ("CPURatio", "S32"), ("ColoName", "Variable", 1), ("ProductSKU", "Variable", 1), ("ProductName", "Variable", 1)],
        "RegionInfo4": [("RegionFlagsExtended", "U64"), ("RegionProtocols", "U64")]
    }
registerMessage(RegionHandshake)

class RegionHandshakeReply(BaseMessage):
    name = "RegionHandshakeReply"; id = 149; freq = 2; trusted = False; zero_coded = True
    blocks = [("AgentData", 1), ("RegionInfo", 1)]
    structure = {
        "AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID")],
        "RegionInfo": [("Flags", "U32")]
    }
registerMessage(RegionHandshakeReply)

class ChatFromSimulator(BaseMessage):
    name = "ChatFromSimulator"; id = 139; freq = 2; trusted = True; zero_coded = False
    blocks = [("ChatData", 1)]
    structure = {"ChatData": [("FromName", "Variable", 1), ("SourceID", "LLUUID"), ("OwnerID", "LLUUID"), ("SourceType", "U8"), ("ChatType", "U8"), ("Audible", "U8"), ("Position", "LLVector3"), ("Message", "Variable", 2)]}
registerMessage(ChatFromSimulator)

class ChatFromViewer(BaseMessage):
    name = "ChatFromViewer"; id = 80; freq = 2; trusted = False; zero_coded = True
    blocks = [("AgentData", 1), ("ChatData", 1)]
    structure = {
        "AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID")],
        "ChatData": [("Message", "Variable", 2), ("Type", "U8"), ("Channel", "S32")]
    }
registerMessage(ChatFromViewer)

class AgentThrottle(BaseMessage):
    name = "AgentThrottle"; id = 81; freq = 2; trusted = False; zero_coded = True
    blocks = [("AgentData", 1), ("Throttle", 1)]
    structure = {
        "AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID"), ("CircuitCode", "U32")],
        "Throttle": [("GenCounter", "U32"), ("Throttles", "Variable", 1)]
    }
registerMessage(AgentThrottle)

class AgentFOV(BaseMessage):
    name = "AgentFOV"; id = 82; freq = 2; trusted = False; zero_coded = False
    blocks = [("AgentData", 1), ("FOVBlock", 1)]
    structure = {
        "AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID"), ("CircuitCode", "U32")],
        "FOVBlock": [("GenCounter", "U32"), ("VerticalAngle", "F32")]
    }
registerMessage(AgentFOV)

class AgentHeightWidth(BaseMessage):
    name = "AgentHeightWidth"; id = 83; freq = 2; trusted = False; zero_coded = False
    blocks = [("AgentData", 1), ("HeightWidthBlock", 1)]
    structure = {
        "AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID"), ("CircuitCode", "U32")],
        "HeightWidthBlock": [("GenCounter", "U32"), ("Height", "U16"), ("Width", "U16")]
    }
registerMessage(AgentHeightWidth)

class AgentUpdate(BaseMessage):
    name = "AgentUpdate"; id = 4; freq = 0; trusted = False; zero_coded = True
    blocks = [("AgentData", 1)]
    structure = {"AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID"), ("BodyRotation", "LLQuaternion"), ("HeadRotation", "LLQuaternion"), ("State", "U8"), ("CameraCenter", "LLVector3"), ("CameraAtAxis", "LLVector3"), ("CameraLeftAxis", "LLVector3"), ("CameraUpAxis", "LLVector3"), ("Far", "F32"), ("ControlFlags", "U32"), ("Flags", "U8")]}
registerMessage(AgentUpdate)

class PacketAck(BaseMessage):
    name = "PacketAck"; id = 4294967291; freq = 3; trusted = False; zero_coded = False
    blocks = [("Packets", 0)]
    structure = {"Packets": [("ID", "U32")]}
registerMessage(PacketAck)

class StartPingCheck(BaseMessage):
    name = "StartPingCheck"; id = 1; freq = 0; trusted = False; zero_coded = False
    blocks = [("PingID", 1)]
    structure = {"PingID": [("PingID", "U8"), ("OldestUnacked", "U32")]}
registerMessage(StartPingCheck)

class CompletePingCheck(BaseMessage):
    name = "CompletePingCheck"; id = 2; freq = 0; trusted = False; zero_coded = False
    blocks = [("PingID", 1)]
    structure = {"PingID": [("PingID", "U8")]}
registerMessage(CompletePingCheck)

class LogoutRequest(BaseMessage):
    name = "LogoutRequest"; id = 252; freq = 2; trusted = False; zero_coded = False
    blocks = [("AgentData", 1)]
    structure = {"AgentData": [("AgentID", "LLUUID"), ("SessionID", "LLUUID")]}
registerMessage(LogoutRequest)

class TeleportFinish(BaseMessage):
    name = "TeleportFinish"; id = 69; freq = 2; trusted = True; zero_coded = False
    blocks = [("Info", 1)]
    structure = {"Info": [("AgentID", "LLUUID"), ("LocationID", "U32"), ("SimIP", "IPADDR"), ("SimPort", "IPPORT"), ("RegionHandle", "U64"), ("SeedCapability", "Variable", 2), ("SimAccess", "U8"), ("TeleportFlags", "U32")]}
registerMessage(TeleportFinish)

class CloseCircuit(BaseMessage):
    name = "CloseCircuit"; id = 4294967293; freq = 3; trusted = False; zero_coded = False
    blocks = []
    structure = {}
registerMessage(CloseCircuit)

# ==========================================
# SECTION 5: PACKET HANDLING (packet.py)
# ==========================================

class Packet:
    bytes = b""; body = None; MID = 0; sequence = 0; extra = b""
    acks = []; flags = 0; zero_coded = 0; reliable = 0; resent = 0; ack = True
    
    def __init__(self, data=None, message=None, mid=0, sequence=0, zero_coded=0, reliable=0, resent=0, ack=0, acks=[]):
        if data:
            self.flags, self.sequence, self.extra_bytes = struct.unpack_from(">BiB", data[:6])
            self.zero_coded = (self.flags&0x80 == 0x80)
            self.reliable = (self.flags&0x40 == 0x40)
            self.resent = (self.flags&0x20 == 0x20)
            self.ack = (self.flags&0x10 == 0x10)
            self.extra = data[6:6+self.extra_bytes]
            
            payload = data[6+self.extra_bytes:]
            if self.zero_coded: self.bytes = zerocode_decode(payload)
            else: self.bytes = payload
                
            offset = 1 # Start past the MID in body

            # Determine MID, Frequency, and Real ID
            try:
                mid_raw = struct.unpack_from(">I", self.bytes, 0)[0]
            except struct.error:
                # Malformed packet body
                return

            realID = mid_raw
            offset = 4
            if mid_raw & 0xFFFFFFFA == 0xFFFFFFFA: # Fixed-frequency packet (3) - CloseCircuit, PacketAck etc.
                self.MID = mid_raw
            elif mid_raw & 0xFFFF0000 == 0xFFFF0000: # High-frequency packet (2) - Most normal packets
                self.MID = mid_raw & 0x0000FFFF
                realID = self.MID + 0xFFFF0000
            elif mid_raw & 0xFF000000 == 0xFF000000: # Medium-frequency packet (1) - Not common
                self.MID = (mid_raw >> 16) & 0xFF
                realID = self.MID + 0xFF00
                offset = 2
            else: # Low-frequency packet (0) - PingCheck, AgentUpdate
                self.MID = (mid_raw >> 24) & 0xFF
                realID = self.MID
                offset = 1
            
            self.body = getMessageByID(realID, self.bytes[offset:])
            if not self.body: 
                self.body = type('UnknownMessage', (object,), {'name': 'Unknown'})()

            if self.ack:
                try:
                    ackcount = data[len(data)-1]
                    ack_offset = len(data) - (ackcount * 4) - 1
                    for i in range(ackcount):
                        self.acks.append(struct.unpack_from(">I", data, ack_offset)[0])
                        ack_offset += 4
                except: 
                    pass # Handle malformed ACK data
        elif message:
            self.MID = message.id
            if len(acks) > 0 or ack: self.ack = True
            self.zero_coded = message.zero_coded
            self.sequence = sequence
            self.body = message
            self.acks = acks
            self.reliable = getattr(message, 'reliable', False) # Set reliable from message metadata
            if reliable: self.reliable = True # Override if explicitly set as reliable
            if resent: self.resent = True

    def __bytes__(self):
        self.flags = 0
        body = bytes(self.body)
        
        # 1. Zero-coding
        if self.zero_coded:
            tmp = zerocode_encode(body)
            if len(tmp) >= len(body):
                self.zero_coded = False; self.flags &= ~0x80 # Don't zero-code if it makes it larger
            else:
                self.flags |= 0x80
                body = tmp
        
        # 2. Set Flags
        if self.reliable: self.flags |= 0x40
        if self.resent: self.flags |= 0x20
        if self.ack: self.flags |= 0x10
        
        # 3. ACK bytes
        acks_bytes = b""
        if self.ack:
            for i in self.acks: acks_bytes += struct.pack(">I", i)
            acks_bytes += struct.pack(">b", len(self.acks))
        
        # 4. Message ID (MID)
        result = b""
        if self.body.freq == 3: result = struct.pack(">I", self.MID)
        elif self.body.freq == 2: result = struct.pack(">I", self.MID + 0xFFFF0000)
        elif self.body.freq == 1: result = struct.pack(">H", self.MID + 0xFF00)
        elif self.body.freq == 0: result = struct.pack(">B", self.MID)
        
        # 5. Full Packet Assembly
        return struct.pack(">BiB", self.flags, self.sequence, len(self.extra)) + self.extra + result + body + acks_bytes

# ==========================================
# SECTION 6: NETWORK LAYER (UDPStream.py as RegionClient)
# ==========================================

class RegionClient:
    host = ""; port = 0; clientPort = 0; sock = None
    agent_id = None; session_id = None; loginToken = {}
    nextPing = 0; nextAck = 0; nextAgentUpdate = 0
    sequence = 1; acks = []
    circuit_code = None; debug = False
    controls = 0; controls_once = 0
    sim = {}
    
    # --- New variables for Handshake Retries ---
    handshake_complete = False
    last_circuit_send = 0 
    last_update_send = 0
    circuit_packet = None 
    circuit_sequence = 0 
    
    # NEW: Tracking for CompleteAgentMovement (CAM)
    cam_packet = None
    last_cam_send = 0
    cam_sequence = 0

    def __init__(self, loginToken, host="0.0.0.0", port=0, debug=False):
        self.debug = debug
        if loginToken.get("login") != "true":
            raise ConnectionError("Unable to log into simulator: %s" % loginToken.get("message", "Unknown"))
        
        self.loginToken = loginToken
        self.host = loginToken["sim_ip"]
        self.port = loginToken["sim_port"]
        self.session_id = LLUUID(loginToken["session_id"])
        self.agent_id = LLUUID(loginToken["agent_id"])
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self.sock.settimeout(1.0)
        # Using 0.0.0.0 allows listening on all interfaces
        self.sock.bind((host, port))
        
        # The circuit_code from login token is a string (e.g., "1234567"), need to pack the integer value
        self.circuit_code = int(loginToken["circuit_code"])
        
        self.last_circuit_send = 0 # Forces an immediate send on first loop iteration

    @property
    def seq(self):
        self.sequence += 1
        return self.sequence - 1
    
    def send_use_circuit_code(self):
        # *** FIX: Store and reuse the packet and sequence number ***
        if self.circuit_packet is None:
            # First time: generate and store the packet
            msg = getMessageByName("UseCircuitCode")
            msg.CircuitCode["Code"] = self.circuit_code
            msg.CircuitCode["SessionID"] = self.session_id
            msg.CircuitCode["ID"] = self.agent_id
            
            self.circuit_sequence = self.seq 
            # The use of ack=False is important here to ensure no acks are piggybacked on the first packet.
            self.circuit_packet = Packet(sequence=self.circuit_sequence, message=msg, reliable=True, ack=False)
        
        # Resend the stored packet (with the original sequence number)
        self.send(self.circuit_packet)
        self.last_circuit_send = time.time()

    def send_complete_movement(self):
        # *** NEW: Store and reuse the CAM packet and sequence number ***
        if self.cam_packet is None:
            # First time: generate and store the packet
            msg = getMessageByName("CompleteAgentMovement")
            msg.AgentData["AgentID"] = self.agent_id
            msg.AgentData["SessionID"] = self.session_id
            msg.AgentData["CircuitCode"] = self.circuit_code
            
            self.cam_sequence = self.seq 
            self.cam_packet = Packet(sequence=self.cam_sequence, message=msg, reliable=True, ack=False)
        
        # Resend the stored packet (with the original sequence number)
        self.send(self.cam_packet)
        self.last_cam_send = time.time()

    def handleInternalPackets(self, pck):
        if not hasattr(pck.body, 'name'): return

        if pck.body.name == "StartPingCheck":
            msg = getMessageByName("CompletePingCheck")
            msg.PingID["PingID"] = pck.body.PingID["PingID"]
            self.send(msg)
            
        elif pck.body.name == "RegionHandshake":
            self.handshake_complete = True # Signal that Handshake is done!
            self.sim['name'] = str(pck.body.RegionInfo["SimName"])
            
            # Send the ACK for the UseCircuitCode packet. This is implied by the successful handshake.
            # The UseCircuitCode packet's sequence number is self.circuit_sequence.
            self.acks.append(self.circuit_sequence) 
            self.circuit_packet = None # No longer need to resend the circuit code
            self.cam_packet = None # ADDED: Clear CAM state

            msg = getMessageByName("RegionHandshakeReply")
            msg.AgentData["AgentID"] = self.agent_id
            msg.AgentData["SessionID"] = self.session_id
            msg.RegionInfo["Flags"] = 0
            self.send(msg)
            
            self.throttle()
            self.setFOV()
            self.setWindowSize()

        if pck.reliable:
            self.acks.append(pck.sequence)
        
        # Only run network maintenance if handshake is still incomplete
        if not self.handshake_complete:
            if time.time() > self.nextAck: self.sendAcks()

    def recv(self):
        try:
            blob = self.sock.recv(65507)
            try: pck = Packet(data=blob)
            except Exception as e: 
                if self.debug: print(f"Packet deserialization error: {e}")
                if self.debug: print(packetErrorTrace(blob))
                return None
            self.handleInternalPackets(pck)
            return pck
        except socket.timeout:
            return None
        except Exception as e:
            if self.debug: print(f"Socket error: {e}")
            return None

    def send(self, blob):
        if type(blob) is not Packet:
            # If a Message object is passed, wrap it in a non-reliable Packet (default)
            # Piggyback any accumulated ACKs on this packet
            blob = Packet(sequence=self.seq, message=blob, acks=self.acks[:255])
            self.acks = self.acks[255:]
            self.nextAck = time.time() + 1
        try:
            # If blob is a Packet (like self.circuit_packet or self.cam_packet), it is sent as-is.
            self.sock.sendto(bytes(blob), (self.host, self.port))
            return True
        except Exception as e: 
            if self.debug: print(f"Send error: {e}")
            return False

    def logout(self):
        msg = getMessageByName("LogoutRequest")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        self.send(msg)

    def sendAcks(self):
        if len(self.acks) > 0:
            msg = getMessageByName("PacketAck")
            tmp = self.acks[:255]
            self.acks = self.acks[255:]
            msg.Packets = [{"ID": i} for i in tmp]
            self.send(msg)
            self.nextAck = time.time() + 1

    def throttle(self):
        msg = getMessageByName("AgentThrottle")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.AgentData["CircuitCode"] = self.circuit_code
        msg.Throttle["GenCounter"] = 0
        # 7 floats: Resend, Land, Wind, Cloud, Task, Texture, Asset
        floats = struct.pack("<fffffff", 150000.0, 170000.0, 34000.0, 34000.0, 446000.0, 446000.0, 220000.0)
        msg.Throttle["Throttles"] = variable(1, floats)
        self.send(msg)

    def setFOV(self):
        msg = getMessageByName("AgentFOV")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.AgentData["CircuitCode"] = self.circuit_code
        msg.FOVBlock["GenCounter"] = 0
        msg.FOVBlock["VerticalAngle"] = 6.28
        self.send(msg)

    def setWindowSize(self):
        msg = getMessageByName("AgentHeightWidth")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.AgentData["CircuitCode"] = self.circuit_code
        msg.HeightWidthBlock["GenCounter"] = 0
        msg.HeightWidthBlock["Height"] = 768
        msg.HeightWidthBlock["Width"] = 1024
        self.send(msg)
    
    # MODIFIED: Added reliable=False to the signature
    def agentUpdate(self, controls=0, reliable=False): 
        msg = getMessageByName("AgentUpdate")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.AgentData["BodyRotation"] = quaternion(1.0, 0.0, 0.0, 0.0)
        msg.AgentData["HeadRotation"] = quaternion(1.0, 0.0, 0.0, 0.0)
        msg.AgentData["State"] = 0
        msg.AgentData["CameraCenter"] = vector3(128,128,0)
        msg.AgentData["CameraAtAxis"] = vector3(0,1,0)
        msg.AgentData["CameraLeftAxis"] = vector3(1,0,0)
        msg.AgentData["CameraUpAxis"] = vector3(0,0,1)
        msg.AgentData["Far"] = 1024.0
        msg.AgentData["ControlFlags"] = controls
        msg.AgentData["Flags"] = 0
        
        # We send the message object, letting self.send handle sequence and ACKs
        self.send(msg)
        self.last_update_send = time.time()
        
    def teleport_to_region(self, region_name):
        # Placeholder for complex teleport logic
        print(f"Teleport to {region_name} requested via packet system (Not fully implemented in this stub).")

# ==========================================
# SECTION 7: MAIN APPLICATION (SLviewer.py)
# ==========================================

# --- Core Second Life Agent Class ---
class SecondLifeAgent:
    """Manages the connection and interaction with the Second Life grid."""
    def __init__(self, ui_callback, debug_callback):
        self.client = None 
        self.ui_callback = ui_callback 
        self.debug_callback = debug_callback 
        self.running = False
        self.event_thread = None
        self.current_region_name = ""
        self.current_position = ""
        
        # Connection credentials
        self.agent_id = None
        self.session_id = None
        self.circuit_code = None
        self.sim_ip = None
        self.sim_port = None
        self.raw_socket = None
        self.first_name = "" 
        self.connection_start_time = 0 

    def log(self, message):
        """Helper to send logs to the UI thread."""
        if self.debug_callback:
            self.debug_callback(message)

    def _event_handler(self):
        """Runs in a separate thread to constantly check for new grid events."""
        self.log("DEBUG: Event handler thread started. Waiting for packets...")
        
        while self.running and self.client:
            
            current_time = time.time()
            if not self.client.handshake_complete:
                
                # 1. Resend UseCircuitCode (Aggressively: every 1.0s)
                if current_time - self.client.last_circuit_send > 1.0: 
                    self.log("DEBUG: Resending UseCircuitCode...")
                    self.client.send_use_circuit_code()
                    
                # NEW: 2. Resend CompleteAgentMovement (Aggressively: every 1.0s)
                if current_time - self.client.last_cam_send > 1.0: 
                    self.log("DEBUG: Resending CompleteAgentMovement...")
                    self.client.send_complete_movement()
                
                # 3. Send AgentUpdate (UNRELIABLE and slightly slower during handshake)
                is_reliable = False # Fixed to False
                if current_time - self.client.last_update_send > 0.5: # Fixed to 0.5s
                    self.log(f"DEBUG: Sending AgentUpdate to poke the sim (Reliable: {is_reliable})...")
                    self.client.agentUpdate(controls=self.client.controls_once|self.client.controls, reliable=is_reliable) 
                    self.client.controls_once = 0
            
            # This handles receiving packets
            packet = self.client.recv()

            if packet:
                # Safe packet name extraction
                packet_name = 'Unknown'
                if hasattr(packet, 'body') and hasattr(packet.body, 'name'):
                    packet_name = packet.body.name
                
                self.log(f"RX Packet: {packet_name}")

                # Handle Login/Handshake
                if packet_name == "RegionHandshake":
                    if hasattr(packet.body, 'RegionInfo'):
                        # Using str() on the fixed/variable type automatically calls __str__ which decodes with latin-1 (in the improved version)
                        self.current_region_name = str(packet.body.RegionInfo.get('SimName', 'Connected Region')) 
                    self.current_position = "Landed"
                    self.ui_callback("status", f"🟢 Successfully logged in to {self.current_region_name}!")
                    self.log(f"DEBUG: Login confirmed via {packet_name}.")
                    
                    # Send movement packet to finish the handshake dance (The RegionClient already clears self.cam_packet and self.circuit_packet on RegionHandshake)
                    time.sleep(0.1) 
                    self.send_complete_movement_raw()
                    
                    # FINAL COMPLETIONIST STEP: Send a reliable AgentUpdate to complete the dance
                    time.sleep(0.1) 
                    self.client.agentUpdate(controls=self.client.controls_once|self.client.controls, reliable=True)


                # Handle Chat
                elif packet_name == "ChatFromSimulator":
                    chat_data = getattr(packet.body, 'ChatData', None)
                         
                    if chat_data:
                        # IMPROVED DECODING LOGIC: rely on the llEncodeType returning an object with a .data attribute
                        def safe_decode_llvariable(ll_var):
                            # The variable object has a 'data' attribute holding the byte content.
                            # Standard SL chat uses Latin-1/ISO-8859-1. Strip the null terminator.
                            if hasattr(ll_var, 'data'):
                                try:
                                    # Use latin-1 decoding and strip null bytes
                                    return ll_var.data.decode('latin-1').rstrip('\x00')
                                except:
                                    # Fallback if latin-1 fails
                                    return ll_var.data.decode('utf-8', 'ignore').rstrip('\x00')
                            return str(ll_var)

                        raw_name = chat_data.get('FromName', 'Unknown')
                        raw_message = chat_data.get('Message', '')
                        
                        from_name = safe_decode_llvariable(raw_name)
                        msg_text = safe_decode_llvariable(raw_message)
                        
                        self.ui_callback("chat", f"[{from_name}]: {msg_text}")
                
                elif packet_name == "TeleportFinish":
                    self.ui_callback("status", "🚀 Teleport finished!")

                elif packet_name == "CloseCircuit":
                    self.ui_callback("status", "👋 Disconnected from the grid.")
                    self.log("DEBUG: CloseCircuit received.")
                    self.running = False
                    break
            
            # Send periodic ACKs and AgentUpdates even if no packets received
            if self.client and current_time - self.client.nextAck > 1.0:
                self.client.sendAcks()
            if self.client and self.client.handshake_complete and current_time - self.client.last_update_send > 0.5:
                # Send non-reliable AgentUpdate once handshake is complete
                self.client.agentUpdate(controls=self.client.controls_once|self.client.controls, reliable=False) 
                self.client.controls_once = 0

            time.sleep(0.005) # Yield to prevent spinning

    # --- MANUAL PACKET CONSTRUCTION (Wrappers around PyVerse classes) ---
    def get_socket(self):
        if self.client: return self.client.sock
        return None

    def send_raw_packet(self, packet_obj):
        if self.client:
            return self.client.send(packet_obj)
        return False
    
    def send_complete_movement_raw(self):
        # NOTE: This is called *after* RegionHandshake to confirm the landing, 
        # NOT the handshake retry version which is in RegionClient.send_complete_movement()
        self.log("DEBUG: Building CompleteAgentMovement packet...")
        msg = getMessageByName("CompleteAgentMovement")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.AgentData["CircuitCode"] = self.circuit_code
        self.send_raw_packet(msg)

    def send_chat_raw(self, message, channel=0, chat_type=1): 
        """Builds and sends ChatFromViewer."""
        self.log(f"DEBUG: Sending Chat: '{message[:15]}...'")
        
        # IMPROVEMENT: Use explicit Latin-1 encoding with null termination
        encoded_message = (message + "\x00").encode('latin-1') 
        
        msg = getMessageByName("ChatFromViewer")
        msg.AgentData["AgentID"] = self.agent_id
        msg.AgentData["SessionID"] = self.session_id
        msg.ChatData["Message"] = variable(2, encoded_message) # Pass the byte string directly.
        msg.ChatData["Type"] = chat_type
        msg.ChatData["Channel"] = channel
        
        return self.send_raw_packet(msg)

    def teleport_to_region(self, region_name):
        # Placeholder for complex teleport logic
        print(f"Teleport to {region_name} requested via packet system (Not fully implemented in this stub).")

    def login(self, first, last, password, region_name):
        self.ui_callback("status", "🌐 Connecting to the Second Life Grid...")
        # NOTE: Logging the exact URI that will be sent to the server for debugging
        self.log(f"DEBUG: Starting login process for {first} {last} @ {region_name}")
        
        try:
            self.log("DEBUG: Requesting XML-RPC login token...")
            # Use the corrected 'region_name' format passed from the UI logic
            login_token = login_to_simulator(first, last, password, start=region_name)

            if login_token.get("login") != "true":
                 message = login_token.get("message", "Unknown login error")
                 self.log(f"DEBUG: Login failed. Server response: {message}")
                 raise ConnectionError(message)
            
            self.log("DEBUG: HTTP Login successful! Token received.")
            
            self.circuit_code = int(login_token['circuit_code'])
            self.agent_id = UUID(login_token['agent_id'])
            self.session_id = UUID(login_token['session_id'])
            self.sim_ip = login_token.get('sim_ip')
            self.sim_port = int(login_token.get('sim_port'))
            self.first_name = first 

            self.log(f"DEBUG: Sim: {self.sim_ip}:{self.sim_port} | Circuit: {self.circuit_code}")

            self.log("DEBUG: Initializing UDP Stream...")
            # The RegionClient automatically initializes retry logic on init
            self.client = RegionClient(login_token, debug=self.debug_callback is not None)
            
            self.raw_socket = self.get_socket()
            self.log(f"DEBUG: Socket acquisition status: {'Success' if self.raw_socket else 'Failed'}")

            self.connection_start_time = time.time() # NEW: Record start time
            self.running = True
            self.event_thread = threading.Thread(target=self._event_handler, daemon=True)
            self.event_thread.start()
            
            self.ui_callback("status", "Logging in to the starting region...")
            return True
                
        except Exception as e:
            self.ui_callback("error", f"❌ Connection Error: {e}")
            self.log(f"ERROR: Login crashed: {e}")
            self.stop()
            return False

    def send_chat(self, message):
        if self.client and self.running:
            return self.send_chat_raw(message)
        return False
        
    def teleport(self, region_name):
        if self.client and self.running:
            self.ui_callback("status", f"Requesting teleport to {region_name}...")
            self.client.teleport_to_region(region_name)
            
    def stop(self):
        self.log("DEBUG: Stopping client...")
        self.running = False
        if self.client:
            try:
                self.client.logout() 
            except:
                pass 
        if self.event_thread and self.event_thread.is_alive():
            try:
                self.event_thread.join(1)
            except: pass

# --- GUI Implementation using Tkinter ---

class ChatWindow(tk.Toplevel):
    def __init__(self, master, sl_agent, first, last):
        super().__init__(master)
        self.master.withdraw() 
        self.title(f"Second Life Chat Viewer - {first} {last}")
        self.geometry("700x600")
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.sl_agent = sl_agent
        self.my_first_name = first
        self.my_last_name = last
        self._create_widgets()

    def _create_widgets(self):
        menu_bar = tk.Menu(self)
        self.config(menu=menu_bar)
        actions_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="Actions", menu=actions_menu)
        actions_menu.add_command(label="Teleport...", command=self.do_teleport)
        actions_menu.add_separator()
        actions_menu.add_command(label="Logout & Exit", command=self.on_closing)
        
        self.chat_display = scrolledtext.ScrolledText(self, state='disabled', wrap=tk.WORD, height=15, bg='#1C1C1C', fg='#FFFFFF', font=('Courier', 10))
        self.chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.status_bar = tk.Label(self, text="Connected", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        input_frame = tk.Frame(self)
        input_frame.pack(padx=10, pady=(0, 10), fill=tk.X)
        self.message_entry = tk.Entry(input_frame, font=('Helvetica', 12))
        self.message_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.message_entry.bind("<Return>", self.send_message_event)
        send_button = tk.Button(input_frame, text="Send", command=self.send_message)
        send_button.pack(side=tk.RIGHT)

    def update_ui(self, update_type, message):
        """Thread-safe update of the GUI."""
        if update_type == "chat":
            self.chat_display.config(state='normal')
            self.chat_display.insert(tk.END, message + "\n")
            self.chat_display.config(state='disabled')
            self.chat_display.see(tk.END) 
        elif update_type == "status":
            self.status_bar.config(text=message)
        elif update_type == "error":
            messagebox.showerror("Agent Error", message)
            self.status_bar.config(text=f"Error: {message}", fg="red")
            
    def send_message_event(self, event):
        self.send_message()
        return "break"

    def send_message(self):
        message = self.message_entry.get().strip()
        if not message:
            return
        self.update_ui("chat", f"[{self.my_first_name} {self.my_last_name}]: {message}") 
        self.sl_agent.send_chat(message)
        self.message_entry.delete(0, tk.END)

    def do_teleport(self):
        region_name = simpledialog.askstring("Teleport", "Enter the name of the region to teleport to:", parent=self)
        if region_name:
            # Re-apply the formatting logic for the teleport
            if region_name.lower() == "home" or "/" not in region_name:
                formatted_name = region_name
            else:
                 # Ensure it uses the correct URI format for logging in/teleporting if a full URI is entered
                formatted_name = f"uri:{region_name.split('/')[0]}&128&128&30" 
            self.sl_agent.teleport(formatted_name.strip())

    def on_closing(self):
        if messagebox.askyesno("Quit", "Are you sure you want to log out and exit?"):
            self.sl_agent.stop()
            self.destroy()
            self.master.destroy()


class LoginWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Second Life Login (Standalone)")
        self.geometry("500x500") 
        self.resizable(True, True)
        self.sl_agent = SecondLifeAgent(self.handle_agent_update, self.handle_debug_log)
        self.eval('tk::PlaceWindow . center')
        self._create_widgets()

    def _create_widgets(self):
        main_frame = tk.Frame(self, padx=10, pady=10)
        main_frame.pack(fill=tk.X)
        
        tk.Label(main_frame, text="First Name:", anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        self.first_name_entry = tk.Entry(main_frame, width=25)
        self.first_name_entry.grid(row=0, column=1, pady=2)
        
        tk.Label(main_frame, text="Last Name:", anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        self.last_name_entry = tk.Entry(main_frame, width=25)
        self.last_name_entry.grid(row=1, column=1, pady=2)
        
        tk.Label(main_frame, text="Password:", anchor='w').grid(row=2, column=0, sticky='w', pady=2)
        self.password_entry = tk.Entry(main_frame, show='*', width=25)
        self.password_entry.grid(row=2, column=1, pady=2)

        tk.Label(main_frame, text="Start Region:", anchor='w').grid(row=3, column=0, sticky='w', pady=2)
        self.region_entry = tk.Entry(main_frame, width=25)
        self.region_entry.insert(0, "Ahern") 
        self.region_entry.grid(row=3, column=1, pady=2)
        
        self.login_button = tk.Button(main_frame, text="Login", command=self.start_login_thread, width=15)
        self.login_button.grid(row=4, column=0, columnspan=2, pady=10)
        
        self.status_label = tk.Label(main_frame, text="Enter credentials and click Login.", fg="grey")
        self.status_label.grid(row=5, column=0, columnspan=2, pady=5)

        log_frame = tk.Frame(self, padx=10, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(log_frame, text="Debug Log (Packet activity):", anchor="w").pack(fill=tk.X)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', font=("Courier", 8))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        tk.Button(log_frame, text="Copy Log", command=self.copy_log).pack(pady=5)

    def copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log_text.get("1.0", tk.END))
        messagebox.showinfo("Copied", "Log copied to clipboard!")

    def handle_debug_log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.config(state='disabled')
        self.log_text.see(tk.END)

    def handle_agent_update(self, update_type, message):
        # The UI update needs to be scheduled to run on the main thread
        self.after(0, self._process_agent_update, update_type, message)
        
    def _process_agent_update(self, update_type, message):
        if update_type == "status":
            self.status_label.config(text=message, fg="blue")
            if "Successfully logged in" in message:
                first = self.first_name_entry.get().strip()
                last = self.last_name_entry.get().strip()
                ChatWindow(self, self.sl_agent, first, last)
            elif "Connection Error" in message:
                self.login_button.config(state=tk.NORMAL, text="Login")
        elif update_type == "error":
            messagebox.showerror("Login Error", message)
            self.status_label.config(text=f"Error: {message}", fg="red")
            self.login_button.config(state=tk.NORMAL, text="Login")
            
    def login_task(self, first, last, password, region_name):
        success = self.sl_agent.login(first, last, password, region_name)
        if not success:
            self.after(100, lambda: self.login_button.config(state=tk.NORMAL, text="Login"))

    def start_login_thread(self):
        first = self.first_name_entry.get().strip()
        last = self.last_name_entry.get().strip()
        password = self.password_entry.get()
        raw_region_name = self.region_entry.get().strip() 
        
        if raw_region_name.lower() == "home":
             formatted_region_name = "home"
        else:
             # FIX FOR 500 SERVER ERROR: Use '&' instead of '/' for the XML-RPC URI format
             formatted_region_name = f"uri:{raw_region_name}&128&128&30" 
        
        if not first or not last or not password:
            self.status_label.config(text="All fields are required.", fg="red")
            return

        self.login_button.config(state=tk.DISABLED, text="Connecting...")
        self.status_label.config(text="Attempting login...", fg="black")
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        
        login_thread = threading.Thread(target=self.login_task, args=(first, last, password, formatted_region_name), daemon=True)
        login_thread.start()

if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()