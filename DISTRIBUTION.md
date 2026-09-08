# SAP IM Config Explorer: Windows Offline Distribution & Operations Guide

This document provides complete instructions for running, operating, updating, and removing **SAP IM Config Explorer** on Windows workstations without external internet access, runtime package downloads, or third-party CDN connections.

---

## 1. Quick Start (Windows Workstations)

### Option A: Double-Click (Zero CLI Setup)
1. Extract the distribution archive (`SAP-IM-Config-Explorer-v<version>-windows-offline.zip`) to your desired folder (e.g. `C:\Tools\SAP-IM-Config-Explorer`).
2. Double-click **`launch.bat`**.
3. The launcher will automatically:
   - Validate or provision local Python dependencies from the pre-bundled `wheels/` directory without accessing the internet.
   - Initialize the local user data storage directory.
   - Bind the application server securely to loopback `127.0.0.1:8000`.
   - Verify server health at `http://127.0.0.1:8000/health`.
   - Launch your default system browser directly into the workspace.

### Option B: PowerShell
From PowerShell in the extracted directory:
```powershell
.\scripts\windows\launch.ps1
```

Custom port or headless background service:
```powershell
# Custom port
.\scripts\windows\launch.ps1 -Port 8080

# Background service (no auto-opening browser)
.\scripts\windows\launch.ps1 -Port 8000 -Background -Headless
```

---

## 2. Server Operations Lifecycle

### Health Check
Verify that the service is running and responsive:
```powershell
.\scripts\windows\healthcheck.ps1
```
Or via double-click on `healthcheck.bat`.

**Output:**
```text
Querying health endpoint: http://127.0.0.1:8000/health...
HEALTH CHECK: PASS
  Endpoint: http://127.0.0.1:8000/health
  Status: ok
  Latency: 8 ms
```

### Stopping the Server
To gracefully terminate the running server process:
```powershell
.\scripts\windows\stop.ps1
```
Or double-click `stop.bat`. The stop script queries `.runtime\app.pid` and safely shuts down the Uvicorn/Python process.

---

## 3. Network & Offline Isolation Policy

- **Loopback Binding by Default**: The application binds exclusively to `127.0.0.1`. It does not listen on external network adapters (`0.0.0.0`) unless explicitly overridden.
- **Zero Runtime CDN / Cloud Access**:
  - Frontend visualization libraries (**Cytoscape.js** 3.30.2 and **3d-force-graph** 1.73.4) are 100% locally vendored in `sap_im_config_graph_explorer/static/vendor/`.
  - Fonts and styles are self-contained in `sap_im_config_graph_explorer/static/styles.css`.
  - All graph calculations, XML parsing, rule lineage analysis, migration scoring, and export serialization occur locally on the machine.

---

## 4. User Data Storage & Upgrade Policy

### Storage Location
User data, reports, waivers, and saved sessions are isolated from the application binaries:
- **Default Location**: `%LOCALAPPDATA%\SAP-IM-Config-Explorer\` (e.g. `C:\Users\<User>\AppData\Local\SAP-IM-Config-Explorer\`)
- **Subdirectories**:
  - `sessions\`: Saved graph sessions (`.json` and `.zip`)
  - `exports\`: Downloaded CSV ZIPs, Markdown reports, and GraphML files
  - `waivers\`: Local audit finding waivers
  - `logs\`: Server execution logs (`server.log`)

### Custom Data Location
To store data in another directory or network drive:
```powershell
.\scripts\windows\launch.ps1 -DataDir "D:\SAP_IM_Data"
```
Or set the environment variable `$env:SAP_IM_DATA_DIR = "D:\SAP_IM_Data"`.

### Upgrading to a New Version
1. Stop the running server:
   ```powershell
   .\scripts\windows\stop.ps1
   ```
2. Unpack the new version archive into a new directory (or replace the application binaries).
3. Run `launch.ps1` in the new folder.
4. All existing saved sessions, waivers, and exports in `%LOCALAPPDATA%\SAP-IM-Config-Explorer` remain immediately available and intact.

---

## 5. Safe Uninstallation & Data Protection

### Safe Removal (Default: Preserves User Data)
To remove the application runtime, temporary caches, and virtual environment:
```powershell
.\scripts\windows\uninstall.ps1
```
Or double-click `uninstall.bat`.

> [!IMPORTANT]
> By default, `uninstall.ps1` **PRESERVES** all user data in `%LOCALAPPDATA%\SAP-IM-Config-Explorer`.
> No user-created graph sessions, waivers, or exports will be deleted.

### Complete Purge (Explicit Confirmation Required)
If you explicitly want to delete all user exports and saved sessions:
```powershell
.\scripts\windows\uninstall.ps1 -PurgeUserData
```
The script will prompt for explicit keyboard confirmation (`Type 'YES' to confirm permanent deletion`) before removing any user data files.

---

## 6. Building the Offline Package

To reproduce or build the distribution ZIP:
```powershell
# Build standard distribution ZIP in dist/
.\scripts\windows\package.ps1

# Download pip wheels and build zero-internet standalone bundle
.\scripts\windows\package.ps1 -DownloadWheels
```

The resulting package is written to:
`dist/SAP-IM-Config-Explorer-v<version>-windows-offline.zip`
accompanied by its `dist_manifest.json` and `.sha256` checksum.

---

## 7. Component Versions and Licenses

| Component | Version | License | Role |
| :--- | :--- | :--- | :--- |
| **SAP IM Config Explorer** | 0.1.0 | MIT | Core dependency graph & validation engine |
| **Cytoscape.js** | 3.30.2 | MIT | Local 2D graph renderer |
| **3d-force-graph** | 1.73.4 | MIT | Local 3D force-directed graph renderer |
| **FastAPI** | 0.139.0 | MIT | Local REST & web server API |
| **Uvicorn** | 0.51.0 | BSD-3-Clause | Local ASGI web server |
| **Starlette** | 1.3.1 | BSD-3-Clause | ASGI framework foundation |
| **Pydantic** | 2.13.4 | MIT | Data parsing and validation models |
| **defusedxml** | 0.7.1 | Apache-2.0 / PSFL | XML security parser (XXE defense) |
| **python-multipart** | 0.0.32 | Apache-2.0 | Multipart form upload handling |

See `LICENSE` and `THIRD_PARTY_LICENSES.md` for full legal notices.
