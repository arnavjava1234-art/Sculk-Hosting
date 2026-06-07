import os
import sys
import json
import asyncio
import shutil
import psutil
from typing import List, Dict, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sculk_hosting.playit_manager import PlayitManager

app = FastAPI(title="Sculk Hosting Control Panel")

# Global State
class GlobalState:
    def __init__(self):
        self.mc_dir = None
        self.java_path = None
        self.process = None
        self.status = "stopped"  # "stopped", "starting", "running", "stopping"
        self.console_history: List[str] = []
        self.max_history = 1000
        self.active_websockets: List[WebSocket] = []
        self.tunnel_url = "http://localhost:8000"
        
        # Download state
        self.download_progress = 0
        self.download_status = "idle"  # "idle", "fetching", "downloading", "complete", "failed"
        self.download_error = ""
        
        # Playit.gg Manager state
        self.playit_manager: PlayitManager = None
        self.playit_websockets: List[WebSocket] = []
        
        # Default Configs
        self.min_ram = "1G"
        self.max_ram = "4G"
        self.playit_secret = ""

state = GlobalState()

# Helper: Load/Save Config
def get_config_path():
    return os.path.join(state.mc_dir, "sculk_config.json")

def load_config():
    config_path = get_config_path()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                state.min_ram = data.get("min_ram", "1G")
                state.max_ram = data.get("max_ram", "4G")
                state.playit_secret = data.get("playit_secret", "")
        except Exception as e:
            print(f"[!] Error loading config: {e}")

def save_config():
    config_path = get_config_path()
    try:
        with open(config_path, "w") as f:
            json.dump({
                "min_ram": state.min_ram,
                "max_ram": state.max_ram,
                "playit_secret": state.playit_secret
            }, f, indent=4)
    except Exception as e:
        print(f"[!] Error saving config: {e}")

# Helper: Auto EULA
def auto_accept_eula():
    eula_path = os.path.join(state.mc_dir, "eula.txt")
    try:
        with open(eula_path, "w") as f:
            f.write("eula=true\n")
        print("[*] Auto-accepted Minecraft EULA.")
    except Exception as e:
        print(f"[!] Warning: Could not write eula.txt: {e}")

# WebSocket Broadcast
async def broadcast_console(message: str):
    state.console_history.append(message)
    if len(state.console_history) > state.max_history:
        state.console_history.pop(0)
        
    disconnected = []
    for ws in state.active_websockets:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
            
    for ws in disconnected:
        if ws in state.active_websockets:
            state.active_websockets.remove(ws)

# Subprocess Output Reader
async def read_stream(stream, name):
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded_line = line.decode('utf-8', errors='replace').rstrip('\r\n')
        
        # Detect running state
        if "Done (" in decoded_line and state.status == "starting":
            state.status = "running"
            await broadcast_console("[Sculk Panel] Minecraft server successfully loaded and running.")
            
        await broadcast_console(decoded_line)

async def download_paper_jar() -> bool:
    server_jar = os.path.join(state.mc_dir, "server.jar")
    state.download_status = "fetching"
    state.download_progress = 0
    state.download_error = ""
    print("[*] server.jar not found. Fetching latest Paper 1.21.1 build details...")
    await broadcast_console("[Sculk Panel] server.jar not found. Fetching latest Paper 1.21.1 build details...")
    
    try:
        loop = asyncio.get_running_loop()
        
        def fetch_details():
            import requests
            res = requests.get("https://api.papermc.io/v2/projects/paper/versions/1.21.1", timeout=10)
            res.raise_for_status()
            return res.json()
            
        data = await loop.run_in_executor(None, fetch_details)
        latest_build = data["builds"][-1]
        download_url = f"https://api.papermc.io/v2/projects/paper/versions/1.21.1/builds/{latest_build}/downloads/paper-1.21.1-{latest_build}.jar"
    except Exception as e:
        print(f"[!] Failed to fetch build details: {e}. Using fallback Paper build 120.")
        await broadcast_console(f"[Sculk Panel] Failed to fetch build details: {e}. Using fallback Paper build 120.")
        download_url = "https://api.papermc.io/v2/projects/paper/versions/1.21.1/builds/120/downloads/paper-1.21.1-120.jar"
        
    print(f"[*] Downloading Paper 1.21.1 jar from: {download_url}")
    await broadcast_console(f"[Sculk Panel] Downloading Paper 1.21.1 jar from: {download_url}")
    
    try:
        def download_file():
            import requests
            state.download_status = "downloading"
            r = requests.get(download_url, stream=True, timeout=30)
            r.raise_for_status()
            total_length = r.headers.get('content-length')
            
            with open(server_jar, "wb") as f:
                if total_length is None:
                    f.write(r.content)
                    state.download_progress = 100
                else:
                    dl = 0
                    total_length = int(total_length)
                    for chunk in r.iter_content(chunk_size=8192):
                        dl += len(chunk)
                        f.write(chunk)
                        percent = int(dl * 100 / total_length)
                        state.download_progress = percent
        
        await loop.run_in_executor(None, download_file)
        state.download_status = "complete"
        state.download_progress = 100
        print("[*] Paper 1.21.1 downloaded and saved as server.jar successfully.")
        await broadcast_console("[Sculk Panel] Paper 1.21.1 downloaded and saved as server.jar successfully.")
        return True
    except Exception as e:
        state.download_status = "failed"
        state.download_error = str(e)
        print(f"[!] Failed to download Paper 1.21.1: {e}")
        await broadcast_console(f"[Sculk Panel ERROR] Failed to download Paper 1.21.1: {e}")
        if os.path.exists(server_jar):
            try:
                os.remove(server_jar)
            except Exception:
                pass
        return False

# Minecraft process lifecycle
async def run_minecraft_server():
    server_jar = os.path.join(state.mc_dir, "server.jar")
    if not os.path.exists(server_jar):
        state.status = "starting"
        success = await download_paper_jar()
        if not success:
            state.status = "stopped"
            return

    auto_accept_eula()
    
    # Build start command
    cmd = [
        state.java_path,
        f"-Xms{state.min_ram}",
        f"-Xmx{state.max_ram}",
        "-jar",
        "server.jar",
        "nogui"
    ]
    
    await broadcast_console(f"[Sculk Panel] Executing: {' '.join(cmd)}")
    state.status = "starting"
    
    try:
        state.process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=state.mc_dir,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Start reading stdout & stderr asynchronously
        stdout_task = asyncio.create_task(read_stream(state.process.stdout, "stdout"))
        stderr_task = asyncio.create_task(read_stream(state.process.stderr, "stderr"))
        
        # Wait for process to exit
        await state.process.wait()
        
        # Wait for streams to finish
        await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
        
    except Exception as e:
        await broadcast_console(f"[Sculk Panel ERROR] Subprocess error: {str(e)}")
    finally:
        state.status = "stopped"
        state.process = None
        await broadcast_console("[Sculk Panel] Minecraft server process terminated.")

# --- API ENDPOINTS ---

@app.get("/api/status")
async def get_status():
    # Gather CPU and RAM
    host_cpu = psutil.cpu_percent()
    host_ram = psutil.virtual_memory().percent
    
    mc_cpu = 0.0
    mc_ram = 0.0
    
    if state.process and state.process.returncode is None:
        try:
            p = psutil.Process(state.process.pid)
            mc_cpu = p.cpu_percent(interval=0.1)
            mc_ram = p.memory_info().rss / (1024 * 1024) # MB
        except Exception:
            pass

    # Check if server.jar exists
    jar_exists = os.path.exists(os.path.join(state.mc_dir, "server.jar"))

    return {
        "status": state.status,
        "tunnel_url": state.tunnel_url,
        "min_ram": state.min_ram,
        "max_ram": state.max_ram,
        "playit_secret": state.playit_secret,
        "jar_exists": jar_exists,
        "download": {
            "status": state.download_status,
            "progress": state.download_progress,
            "error": state.download_error
        },
        "metrics": {
            "host_cpu": host_cpu,
            "host_ram": host_ram,
            "mc_cpu": mc_cpu,
            "mc_ram": mc_ram
        }
    }

@app.post("/api/download/clear")
async def clear_download():
    state.download_status = "idle"
    state.download_progress = 0
    state.download_error = ""
    return {"message": "Download state cleared"}

class ConfigModel(BaseModel):
    min_ram: str
    max_ram: str
    playit_secret: str

@app.post("/api/config")
async def update_config(cfg: ConfigModel):
    old_secret = state.playit_secret
    state.min_ram = cfg.min_ram
    state.max_ram = cfg.max_ram
    state.playit_secret = cfg.playit_secret
    save_config()
    
    # Automatically restart Playit agent when secret changes
    if old_secret != cfg.playit_secret and state.playit_manager:
        state.playit_manager.secret_key = cfg.playit_secret
        state.playit_manager.stop()
        try:
            state.playit_manager.start()
        except Exception as e:
            print(f"[!] Failed to restart playit agent: {e}")
            
    return {"message": "Config updated successfully"}

@app.post("/api/control")
async def control_server(action: Dict[str, str]):
    act = action.get("action")
    if act == "start":
        if state.status != "stopped":
            raise HTTPException(status_code=400, detail="Server is already running or transitioning.")
        asyncio.create_task(run_minecraft_server())
        return {"message": "Server start initiated"}
        
    elif act == "stop":
        if state.status not in ["starting", "running"]:
            raise HTTPException(status_code=400, detail="Server is not running.")
        state.status = "stopping"
        if state.process and state.process.stdin:
            state.process.stdin.write(b"stop\n")
            await state.process.stdin.drain()
        return {"message": "Server stop command sent"}
        
    elif act == "restart":
        if state.status not in ["starting", "running"]:
            raise HTTPException(status_code=400, detail="Server is not running.")
        state.status = "stopping"
        if state.process and state.process.stdin:
            state.process.stdin.write(b"stop\n")
            await state.process.stdin.drain()
        
        # Poll till stopped, then start
        async def wait_and_restart():
            while state.status != "stopped":
                await asyncio.sleep(1)
            asyncio.create_task(run_minecraft_server())
            
        asyncio.create_task(wait_and_restart())
        return {"message": "Server restart scheduled"}
    
    raise HTTPException(status_code=400, detail="Invalid action")

# --- FILE MANAGER APIs ---

def is_text_file(filepath: str) -> bool:
    # Basic binary extensions to exclude from plain editing
    binary_extensions = {
        '.jar', '.zip', '.gz', '.tar', '.png', '.jpg', '.jpeg', '.gif',
        '.class', '.db', '.dat', '.mca', '.schematic', '.dll', '.so', '.exe'
    }
    _, ext = os.path.splitext(filepath.lower())
    if ext in binary_extensions:
        return False
    # If no binary extension, try reading first block to verify
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            return b'\x00' not in chunk
    except Exception:
        return False

@app.get("/api/files")
async def list_files(path: str = ""):
    # Prevent directory traversal
    target_path = os.path.normpath(os.path.join(state.mc_dir, path))
    if not target_path.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.exists(target_path):
        return []
        
    items = []
    try:
        for entry in os.scandir(target_path):
            # Skip hidden metadata / config files if we want cleaner UI, except .json/properties
            if entry.name.startswith(".") and entry.name != ".properties":
                continue
                
            rel_path = os.path.relpath(entry.path, state.mc_dir).replace("\\", "/")
            
            is_dir = entry.is_dir()
            size = entry.stat().st_size if not is_dir else 0
            
            items.append({
                "name": entry.name,
                "path": rel_path,
                "is_dir": is_dir,
                "size": size,
                "is_editable": not is_dir and is_text_file(entry.path)
            })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    # Sort: folders first, then files alphabetically
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return items

@app.get("/api/files/read")
async def read_file(path: str):
    target_path = os.path.normpath(os.path.join(state.mc_dir, path))
    if not target_path.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    if not os.path.exists(target_path) or os.path.isdir(target_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class WriteFileModel(BaseModel):
    path: str
    content: str

@app.post("/api/files/write")
async def write_file(data: WriteFileModel):
    target_path = os.path.normpath(os.path.join(state.mc_dir, data.path))
    if not target_path.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(data.content)
        return {"message": "File saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    path: str = Form("")
):
    # Determine destination dir
    dest_dir = os.path.normpath(os.path.join(state.mc_dir, path))
    if not dest_dir.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    os.makedirs(dest_dir, exist_ok=True)
    
    filename = file.filename
    # If it is a jar file, and no server.jar exists OR user uploads it, rename to server.jar
    # If the user uploads a jar directly to root folder, rename it to server.jar
    if filename.endswith(".jar") and path == "":
        filename = "server.jar"
        
    dest_file = os.path.join(dest_dir, filename)
    
    try:
        with open(dest_file, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"message": f"Uploaded {filename} successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/files/newfolder")
async def create_folder(data: Dict[str, str]):
    path = data.get("path", "")
    target_path = os.path.normpath(os.path.join(state.mc_dir, path))
    if not target_path.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    try:
        os.makedirs(target_path, exist_ok=True)
        return {"message": "Folder created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/files")
async def delete_file(path: str):
    target_path = os.path.normpath(os.path.join(state.mc_dir, path))
    if not target_path.startswith(state.mc_dir):
        raise HTTPException(status_code=403, detail="Access denied")
        
    try:
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)
        return {"message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- WEBSOCKET FOR CONSOLE STREAM ---

@app.websocket("/ws/console")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.active_websockets.append(websocket)
    
    # Send historical logs immediately so the user sees past activity
    for log in state.console_history:
        await websocket.send_text(log)
        
    try:
        while True:
            # Wait for client input commands
            data = await websocket.receive_text()
            if state.process and state.process.stdin:
                # Write command to Minecraft console
                cmd = data.strip() + "\n"
                state.process.stdin.write(cmd.encode())
                await state.process.stdin.drain()
                # Local echoing of command
                await broadcast_console(f"> {data}")
    except WebSocketDisconnect:
        if websocket in state.active_websockets:
            state.active_websockets.remove(websocket)
    except Exception as e:
        print(f"[!] WS Exception: {e}")
        if websocket in state.active_websockets:
            state.active_websockets.remove(websocket)

# --- WEBSOCKET FOR PLAYIT LOG STREAM ---

@app.websocket("/ws/playit")
async def playit_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.playit_websockets.append(websocket)
    
    # Send historical logs immediately
    if state.playit_manager:
        for log in state.playit_manager.logs:
            await websocket.send_text(log)
            
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in state.playit_websockets:
            state.playit_websockets.remove(websocket)
    except Exception as e:
        print(f"[!] Playit WS Exception: {e}")
        if websocket in state.playit_websockets:
            state.playit_websockets.remove(websocket)

def handle_playit_log(msg: str):
    """Callback to broadcast Playit logs to connected WebSockets in a thread-safe manner."""
    async def send():
        disconnected = []
        for ws in state.playit_websockets:
            try:
                await ws.send_text(msg)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            if ws in state.playit_websockets:
                state.playit_websockets.remove(ws)
                
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(send(), loop)
    except Exception:
        pass
