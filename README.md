# Sculk Hosting 🌌

A premium, lightweight, zero-configuration Minecraft server control panel designed specifically for running servers inside **Google Colab**.

---

## 🚀 Quick Start on Google Colab

Copy and paste this single cell into your Google Colab Notebook to install **Sculk Hosting** and launch the control panel:

```python
# 1. Install Sculk Hosting directly from GitHub
!pip install git+https://github.com/arnavjava1234-art/Sculk-Hosting.git

# 2. Run the panel (it will auto-install JDK 21, set up a Cloudflare Tunnel, and start the dashboard)
!sculk
```

*Once executed, a **`trycloudflare.com`** URL will be printed in the output logs. Open it in your browser to access the control panel!*

---

## ✨ Features

- **Zero configuration**: Auto-downloads a portable **JDK 21** and **Cloudflare Tunnel** matching the Google Colab environment.
- **Dark "Sculk" Theme**: High-fidelity dark mode with glowing teal/purple accents using **Lucide icons**.
- **Real-time Console**: Live-streamed stdout logs and direct command input via WebSockets.
- **JVM RAM Slider**: Instantly adjust memory allocation from the UI.
- **Auto EULA**: Automatically accepts the Minecraft EULA on start.
- **File Manager**: Upload jar files (renames them automatically to `server.jar`), create directories, delete files, and edit configuration files (like `server.properties`) directly in the browser.

---

## 🛠️ Local Development & Testing

To install and run **Sculk Hosting** locally in development mode:

1. Clone the repository and navigate to the folder:
   ```bash
   cd Sculk-Hosting
   ```

2. Install the package in editable mode:
   ```bash
   pip install -e .
   ```

3. Run the CLI tool specifying a custom server directory:
   ```bash
   sculk --dir ./my_test_server
   ```
