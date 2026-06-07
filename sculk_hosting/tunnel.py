import os
import sys
import re
import shutil
import urllib.request
import subprocess
import threading
import time

class CloudflareTunnel:
    def __init__(self, runtime_dir: str, local_port: int):
        self.runtime_dir = runtime_dir
        self.local_port = local_port
        self.process = None
        self.public_url = None
        self.tunnel_thread = None
        
        is_windows = sys.platform.startswith("win")
        if is_windows:
            self.binary_name = "cloudflared.exe"
            self.download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        else:
            self.binary_name = "cloudflared"
            self.download_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
            
        self.binary_path = os.path.join(runtime_dir, self.binary_name)

    def download_if_missing(self):
        """Downloads cloudflared binary if it is not present in runtime_dir."""
        if os.path.exists(self.binary_path):
            return
            
        os.makedirs(self.runtime_dir, exist_ok=True)
        print(f"[*] Downloading cloudflared for tunnel exposure...")
        print(f"[*] Source: {self.download_url}")
        
        try:
            req = urllib.request.Request(
                self.download_url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(self.binary_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            # Chmod +x on Linux
            if not sys.platform.startswith("win"):
                os.chmod(self.binary_path, 0o755)
                
            print("[*] cloudflared downloaded successfully.")
        except Exception as e:
            print(f"[!] Failed to download cloudflared: {e}")
            if os.path.exists(self.binary_path):
                os.remove(self.binary_path)
            raise e

    def start(self):
        """Starts the Cloudflare tunnel in a background thread."""
        self.download_if_missing()
        
        # Start tunnel thread
        self.tunnel_thread = threading.Thread(target=self._run_tunnel, daemon=True)
        self.tunnel_thread.start()

    def _run_tunnel(self):
        cmd = [self.binary_path, "tunnel", "--protocol", "http2", "--url", f"http://127.0.0.1:{self.local_port}"]
        
        # We redirect stderr to stdout because cloudflared logs to stderr
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        
        # Regex to match the trycloudflare URL
        url_regex = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        
        for line in iter(self.process.stdout.readline, ''):
            if not line:
                break
            
            # Print cloudflared outputs to console for logging/debugging
            clean_line = line.strip()
            if "trycloudflare.com" in clean_line:
                match = url_regex.search(clean_line)
                if match:
                    self.public_url = match.group(0)
                    print(f"\n[+] CLOUDFLARE TUNNEL ESTABLISHED!")
                    print(f"[+] Access Sculk Hosting Dashboard at: {self.public_url}")
                    print(f"[+] ---------------------------------------------\n")
            
        self.process.wait()

    def stop(self):
        """Terminates the tunnel process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            print("[*] Cloudflare tunnel stopped.")
            self.process = None
            self.public_url = None
