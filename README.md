# Mosaic — Surgical Video De-identification

Manually select and blur frames from surgical videos on your local device. All processing happens on-device; no video data is sent to any external server.

---

## Quick Start (Zero Terminal — macOS)

1. **Double-click** `mosaic-launcher.app` in the project root.
2. The launcher will automatically:
   - install backend Python dependencies
   - build the React frontend
   - start the local server
   - open your browser to http://localhost:8000

To stop the app, run `./stop.sh` in terminal.

---

## Manual Start (Terminal)

### Prerequisites

- Python 3.9+
- Node.js 16+
- ffmpeg + ffprobe (`brew install ffmpeg` on macOS)

### Setup

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install
npm run build
```

### Run

```bash
cd backend
source venv/bin/activate
python main.py
```

Open http://localhost:8000 in your browser. The backend serves the compiled frontend, so only one process is needed.

---

## Usage

1. **Upload** a video (MP4, MOV, AVI, MKV, WebM) from the home page.
2. **Wait** for preview frames to extract at 5 FPS.
3. **Select frames** to blur:
   - Click a frame to select or deselect it.
   - Click and drag across frames to select a range.
   - Drag starting on an already-selected frame to deselect a range.
   - Use the **Frame size** toggle (Large / Medium / Small) to fit more frames on screen.
4. **Export** — click the export button, name your output file, and confirm.
5. **Download** the blurred video using the green Download button. The file is removed from the server automatically after download.

---

## Export Performance

The export pipeline uses a segment-based approach for speed:

- The video is split at blur range boundaries.
- **Blurred segments** are re-encoded with a heavy Gaussian blur (`gblur sigma=30`).
- **Unblurred segments** are re-encoded without any filter — no blur cost.
- All segments are merged with a fast stream-copy concat pass.
- On macOS, the hardware H.264 encoder (`h264_videotoolbox`) is used automatically when available, falling back to `libx264 -preset ultrafast`.

Typical performance: **~1 minute for a 15-minute 1080p video** on Apple Silicon.

---

## File Lifecycle

| File | When deleted |
|---|---|
| Uploaded source video | Immediately after successful export |
| Preview frames (`backend/frames/`) | After export completes |
| Exported blurred video | After the user downloads it |
| Abandoned session (no export) | When the user navigates home or uploads a new video |

---

## Project Structure

```
mosaic/
├── backend/
│   ├── main.py              # FastAPI server — upload, export, cleanup, download endpoints
│   ├── video_processing.py  # FFmpeg-based frame extraction and segment export pipeline
│   ├── requirements.txt     # Python dependencies
│   ├── uploads/             # Temporary storage for uploaded and exported videos
│   └── frames/              # Temporary preview frame JPEGs (cleared after export)
├── frontend/
│   ├── public/
│   │   ├── Mosaic_Logo.png
│   │   └── homepage_photo.png
│   ├── src/
│   │   ├── App.tsx          # Main React component
│   │   └── App.css          # Styles
│   └── package.json
├── start.sh                 # Manual start script
├── stop.sh                  # Stop script
├── mosaic-launcher.app      # Zero-terminal macOS launcher
└── README.md
```

---

## Disclaimer

This tool is intended for assistive de-identification workflows only. It is not guaranteed to fully remove all identifiable information.
