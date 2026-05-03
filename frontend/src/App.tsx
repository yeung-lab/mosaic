import React, { useEffect, useRef, useState } from 'react';
import './App.css';

function App() {
  const [serverStatus, setServerStatus] = useState('Checking...');
  const [uploadedVideo, setUploadedVideo] = useState<string | null>(null);
  const [frames, setFrames] = useState<any[]>([]);
  const [selectedFrames, setSelectedFrames] = useState<Set<number>>(new Set());
  const [uploadProgress, setUploadProgress] = useState<number>(0);
  const [uploadStatus, setUploadStatus] = useState<string>('Waiting for upload');
  const [actionStatus, setActionStatus] = useState<string>('');
  const [extractTaskId, setExtractTaskId] = useState<string | null>(null);
  const [exportTaskId, setExportTaskId] = useState<string | null>(null);
  const [extractProgress, setExtractProgress] = useState<number>(0);
  const [exportProgress, setExportProgress] = useState<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragStartTime, setDragStartTime] = useState<number>(0);
  const [dragStartSelection, setDragStartSelection] = useState<Set<number>>(new Set());
  const [dragMode, setDragMode] = useState<'add' | 'remove'>('add');
  const dragActivatedRef = useRef(false);
  const [showExportDialog, setShowExportDialog] = useState<boolean>(false);
  const [exportFilename, setExportFilename] = useState<string>('deidentified_video.mp4');
  const [exportedFilename, setExportedFilename] = useState<string | null>(null);
  const [hasInteracted, setHasInteracted] = useState<boolean>(false);
  const [frameSize, setFrameSize] = useState<'large' | 'medium' | 'small'>('large');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const frameSizeMap = { large: '150px', medium: '100px', small: '65px' };

  useEffect(() => {
    const checkServer = async () => {
      try {
        const response = await fetch('/health');
        setServerStatus(response.ok ? 'Online' : 'Offline');
      } catch {
        setServerStatus('Offline');
      }
    };
    checkServer();
  }, []);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (extractTaskId) {
      interval = setInterval(async () => {
        try {
          const response = await fetch(`/tasks/${extractTaskId}`);
          const task = await response.json();
          setExtractProgress(task.progress);
          setUploadStatus(task.message);
          if (task.status === 'completed') {
            setExtractTaskId(null);
            setFrames(task.result.frames);
            setUploadStatus('Preview frames ready. Select frames to blur.');
          } else if (task.status === 'failed') {
            setExtractTaskId(null);
            setUploadStatus('Frame extraction failed.');
            setActionStatus(task.error);
          }
        } catch {
          console.error('Task check failed');
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [extractTaskId]);

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (exportTaskId) {
      interval = setInterval(async () => {
        try {
          const response = await fetch(`/tasks/${exportTaskId}`);
          const task = await response.json();
          setExportProgress(task.progress);
          setActionStatus(task.message);
          if (task.status === 'completed') {
            setExportTaskId(null);
            const fname = task.result.output_path.split('/').pop();
            setExportedFilename(fname);
            setActionStatus('Export complete. Ready to download.');
          } else if (task.status === 'failed') {
            setExportTaskId(null);
            setActionStatus(task.error);
          }
        } catch {
          console.error('Task check failed');
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [exportTaskId]);

  const triggerFileInput = () => fileInputRef.current?.click();

  const cleanupSession = (videoPath: string | null) => {
    if (!videoPath) return;
    fetch('/cleanup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_path: videoPath }),
    }).catch(() => {});
  };

  const handleFileUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setHasInteracted(true);
    if (!exportTaskId) cleanupSession(uploadedVideo);
    setUploadProgress(0);
    setUploadStatus('Preparing upload...');
    setActionStatus('');
    setFrames([]);
    setSelectedFrames(new Set());
    setUploadedVideo(null);
    setExtractTaskId(null);
    setExportTaskId(null);
    setExtractProgress(0);
    setExportProgress(0);
    setExportedFilename(null);

    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload');

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        const percent = Math.round((e.loaded / e.total) * 100);
        setUploadProgress(percent);
        setUploadStatus(`Uploading: ${percent}%`);
      }
    };

    xhr.onload = async () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        setUploadStatus('Upload complete. Extracting frames...');
        try {
          const uploadData = JSON.parse(xhr.responseText);
          setUploadedVideo(uploadData.path);
          const extractResponse = await fetch('/extract-frames', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ video_path: uploadData.path }),
          });
          if (!extractResponse.ok) throw new Error(`Frame extraction failed: ${extractResponse.statusText}`);
          const extractData = await extractResponse.json();
          setExtractTaskId(extractData.task_id);
        } catch {
          setUploadStatus('Frame extraction failed.');
          setActionStatus('Error extracting preview frames.');
        }
      } else {
        setUploadStatus('Upload failed.');
        setActionStatus(`Upload failed: ${xhr.statusText}`);
      }
    };

    xhr.onerror = () => {
      setUploadStatus('Upload failed.');
      setActionStatus('There was an error uploading the file.');
    };

    xhr.send(formData);
  };

  const handleFrameMouseDown = (index: number, event: React.MouseEvent) => {
    event.preventDefault();
    dragActivatedRef.current = false;
    setIsDragging(true);
    setDragStart(index);
    setDragStartTime(Date.now());
    setDragStartSelection(new Set(selectedFrames));
    setDragMode(selectedFrames.has(index) ? 'remove' : 'add');
  };

  const handleFrameMouseEnter = (index: number) => {
    if (isDragging && dragStart !== null && Date.now() - dragStartTime > 100) {
      dragActivatedRef.current = true;
      const start = Math.min(dragStart, index);
      const end = Math.max(dragStart, index);
      const newSelected = new Set(dragStartSelection);
      for (let i = start; i <= end; i++) {
        if (dragMode === 'add') newSelected.add(i);
        else newSelected.delete(i);
      }
      setSelectedFrames(newSelected);
    }
  };

  const handleFrameClick = (index: number) => {
    if (!dragActivatedRef.current) {
      const newSelected = new Set(selectedFrames);
      if (newSelected.has(index)) newSelected.delete(index);
      else newSelected.add(index);
      setSelectedFrames(newSelected);
    }
  };

  const handleFrameMouseUp = () => {
    setIsDragging(false);
    setDragStart(null);
    setDragStartTime(0);
    setDragStartSelection(new Set());
  };

  const openExportDialog = () => {
    setExportFilename('deidentified_video.mp4');
    setExportedFilename(null);
    setShowExportDialog(true);
  };

  const handleExport = async () => {
    if (!uploadedVideo || selectedFrames.size === 0) return;
    let filename = exportFilename.trim() || 'deidentified_video.mp4';
    if (!filename.toLowerCase().endsWith('.mp4')) filename += '.mp4';

    setShowExportDialog(false);
    setActionStatus('Starting export...');
    setExportProgress(0);
    const timestamps = Array.from(selectedFrames).map((i) => parseFloat(frames[i].timestamp.replace('s', '')));

    try {
      const response = await fetch('/export-video', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ original_video: uploadedVideo, frame_timestamps: timestamps, output_filename: filename }),
      });
      if (!response.ok) throw new Error(`Export failed: ${response.statusText}`);
      const data = await response.json();
      setExportTaskId(data.task_id);
    } catch {
      setActionStatus('Export failed.');
    }
  };

  // ─── Landing page ───
  if (!hasInteracted) {
    return (
      <div className="landing">
        <div className="landing-photo" style={{ backgroundImage: `url(${process.env.PUBLIC_URL}/homepage_photo.png)` }} />
        <div className="landing-panel">
          <div className="landing-content">
            <img src="/Mosaic_Logo.png" alt="Mosaic" className="landing-logo" />
            <h1 className="landing-title">Surgical Video De-identification</h1>
            <p className="landing-description">
              Manually select and blur frames from surgical videos on your local device.
            </p>
            <button className="btn-red btn-full" onClick={triggerFileInput}>
              Upload Video
            </button>
            <p className="landing-disclaimer">
              For assistive de-identification workflows only. Not guaranteed to fully remove all identifiable information.
            </p>
          </div>
          <input ref={fileInputRef} type="file" accept=".mp4,.mov,.avi,.mkv,.webm" onChange={handleFileUpload} style={{ display: 'none' }} />
        </div>
      </div>
    );
  }

  // ─── Working view ───
  return (
    <div className="App">
      <div className="app-header">
        <img src="/Mosaic_Logo.png" alt="Mosaic" className="header-logo" style={{ cursor: 'pointer' }} onClick={() => { if (!exportTaskId) cleanupSession(uploadedVideo); setHasInteracted(false); }} />
        <div className="header-right">
          <span className={`status-dot ${serverStatus === 'Online' ? 'online' : 'offline'}`} />
          <span className="status-label">{serverStatus}</span>
          <button className="btn-red btn-sm" onClick={triggerFileInput}>Upload New Video</button>
        </div>
        <input ref={fileInputRef} type="file" accept=".mp4,.mov,.avi,.mkv,.webm" onChange={handleFileUpload} style={{ display: 'none' }} />
      </div>

      <div className="work-body">
        <div className="status-panel">
          {exportProgress === 0 && <div className="status-text">{uploadStatus}</div>}
          {uploadProgress > 0 && uploadProgress < 100 && (
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${uploadProgress}%` }} /></div>
          )}
          {extractProgress > 0 && exportProgress === 0 && (
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${extractProgress}%` }} /></div>
          )}
          {exportProgress > 0 && (
            <div className="progress-bar"><div className="progress-fill" style={{ width: `${exportProgress}%` }} /></div>
          )}
          {actionStatus && <div className="action-status">{actionStatus}</div>}
        </div>

        {frames.length > 0 && (
          <div className="grid-toolbar">
            <span className="grid-toolbar-label">Frame size</span>
            <div className="size-toggle">
              {(['large', 'medium', 'small'] as const).map((s) => (
                <button key={s} className={`size-btn ${frameSize === s ? 'active' : ''}`} onClick={() => setFrameSize(s)}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </button>
              ))}
            </div>
          </div>
        )}
        {frames.length > 0 && (
          <div
            className="frames-grid"
            style={{ gridTemplateColumns: `repeat(auto-fill, minmax(${frameSizeMap[frameSize]}, 1fr))` }}
            onMouseUp={handleFrameMouseUp}
            onMouseLeave={handleFrameMouseUp}
          >
            {frames.map((frame, index) => (
              <div
                key={index}
                className={`frame-thumbnail ${selectedFrames.has(index) ? 'selected' : ''}`}
                onMouseDown={(e) => handleFrameMouseDown(index, e)}
                onMouseEnter={() => handleFrameMouseEnter(index)}
                onClick={() => handleFrameClick(index)}
              >
                <img src={`/frames/${frame.path.split('/').pop()}`} alt={`Frame ${index}`} />
                <div className="frame-info">{frame.timestamp}</div>
              </div>
            ))}
          </div>
        )}

        <div className="action-row">
          {selectedFrames.size > 0 && (
            <button className="btn-red" onClick={openExportDialog} disabled={!!exportTaskId}>
              Export Video with Blurred Frames ({selectedFrames.size} frames selected)
            </button>
          )}
          {exportedFilename && (
            <a href={`/download/${exportedFilename}`} download={exportedFilename}>
              <button className="btn-download">Download {exportedFilename}</button>
            </a>
          )}
        </div>
      </div>

      {showExportDialog && (
        <div className="modal-overlay" onClick={() => setShowExportDialog(false)}>
          <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
            <h3>Name your export</h3>
            <input
              type="text"
              value={exportFilename}
              onChange={(e) => setExportFilename(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && exportFilename.trim() && handleExport()}
              autoFocus
            />
            <p className="modal-hint">A .mp4 extension will be added if omitted. Use your browser's download dialog to choose where to save the file.</p>
            <div className="modal-actions">
              <button className="btn-secondary" onClick={() => setShowExportDialog(false)}>Cancel</button>
              <button className="btn-red" onClick={handleExport} disabled={!exportFilename.trim()}>Export</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
