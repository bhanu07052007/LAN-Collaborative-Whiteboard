# LAN-Based Multi-User Collaborative Whiteboard

A robust, standalone, high-performance desktop collaborative whiteboard application designed for Local Area Networks (LAN). Built with direct TCP socket programming in Python 3 and a modern desktop interface using PySide6 (Qt). Operates **completely offline without requiring an internet connection**.

---

## 1. Project Overview & Features

### Core Capabilities & Upgraded Features
- **Multi-User Real-Time Drawing**: Freehand pencil with stroke smoothing, eraser, straight line, rectangle, and circle/ellipse tools.
- **FEATURE 1: Sticky Notes & Text Tool**: Rich text objects and colorful sticky notes (Yellow, Pink, Blue, Green, Orange) placed anywhere on the canvas.
- **Mandatory Author Attribution**: Every text object and sticky note clearly shows `"Written by: <username>"`. Creator IDs and usernames are enforced authoritatively by the server to eliminate impersonation, and author info is preserved during moves, edits, and reloads.
- **FEATURE 2: Select, Move & Resize Objects**: Dedicated selection tool displaying dashed bounding boxes and resize handles. Drag to move, drag handles to resize, and delete via the Delete key without triggering new drawings.
- **FEATURE 3: Whiteboard History & Replay**: Server-ordered operation log with sequence numbers and timestamps. Full playback panel with timeline slider scrubber, Play/Pause, Step Forward/Back, variable playback speeds (0.5x, 1x, 2x, 4x), and state restoration.
- **FEATURE 4: Laser Pen & Laser Pointer**: Ephemeral presentation tools. Laser Pen draws glowing temporary strokes that automatically fade after ~2.5 seconds without polluting canvas history. Laser Pointer provides real-time cursor tracking with participant name badge.
- **FEATURE 5: Application-Level Delivery ACKs (OP_ACK)**: Explicit server acknowledgements for drawing operations with client pending tracking, error feedback, and server-side deduplication caching.
- **FEATURE 6: Chunked File Sharing Over TCP**: Direct file transfer through TCP sockets with base64 streaming, progress bar, chat notification, and local file download for recipients.
- **FEATURE 7: Meeting Session Report**: Automatic audit report generated in `data/meeting_logs/<room_id>_<date>_session.log` with Sections A (Session Info), B (Participant Activity Log), C (Chronological Event History), and D (Session End Summary). Automatically tracks early exits (`"Exited Early"` vs `"Completed"`).
- **FEATURE 8: Responsive GUI**: QScrollArea canvas embedding, QSplitter panel proportioning, non-wrapping compact toolbar, and clean high-DPI layout adapting to normal, maximized, and small screen sizes.
- **Late-Joining Client Catch-up**: Late joiners automatically receive an authoritative canvas snapshot containing active operations and the current sequence number.
- **Crash & Restart Recovery**: Atomic JSON session persistence stores whiteboard history, room settings, and chat logs across server restarts.

---

## 2. Technology Stack

| Component | Technology | Rationale |
|---|---|---|
| **Language** | Python 3.12 / 3.13 | High standard library networking support |
| **GUI Framework** | PySide6 (Qt 6) | Native cross-platform desktop UI with hardware-accelerated QPainter |
| **Transport Layer** | Direct TCP Sockets (`socket`) | Low-overhead byte streams without third-party web frameworks |
| **Framing Protocol** | Length-Prefixed Big-Endian Framing | 4-byte header (`!I`) + UTF-8 JSON payload to eliminate TCP streaming boundaries |
| **Concurrency** | `threading` + `threading.RLock` | Independent per-client receiver threads with per-client socket send locks |
| **Testing** | `pytest` / Custom Test Runner | Automated tests covering network framing, concurrency, ordering, sessions, and recovery |
| **Packaging** | `PyInstaller` | Standalone `.exe` binaries for Windows |

> **Strict Compliance**: No WebSockets, no Flask/Django/FastAPI, no Node.js, and no cloud dependencies.

---

## 3. System Architecture & Protocol

### Network Architecture
The system uses a centralized client-server topology:

```
                      +-----------------------------+
                      |   Authoritative TCP Server  |
                      |   (State, Ordering, Auth)   |
                      +--------------+--------------+
                                     |
              +----------------------+----------------------+
              |                      |                      |
      [TCP Port 8555]        [TCP Port 8555]        [TCP Port 8555]
              |                      |                      |
    +---------v---------+  +---------v---------+  +---------v---------+
    |  Client 1 (Alice) |  |   Client 2 (Bob)  |  | Client 3 (Charlie)|
    |  PySide6 GUI      |  |   PySide6 GUI     |  | PySide6 GUI       |
    +-------------------+  +-------------------+  +-------------------+
```

### TCP Message Framing
TCP provides a continuous byte stream without message boundaries. To prevent partial packet reads or message concatenation errors, every application message is framed as:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|               Message Length (4 bytes, Big-Endian)            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                                               |
|                   UTF-8 Encoded JSON Payload                  |
|                                                               |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Supported Protocol Message Types
- **Session Control**: `CREATE_ROOM`, `ROOM_CREATED`, `JOIN_ROOM`, `JOIN_SUCCESS`, `JOIN_FAILURE`, `LEAVE_ROOM`
- **Whiteboard Events**: `DRAW`, `ERASE`, `SHAPE`, `CLEAR_CANVAS`, `UNDO`, `REDO`
- **State & Synchronization**: `STATE_UPDATE`, `CANVAS_SNAPSHOT`
- **Collaboration**: `CHAT`, `PARTICIPANT_JOINED`, `PARTICIPANT_LEFT`
- **Health & Heartbeat**: `PING`, `PONG`, `ERROR`

---

## 4. Directory Structure

```
Collaborative-Whiteboard/
│
├── server/
│   ├── __init__.py
│   ├── main.py                     # Server CLI entry point and LAN discovery
│   ├── socket_server.py            # Multi-client TCP socket server and dispatcher
│   ├── connection_manager.py       # Client registry, thread-safe broadcasting
│   ├── session_manager.py          # Room lifecycle, passwords, participant tracking
│   ├── whiteboard_manager.py       # Authoritative canvas state, sequence numbering, undo/redo
│   ├── chat_manager.py             # Room chat storage and validation
│   ├── persistence_manager.py      # Atomic JSON session persistence
│   └── server_config.py            # Configuration settings and network IP resolution
│
├── client/
│   ├── __init__.py
│   ├── main.py                     # Client entry point and window manager
│   ├── network_client.py           # Background socket thread with Qt signals
│   ├── main_window.py              # Main whiteboard interface
│   ├── connection_window.py        # Connection and room selection landing screen
│   ├── canvas.py                   # PySide6 QPainter canvas with anti-aliasing
│   ├── toolbar.py                  # Drawing tools, color swatches, brush size slider
│   ├── chat_panel.py               # Real-time group chat panel
│   ├── participant_panel.py        # Connected user presence panel
│   └── local_state.py              # Client-side session and operation state
│
├── common/
│   ├── __init__.py
│   ├── protocol.py                 # Length-prefixed framing (send/recv/recv_exact)
│   ├── message_types.py            # Protocol MessageType definitions
│   └── constants.py                # Network constants, canvas limits, color palette
│
├── data/
│   └── sessions/                   # Saved room JSON snapshots
│
├── tests/
│   ├── __init__.py
│   ├── test_protocol.py            # Framing, partial reads, stream fragmentation
│   ├── test_server.py              # Multi-client TCP integration and dispatch
│   ├── test_sessions.py            # Room lifecycle, passwords, disambiguation
│   ├── test_synchronization.py     # Concurrent ops, sequence ordering, undo/redo
│   └── test_persistence.py         # State saving and restart recovery
│
├── requirements.txt                # Python package dependencies
├── run_tests.py                    # Automated test runner with detailed metrics
├── run_server.bat                  # One-click Windows server launch script
├── run_client.bat                  # One-click Windows client launch script
├── build_server.bat                # Windows PyInstaller server binary packager
├── build_client.bat                # Windows PyInstaller client binary packager
├── README.md                       # Comprehensive project documentation
└── PROJECT_STATUS.md               # Implementation checklist and verification
```

---

## 5. Installation & Setup

### Prerequisites
- Windows 10/11 (or Linux / macOS)
- Python 3.10, 3.11, 3.12, or 3.13 installed
- Ensure Python and pip are added to your system `PATH`.

### Installing Dependencies
Open Command Prompt or PowerShell in the project directory:

```powershell
pip install -r requirements.txt
```

---

## 6. How to Run the Application

### A. Starting the Server
Run using the provided batch script:
```powershell
.\run_server.bat
```
Or execute directly with Python:
```powershell
python -m server.main
```
Optional command-line arguments:
```powershell
python -m server.main --host 0.0.0.0 --port 8555 --verbose
```

When started, the terminal prints:
1. Active port (default `8555`).
2. List of non-loopback LAN IPv4 addresses assigned to your computer.

### B. Starting the Client
Run using the provided batch script:
```powershell
.\run_client.bat
```
Or execute directly with Python:
```powershell
python -m client.main
```

Launch multiple client instances on the same computer (using `127.0.0.1`) or from separate computers across your LAN.

---

## 7. Connecting Over Local Area Network (Multi-Computer Guide)

To collaborate with multiple computers connected to the same Wi-Fi router or Ethernet switch:

### Step 1: Find Server Machine IP
On the server computer, open Command Prompt and run:
```cmd
ipconfig
```
Look for **IPv4 Address** under your active Wi-Fi or Ethernet adapter (e.g., `192.168.1.45`). The server terminal also outputs this automatically upon startup.

### Step 2: Configure Windows Firewall
Allow incoming TCP connections on port 8555 on the server computer:

**Quick Command (Run PowerShell as Administrator):**
```powershell
New-NetFirewallRule -DisplayName "WhiteboardServer" -Direction Inbound -LocalPort 8555 -Protocol TCP -Action Allow
```

*Or via Windows Defender GUI:*
1. Open Windows Defender Firewall -> Advanced Settings.
2. Inbound Rules -> New Rule -> Port -> TCP -> Specific local ports: `8555`.
3. Select "Allow the connection" -> Name it "Whiteboard Server".

### Step 3: Connect Client Machines
On participant computers:
1. Launch the client application (`.\run_client.bat`).
2. In **Server IP Address**, enter the server's LAN IP (e.g., `192.168.1.45`).
3. Set **Port** to `8555`.
4. Enter your chosen **Username** and **Room ID** (e.g., `room-1`).
5. Click **Join Room** (or **Create Room** if hosting).

### Step 4: Running Without Internet
This application uses direct LAN TCP sockets. Disabling your external internet connection (or disconnecting the WAN cable from your router) will not affect the whiteboard; all connected devices on the LAN will continue collaborating smoothly.

---

## 8. Running Automated Tests

Run the comprehensive test suite with the built-in test runner:
```powershell
python run_tests.py
```
Or with pytest:
```powershell
pytest -v
```

The test suite validates:
1. TCP framing and packet header packing/unpacking.
2. Handling partial TCP reads and network chunking.
3. Multiple concatenated messages arriving in a single stream.
4. Malformed JSON and oversized message rejection.
5. End-to-end multi-client TCP socket connection and dispatch.
6. Room creation and access control with salted password hashes.
7. Automatic username disambiguation for duplicate participant names.
8. Concurrent drawing by multiple threads with strictly monotonic sequence numbers.
9. User-specific undo/redo isolating operations across collaborators.
10. Canvas clearing and late-joining client snapshot catch-up.
11. Atomic session persistence and recovery across server restarts.

---

## 9. Building Windows Standalone Executables (.exe)

Compile independent, standalone `.exe` binaries with PyInstaller:

### Build Server Executable:
```powershell
.\build_server.bat
```
Generates `dist\server.exe`.

### Build Client Executable:
```powershell
.\build_client.bat
```
Generates `dist\client.exe`.

The packaged executables can be transferred to any compatible Windows machine without requiring Python or external libraries to be installed.

---

## 10. Troubleshooting & FAQ

| Problem | Cause | Solution |
|---|---|---|
| **Client says "Could not connect to server"** | Server not running, wrong IP, or firewall blocked | Verify server terminal is running. Ensure client typed the server's LAN IPv4. Check Windows Firewall inbound rule on port 8555. |
| **"This room requires a password" error** | Room was created with password protection | Enter the room password in the connection window before clicking "Join Room". |
| **"Room not found" error** | Room hasn't been created yet | Click "Create Room" to create the room first, or verify the Room ID. |
| **Drawing is slow or laggy** | Mouse event flooding | The client includes built-in distance filtering (2px minimum delta) to batch drawing coordinates without overloading the network. |
| **Server port already in use** | Port 8555 occupied by another process | Specify a different port: `python -m server.main --port 9000` and use `9000` on the client. |
