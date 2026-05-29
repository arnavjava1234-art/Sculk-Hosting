import os
import sys
import argparse
import asyncio
import threading
import time
import uvicorn

from sculk_hosting.jdk_manager import get_java_executable
from sculk_hosting.tunnel import CloudflareTunnel
from sculk_hosting.playit_manager import PlayitManager
from sculk_hosting.server import app, state, load_config, handle_playit_log

def sync_tunnel_url(tunnel: CloudflareTunnel):
    """
    Background thread to sync the Cloudflare tunnel public URL to the FastAPI state.
    """
    while True:
        if tunnel.public_url:
            state.tunnel_url = tunnel.public_url
        time.sleep(1)

def main():
    parser = argparse.ArgumentParser(
        description="Sculk Hosting: A premium, lightweight Minecraft server control panel for Kaggle notebooks."
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Local port to run the dashboard on (default: 8000)"
    )
    parser.add_argument(
        "--dir", 
        type=str, 
        default="./minecraft_server", 
        help="Directory to host the Minecraft server files in (default: ./minecraft_server)"
    )
    
    args = parser.parse_args()
    
    # 1. Resolve absolute paths
    mc_dir = os.path.abspath(args.dir)
    os.makedirs(mc_dir, exist_ok=True)
    
    runtime_dir = os.path.join(mc_dir, ".sculk_runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    
    # 2. Setup Globals
    state.mc_dir = mc_dir
    load_config()  # Loads existing configs (like RAM settings)
    
    print(f"[*] Starting Sculk Hosting Control Panel...")
    print(f"[*] Minecraft directory: {mc_dir}")
    print(f"[*] Runtime directory: {runtime_dir}")
    
    # 3. Download / Verify JDK 21
    try:
        java_path = get_java_executable(runtime_dir)
        state.java_path = java_path
    except Exception as e:
        print(f"[!] Error setting up JDK 21: {e}")
        sys.exit(1)
        
    # 4. Start Cloudflare Tunnel
    tunnel = CloudflareTunnel(runtime_dir, args.port)
    try:
        tunnel.start()
        # Start a daemon thread to keep updating the dashboard with the tunnel URL
        t = threading.Thread(target=sync_tunnel_url, args=(tunnel,), daemon=True)
        t.start()
    except Exception as e:
        print(f"[!] Warning: Could not initialize Cloudflare Tunnel: {e}")
        print("[*] Dashboard will only be accessible locally.")
        
    # 4.5 Start Playit.gg Tunnel Agent
    playit = PlayitManager(runtime_dir, state.playit_secret)
    state.playit_manager = playit
    playit.send_log_to_callbacks(handle_playit_log)
    try:
        playit.start()
    except Exception as e:
        print(f"[!] Warning: Could not initialize Playit.gg: {e}")

    # 5. Serve Frontend Static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    
    # We must dynamically import StaticFiles inside main to avoid import errors on mount
    # because FastAPI is configured above, and StaticFiles is imported here.
    
    # 6. Run Web Server
    try:
        uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
    except KeyboardInterrupt:
        print("\n[*] Exiting Sculk Hosting...")
    finally:
        # Cleanup
        tunnel.stop()
        playit.stop()
        if state.process:
            print("[*] Terminating Minecraft server process...")
            try:
                state.process.terminate()
            except Exception:
                pass

# Import StaticFiles helper to be run inside cli.py
from fastapi.staticfiles import StaticFiles

if __name__ == "__main__":
    main()
