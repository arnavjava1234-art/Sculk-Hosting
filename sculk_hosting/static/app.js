// State Management
const appState = {
    currentTab: 'overview',
    serverStatus: 'stopped',
    currentPath: '',
    editingFilePath: '',
    ws: null,
    pollInterval: null,
    wsReconnectTimeout: null
};

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    setupTabNavigation();
    setupStatusPolling();
    setupWebSocket();
    setupControlButtons();
    setupRamConfigSync();
    setupFileManager();
    setupPlayitWebSocket();
    
    // Initial load
    refreshStatus();
    loadFiles();
    
    // Create initial Lucide icons
    lucide.createIcons();
});

// 1. Tab Navigation
function setupTabNavigation() {
    const navItems = document.querySelectorAll('.nav-item');
    const tabContents = document.querySelectorAll('.tab-content');
    
    const tabMeta = {
        overview: { title: 'Dashboard Overview', subtitle: 'Monitor and control your remote Minecraft server.' },
        console: { title: 'Server Console', subtitle: 'Direct terminal access to Minecraft stdout and stdin.' },
        files: { title: 'File Manager', subtitle: 'Browse, edit, upload, and manage your server files.' },
        join: { title: 'Playit.gg Tunnel Integration', subtitle: 'Expose your server port directly to the internet without port forwarding.' }
    };

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const tabId = item.getAttribute('data-tab');
            appState.currentTab = tabId;

            // Nav state
            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            // View state
            tabContents.forEach(content => {
                content.classList.remove('active');
                if (content.id === `tab-${tabId}`) {
                    content.classList.add('active');
                }
            });

            // Header labels
            document.getElementById('page-title').textContent = tabMeta[tabId].title;
            document.getElementById('page-subtitle').textContent = tabMeta[tabId].subtitle;
            
            if (tabId === 'files') {
                loadFiles();
            } else if (tabId === 'console') {
                scrollToBottom();
            } else if (tabId === 'join') {
                const output = document.getElementById('playit-output');
                if (output) output.scrollTop = output.scrollHeight;
            }
        });
    });
}

// 2. Status Polling
function setupStatusPolling() {
    refreshStatus();
    appState.pollInterval = setInterval(refreshStatus, 3000);
}

async function refreshStatus() {
    try {
        const res = await fetch('/api/status');
        if (!res.ok) throw new Error("Status API failed");
        
        const data = await res.json();
        
        // Update status state
        appState.serverStatus = data.status;
        
        // Update Badges & indicators
        updateStatusUI(data.status);
        
        // Update Tunnel URL
        const tunnelLink = document.getElementById('tunnel-link');
        const tunnelBadge = document.getElementById('tunnel-badge-container');
        if (data.tunnel_url && data.tunnel_url !== "http://localhost:8000") {
            tunnelLink.textContent = data.tunnel_url;
            tunnelBadge.style.display = 'flex';
        } else {
            tunnelLink.textContent = "Offline / Local Only";
            tunnelBadge.style.display = 'none';
        }
        
        // Update Missing Jar Alert
        const missingAlert = document.getElementById('missing-jar-alert');
        if (!data.jar_exists) {
            missingAlert.classList.remove('hidden');
        } else {
            missingAlert.classList.add('hidden');
        }
        
        // Update Download Progress Modal
        const dlModal = document.getElementById('download-modal');
        const dlTitle = document.getElementById('download-modal-title');
        const dlStatus = document.getElementById('download-modal-status-text');
        const dlBar = document.getElementById('download-modal-progress-bar');
        const dlIconContainer = document.getElementById('download-modal-icon-container');
        const dlPercent = document.getElementById('download-modal-percentage');
        const dlCloseBtn = document.getElementById('download-modal-close-btn');
        
        if (!appState.isClearingDownload) {
            if (data.download && data.download.status !== 'idle') {
                dlModal.classList.add('open');
                
                let iconName = 'download-cloud';
                let iconClass = 'download-card-icon';
                
                if (data.download.status === 'fetching') {
                    dlTitle.textContent = 'Preparing Server Jar...';
                    dlStatus.textContent = 'Querying PaperMC API for build details...';
                    dlBar.style.width = '10%';
                    dlPercent.textContent = '10%';
                    iconName = 'download-cloud';
                    iconClass = 'download-card-icon';
                    dlCloseBtn.classList.add('hidden');
                    appState.downloadCompleteTriggered = false;
                } else if (data.download.status === 'downloading') {
                    dlTitle.textContent = 'Downloading Paper 1.21.1...';
                    dlStatus.textContent = 'Downloading server executable...';
                    dlBar.style.width = `${data.download.progress}%`;
                    dlPercent.textContent = `${data.download.progress}%`;
                    iconName = 'download-cloud';
                    iconClass = 'download-card-icon';
                    dlCloseBtn.classList.add('hidden');
                    appState.downloadCompleteTriggered = false;
                } else if (data.download.status === 'complete') {
                    dlTitle.textContent = 'Ready!';
                    dlStatus.textContent = 'Paper 1.21.1 installed successfully. Starting server...';
                    dlBar.style.width = '100%';
                    dlPercent.textContent = '100%';
                    iconName = 'check-circle-2';
                    iconClass = 'download-card-icon success';
                    dlCloseBtn.classList.add('hidden');
                    
                    if (!appState.downloadCompleteTriggered) {
                        appState.downloadCompleteTriggered = true;
                        appState.isClearingDownload = true;
                        setTimeout(async () => {
                            dlModal.classList.remove('open');
                            await fetch('/api/download/clear', { method: 'POST' });
                            appState.downloadCompleteTriggered = false;
                            appState.isClearingDownload = false;
                            refreshStatus();
                        }, 3000);
                    }
                } else if (data.download.status === 'failed') {
                    dlTitle.textContent = 'Installation Failed';
                    dlStatus.textContent = `Error: ${data.download.error}`;
                    dlBar.style.width = '0%';
                    dlPercent.textContent = '0%';
                    iconName = 'alert-triangle';
                    iconClass = 'download-card-icon error';
                    dlCloseBtn.classList.remove('hidden');
                }
                
                if (dlIconContainer) {
                    dlIconContainer.innerHTML = `<i data-lucide="${iconName}" class="${iconClass}"></i>`;
                }
                lucide.createIcons();
            } else {
                dlModal.classList.remove('open');
            }
        }
        
        // Update Metrics
        document.getElementById('mc-cpu-value').textContent = `${data.metrics.mc_cpu.toFixed(1)}%`;
        document.getElementById('mc-cpu-bar').style.width = `${Math.min(100, data.metrics.mc_cpu)}%`;
        
        document.getElementById('mc-ram-value').textContent = `${data.metrics.mc_ram.toFixed(0)} MB`;
        
        document.getElementById('host-cpu-value').textContent = `${data.metrics.host_cpu.toFixed(1)}%`;
        document.getElementById('host-cpu-bar').style.width = `${data.metrics.host_cpu}%`;
        
        document.getElementById('host-ram-value').textContent = `${data.metrics.host_ram.toFixed(1)}%`;
        document.getElementById('host-ram-bar').style.width = `${data.metrics.host_ram}%`;

        // Update JVM Ram values if not focused
        const minText = document.getElementById('min-ram-text');
        const maxText = document.getElementById('max-ram-text');
        const minSlider = document.getElementById('min-ram-slider');
        const maxSlider = document.getElementById('max-ram-slider');
        
        if (document.activeElement !== minText && document.activeElement !== minSlider) {
            minText.value = data.min_ram;
            minSlider.value = parseInt(data.min_ram) || 1;
        }
        if (document.activeElement !== maxText && document.activeElement !== maxSlider) {
            maxText.value = data.max_ram;
            maxSlider.value = parseInt(data.max_ram) || 4;
        }
        
        const playitSecret = document.getElementById('playit-secret-input');
        if (playitSecret && document.activeElement !== playitSecret) {
            playitSecret.value = data.playit_secret || '';
        }
        
    } catch (err) {
        console.error("Error fetching status:", err);
        updateStatusUI('offline');
    }
}

function updateStatusUI(status) {
    const sidebarDot = document.getElementById('sidebar-status-dot');
    const sidebarText = document.getElementById('sidebar-status-text');
    const overviewBadge = document.getElementById('overview-status-badge');
    
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const restartBtn = document.getElementById('restart-btn');
    const consoleInput = document.getElementById('console-input');
    const sendCmdBtn = document.getElementById('send-cmd-btn');

    // Remove old classes
    const classes = ['stopped', 'starting', 'running', 'stopping', 'offline'];
    classes.forEach(c => {
        sidebarDot.classList.remove(c);
        overviewBadge.classList.remove(c);
    });

    sidebarDot.classList.add(status);
    overviewBadge.classList.add(status);
    
    sidebarText.textContent = status.toUpperCase();
    overviewBadge.textContent = status.toUpperCase();
    
    // Button controls based on state
    if (status === 'stopped') {
        startBtn.disabled = false;
        stopBtn.disabled = true;
        restartBtn.disabled = true;
        consoleInput.disabled = true;
        sendCmdBtn.disabled = true;
    } else if (status === 'running') {
        startBtn.disabled = true;
        stopBtn.disabled = false;
        restartBtn.disabled = false;
        consoleInput.disabled = false;
        sendCmdBtn.disabled = false;
    } else if (status === 'starting' || status === 'stopping') {
        startBtn.disabled = true;
        stopBtn.disabled = true;
        restartBtn.disabled = true;
        consoleInput.disabled = false;  // Allow command entries during start/stop
        sendCmdBtn.disabled = false;
    } else { // offline / error
        startBtn.disabled = true;
        stopBtn.disabled = true;
        restartBtn.disabled = true;
        consoleInput.disabled = true;
        sendCmdBtn.disabled = true;
    }
}

// 3. Control Buttons Handlers
function setupControlButtons() {
    const startBtn = document.getElementById('start-btn');
    const stopBtn = document.getElementById('stop-btn');
    const restartBtn = document.getElementById('restart-btn');
    const copyBtn = document.getElementById('copy-tunnel-btn');
    
    startBtn.addEventListener('click', () => controlServer('start'));
    stopBtn.addEventListener('click', () => controlServer('stop'));
    restartBtn.addEventListener('click', () => controlServer('restart'));
    
    copyBtn.addEventListener('click', () => {
        const link = document.getElementById('tunnel-link').textContent;
        if (link && link !== "Exposing..." && link !== "Offline / Local Only") {
            navigator.clipboard.writeText(link)
                .then(() => {
                    const originalHTML = copyBtn.innerHTML;
                    copyBtn.innerHTML = '<i data-lucide="check" style="color:var(--success)"></i>';
                    lucide.createIcons();
                    setTimeout(() => {
                        copyBtn.innerHTML = originalHTML;
                        lucide.createIcons();
                    }, 1500);
                });
        }
    });

    // Auto setup button
    const autoDownloadBtn = document.getElementById('auto-download-btn');
    if (autoDownloadBtn) {
        autoDownloadBtn.addEventListener('click', () => {
            controlServer('start');
        });
    }

    // Download modal close
    const dlCloseBtn = document.getElementById('download-modal-close-btn');
    if (dlCloseBtn) {
        dlCloseBtn.addEventListener('click', async () => {
            document.getElementById('download-modal').classList.remove('open');
            await fetch('/api/download/clear', { method: 'POST' });
            refreshStatus();
        });
    }

    // Jar upload alert button
    document.getElementById('trigger-jar-upload').addEventListener('click', () => {
        document.getElementById('jar-upload-native').click();
    });
    
    document.getElementById('jar-upload-native').addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            uploadSingleFile(e.target.files[0], "");
        }
    });
}

async function controlServer(action) {
    try {
        const res = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const data = await res.json();
        refreshStatus();
    } catch (err) {
        console.error("Control API failed:", err);
    }
}

// 4. WebSocket Console
function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/console`;
    
    appState.ws = new WebSocket(wsUrl);
    
    const output = document.getElementById('console-output');
    const input = document.getElementById('console-input');
    const sendBtn = document.getElementById('send-cmd-btn');
    
    appState.ws.onopen = () => {
        appendLog("[Sculk Panel] Console stream connected.", "system-log");
        if (appState.wsReconnectTimeout) {
            clearTimeout(appState.wsReconnectTimeout);
            appState.wsReconnectTimeout = null;
        }
    };
    
    appState.ws.onmessage = (event) => {
        appendLog(event.data);
    };
    
    appState.ws.onclose = () => {
        appendLog("[Sculk Panel] Console stream disconnected. Reconnecting in 5s...", "system-log");
        // Disable controls
        input.disabled = true;
        sendBtn.disabled = true;
        
        // Reconnect loop
        appState.wsReconnectTimeout = setTimeout(setupWebSocket, 5000);
    };

    appState.ws.onerror = (err) => {
        console.error("WebSocket error:", err);
    };

    // Input handlers
    const sendCommand = () => {
        const cmd = input.value.trim();
        if (cmd && appState.ws && appState.ws.readyState === WebSocket.OPEN) {
            appState.ws.send(cmd);
            input.value = '';
        }
    };

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendCommand();
    });
    
    sendBtn.addEventListener('click', sendCommand);
}

function appendLog(line, className = "") {
    const output = document.getElementById('console-output');
    const row = document.createElement('div');
    if (className) {
        row.className = className;
    }
    
    // Quick simple formatting for standard MC logs
    if (line.includes("[INFO]")) {
        row.style.color = "#ffffff";
    } else if (line.includes("[WARN]")) {
        row.style.color = "#fbbf24";
    } else if (line.includes("[ERROR]")) {
        row.style.color = "#ef4444";
    } else if (line.startsWith("> ")) {
        row.style.color = "var(--accent)";
        row.style.fontWeight = "bold";
    }
    
    row.textContent = line;
    output.appendChild(row);
    
    // Cap log lines inside browser to avoid lag
    if (output.childNodes.length > 1000) {
        output.removeChild(output.firstChild);
    }
    
    scrollToBottom();
}

function scrollToBottom() {
    const output = document.getElementById('console-output');
    output.scrollTop = output.scrollHeight;
}

// 5. RAM settings synchronization
function setupRamConfigSync() {
    const minSlider = document.getElementById('min-ram-slider');
    const minText = document.getElementById('min-ram-text');
    const maxSlider = document.getElementById('max-ram-slider');
    const maxText = document.getElementById('max-ram-text');
    
    // Sync slider -> text & save
    minSlider.addEventListener('input', (e) => {
        minText.value = `${e.target.value}G`;
    });
    minSlider.addEventListener('change', () => {
        saveRamConfig();
    });
    
    maxSlider.addEventListener('input', (e) => {
        maxText.value = `${e.target.value}G`;
    });
    maxSlider.addEventListener('change', () => {
        saveRamConfig();
    });
    
    // Sync text -> slider & save
    minText.addEventListener('change', (e) => {
        const val = parseInt(e.target.value) || 1;
        minSlider.value = val;
        e.target.value = `${val}G`;
        saveRamConfig();
    });
    maxText.addEventListener('change', (e) => {
        const val = parseInt(e.target.value) || 4;
        maxSlider.value = val;
        e.target.value = `${val}G`;
        saveRamConfig();
    });
    
    const playitSecret = document.getElementById('playit-secret-input');
    if (playitSecret) {
        playitSecret.addEventListener('change', () => {
            saveRamConfig();
        });
    }
}

async function saveRamConfig() {
    const minText = document.getElementById('min-ram-text');
    const maxText = document.getElementById('max-ram-text');
    const playitSecret = document.getElementById('playit-secret-input');
    const indicator = document.getElementById('ram-autosave-indicator');
    const iconContainer = indicator.querySelector('.icon-container');
    
    indicator.classList.add('saving');
    indicator.querySelector('span').textContent = 'Saving settings...';
    iconContainer.innerHTML = '<i data-lucide="refresh-cw"></i>';
    lucide.createIcons();
    
    try {
        const minRam = minText.value;
        const maxRam = maxText.value;
        const secretVal = playitSecret ? playitSecret.value : '';
        const res = await fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ min_ram: minRam, max_ram: maxRam, playit_secret: secretVal })
        });
        if (res.ok) {
            setTimeout(() => {
                indicator.classList.remove('saving');
                indicator.querySelector('span').textContent = 'Settings saved automatically';
                iconContainer.innerHTML = '<i data-lucide="check"></i>';
                lucide.createIcons();
            }, 600);
        } else {
            indicator.classList.remove('saving');
            indicator.querySelector('span').textContent = 'Failed to auto-save';
            iconContainer.innerHTML = '<i data-lucide="x"></i>';
            lucide.createIcons();
        }
    } catch (err) {
        console.error("Failed to save RAM config:", err);
        indicator.classList.remove('saving');
        indicator.querySelector('span').textContent = 'Failed to auto-save';
        iconContainer.innerHTML = '<i data-lucide="x"></i>';
        lucide.createIcons();
    }
}

// 6. File Manager
function setupFileManager() {
    const tbody = document.getElementById('file-list-tbody');
    const uploadInput = document.getElementById('file-upload-input');
    const newFolderBtn = document.getElementById('new-folder-btn');
    
    // Modal buttons
    const editorModal = document.getElementById('editor-modal');
    const closeEditorBtn = document.getElementById('close-editor-btn');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const saveEditBtn = document.getElementById('save-edit-btn');
    
    const folderModal = document.getElementById('folder-modal');
    const closeFolderBtn = document.getElementById('close-folder-modal-btn');
    const cancelFolderBtn = document.getElementById('cancel-folder-btn');
    const confirmFolderBtn = document.getElementById('confirm-folder-btn');
    
    // Editor closure
    const hideEditor = () => editorModal.classList.remove('open');
    closeEditorBtn.addEventListener('click', hideEditor);
    cancelEditBtn.addEventListener('click', hideEditor);
    
    saveEditBtn.addEventListener('click', saveEditedFile);
    
    // Folder closure
    const hideFolder = () => folderModal.classList.remove('open');
    closeFolderBtn.addEventListener('click', hideFolder);
    cancelFolderBtn.addEventListener('click', hideFolder);
    
    newFolderBtn.addEventListener('click', () => {
        document.getElementById('new-folder-name').value = '';
        folderModal.classList.add('open');
    });
    
    confirmFolderBtn.addEventListener('click', createNewFolder);
    
    // Multi Upload File trigger
    uploadInput.addEventListener('change', async (e) => {
        if (e.target.files.length > 0) {
            for (let file of e.target.files) {
                await uploadSingleFile(file, appState.currentPath);
            }
            loadFiles();
        }
    });
}

async function loadFiles() {
    const tbody = document.getElementById('file-list-tbody');
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">Loading files...</td></tr>';
    
    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(appState.currentPath)}`);
        if (!res.ok) throw new Error("Failed to fetch files");
        const items = await res.json();
        
        tbody.innerHTML = '';
        
        if (items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">This folder is empty.</td></tr>';
            buildBreadcrumbs();
            lucide.createIcons();
            return;
        }
        
        items.forEach(item => {
            const tr = document.createElement('tr');
            
            // Name cell with icon
            const nameTd = document.createElement('td');
            const nameWrapper = document.createElement('div');
            nameWrapper.className = 'file-name-wrapper';
            
            let iconType = 'file';
            let iconClass = 'file-icon';
            if (item.is_dir) {
                iconType = 'folder';
                iconClass = 'folder-icon';
            } else if (item.name.endsWith('.jar')) {
                iconType = 'binary';
            } else if (item.is_editable) {
                iconType = 'file-text';
            }
            
            nameWrapper.innerHTML = `<i data-lucide="${iconType}" class="${iconClass}"></i> <span>${item.name}</span>`;
            nameTd.appendChild(nameWrapper);
            
            // Navigate if clicked
            nameWrapper.addEventListener('click', () => {
                if (item.is_dir) {
                    appState.currentPath = item.path;
                    loadFiles();
                } else if (item.is_editable) {
                    openFileEditor(item.path);
                }
            });
            
            // Size cell
            const sizeTd = document.createElement('td');
            sizeTd.textContent = item.is_dir ? '-' : formatSize(item.size);
            
            // Actions cell
            const actionsTd = document.createElement('td');
            const actionsWrapper = document.createElement('div');
            actionsWrapper.className = 'file-actions-wrapper';
            
            let actionButtonsHTML = '';
            if (item.is_editable) {
                actionButtonsHTML += `
                    <button class="action-btn edit-btn" title="Edit File" onclick="openFileEditor('${item.path}')">
                        <i data-lucide="edit-3"></i>
                    </button>
                `;
            }
            
            actionButtonsHTML += `
                <button class="action-btn delete-btn" title="Delete" onclick="deleteFileOrFolder('${item.path}')">
                    <i data-lucide="trash-2"></i>
                </button>
            `;
            
            actionsWrapper.innerHTML = actionButtonsHTML;
            actionsTd.appendChild(actionsWrapper);
            
            tr.appendChild(nameTd);
            tr.appendChild(sizeTd);
            tr.appendChild(actionsTd);
            
            tbody.appendChild(tr);
        });
        
        buildBreadcrumbs();
        lucide.createIcons();
    } catch (err) {
        console.error(err);
        tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;color:var(--danger);">Failed to load files.</td></tr>';
    }
}

function buildBreadcrumbs() {
    const container = document.getElementById('file-breadcrumbs');
    container.innerHTML = '<span class="breadcrumb-item" data-path="">root</span>';
    
    if (!appState.currentPath) {
        return;
    }
    
    const parts = appState.currentPath.split('/');
    let currentAccumulated = '';
    
    parts.forEach(part => {
        if (!part) return;
        currentAccumulated += (currentAccumulated ? '/' : '') + part;
        
        const span = document.createElement('span');
        span.className = 'breadcrumb-item';
        span.setAttribute('data-path', currentAccumulated);
        span.textContent = part;
        
        container.appendChild(span);
    });
    
    // Add click listeners to all items
    document.querySelectorAll('.breadcrumb-item').forEach(el => {
        el.addEventListener('click', () => {
            appState.currentPath = el.getAttribute('data-path');
            loadFiles();
        });
    });
}

async function openFileEditor(path) {
    try {
        const res = await fetch(`/api/files/read?path=${encodeURIComponent(path)}`);
        if (!res.ok) throw new Error("Failed to read file");
        
        const data = await res.json();
        
        appState.editingFilePath = path;
        document.getElementById('editor-title').textContent = `Editing: ${path}`;
        document.getElementById('editor-textarea').value = data.content;
        
        document.getElementById('editor-modal').classList.add('open');
    } catch (err) {
        alert(`Could not open file: ${err.message}`);
    }
}

// Attach globally so onclick attribute works in row HTML
window.openFileEditor = openFileEditor;

async function saveEditedFile() {
    try {
        const content = document.getElementById('editor-textarea').value;
        const res = await fetch('/api/files/write', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: appState.editingFilePath, content })
        });
        if (res.ok) {
            document.getElementById('editor-modal').classList.remove('open');
            loadFiles();
        } else {
            const err = await res.json();
            alert(`Error saving file: ${err.detail}`);
        }
    } catch (err) {
        alert(`Failed to save file: ${err}`);
    }
}

async function deleteFileOrFolder(path) {
    if (!confirm(`Are you sure you want to delete ${path}?`)) return;
    try {
        const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            loadFiles();
        } else {
            const err = await res.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (err) {
        alert(`Delete failed: ${err}`);
    }
}

// Attach globally
window.deleteFileOrFolder = deleteFileOrFolder;

async function createNewFolder() {
    const name = document.getElementById('new-folder-name').value.trim();
    if (!name) return;
    
    const folderPath = appState.currentPath ? `${appState.currentPath}/${name}` : name;
    
    try {
        const res = await fetch('/api/files/newfolder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: folderPath })
        });
        if (res.ok) {
            document.getElementById('folder-modal').classList.remove('open');
            loadFiles();
        } else {
            const err = await res.json();
            alert(`Error: ${err.detail}`);
        }
    } catch (err) {
        alert(`Failed to create folder: ${err}`);
    }
}

async function uploadSingleFile(file, destPath) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('path', destPath);
    
    try {
        const res = await fetch('/api/files/upload', {
            method: 'POST',
            body: formData
        });
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || "Upload failed");
        }
    } catch (err) {
        alert(`Upload error for ${file.name}: ${err.message}`);
    }
}

function formatSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function setupPlayitWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/playit`;
    
    let ws = new WebSocket(wsUrl);
    const output = document.getElementById('playit-output');
    
    ws.onopen = () => {
        output.innerHTML = '<div class="system-log">[Sculk Panel] Playit stream connected.</div>';
    };
    
    ws.onmessage = (event) => {
        const line = event.data;
        const row = document.createElement('div');
        
        if (line.includes("https://playit.gg/claim/")) {
            row.style.color = "var(--accent)";
            row.style.fontWeight = "bold";
            const urlRegex = /(https:\/\/playit\.gg\/claim\/[a-zA-Z0-9-]+)/g;
            row.innerHTML = line.replace(urlRegex, '<a href="$1" target="_blank" style="color:var(--accent); text-decoration: underline; font-weight: 700;">$1</a>');
        } else {
            row.textContent = line;
        }
        
        output.appendChild(row);
        
        if (output.childNodes.length > 500) {
            output.removeChild(output.firstChild);
        }
        output.scrollTop = output.scrollHeight;
    };
    
    ws.onclose = () => {
        const row = document.createElement('div');
        row.className = 'system-log';
        row.textContent = '[Sculk Panel] Playit stream disconnected. Reconnecting in 5s...';
        output.appendChild(row);
        output.scrollTop = output.scrollHeight;
        setTimeout(setupPlayitWebSocket, 5000);
    };
}
