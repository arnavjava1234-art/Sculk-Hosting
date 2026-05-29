import os
import sys
import shutil
import urllib.request
import subprocess
import threading
from typing import List, Callable

class PlayitManager:
    def __init__(self, runtime_dir: str, secret_key: str = ""):
        self.runtime_dir = runtime_dir
        self.secret_key = secret_key
        self.process = None
        self.logs: List[str] = []
        self.max_logs = 500
        self.log_callbacks: List[Callable[[str], None]] = []
        self.thread = None

        is_windows = sys.platform.startswith("win")
        if is_windows:
            self.binary_name = "playit.exe"
            self.download_url = "https://github.com/playit-cloud/playit-agent/releases/latest/download/playit-windows-amd64.exe"
        else:
            self.binary_name = "playit"
            self.download_url = "https://github.com/playit-cloud/playit-agent/releases/latest/download/playit-linux-amd64"

        self.binary_path = os.path.join(runtime_dir, self.binary_name)

    def download_if_missing(self):
        """Downloads the playit agent binary if missing."""
        if os.path.exists(self.binary_path):
            return

        os.makedirs(self.runtime_dir, exist_ok=True)
        print(f"[*] Downloading playit.gg tunnel agent...")
        print(f"[*] Source: {self.download_url}")

        try:
            req = urllib.request.Request(
                self.download_url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req) as response, open(self.binary_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)

            if not sys.platform.startswith("win"):
                os.chmod(self.binary_path, 0o755)

            print("[*] playit.gg agent downloaded successfully.")
        except Exception as e:
            print(f"[!] Failed to download playit: {e}")
            if os.path.exists(self.binary_path):
                os.remove(self.binary_path)
            raise e

    def start(self):
        """Starts playit process in a background thread."""
        self.download_if_missing()
        
        if self.secret_key:
            try:
                config_path = os.path.expanduser("~/.config/playit_gg/playit.toml")
                if sys.platform.startswith("win"):
                    config_path = os.path.expandvars(r"%LOCALAPPDATA%\playit\playit.toml")
                
                os.makedirs(os.path.dirname(config_path), exist_ok=True)
                with open(config_path, "w") as f:
                    f.write(f'secret_key = "{self.secret_key}"\n')
                print(f"[*] Pre-configured playit secret key at {config_path}")
            except Exception as e:
                print(f"[!] Warning: Could not write playit.toml: {e}")
                
        self.thread = threading.Thread(target=self._run_agent, daemon=True)
        self.thread.start()

    def _run_agent(self):
        cmd = [self.binary_path]
        if sys.platform.startswith("win"):
            # On windows, sometimes it opens a GUI or needs specific args, but agent CLI runs fine
            # We can run it in CLI mode or default
            pass
            
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=self.runtime_dir
        )

        for line in iter(self.process.stdout.readline, ''):
            if not line:
                break
            clean_line = line.strip()
            self._add_log(clean_line)

        self.process.wait()

    def _add_log(self, msg: str):
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_msg = ansi_escape.sub('', msg)
        self.logs.append(clean_msg)
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)
            
        # Fire callbacks
        for callback in self.log_callbacks:
            try:
                callback(clean_msg)
            except Exception:
                pass

    def send_log_to_callbacks(self, callback: Callable[[str], None]):
        self.log_callbacks.append(callback)

    def stop(self):
        """Stops the playit process."""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
            print("[*] playit.gg agent stopped.")
