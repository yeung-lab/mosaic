import os
import re
import subprocess
import json
import shutil
import tempfile
import threading
import cv2
from pathlib import Path
from typing import List, Dict, Tuple


class VideoProcessor:
    def __init__(self, upload_dir: str = "uploads", frames_dir: str = "frames"):
        self.upload_dir = Path(upload_dir)
        self.frames_dir = Path(frames_dir)
        self.upload_dir.mkdir(exist_ok=True)
        self.frames_dir.mkdir(exist_ok=True)
        self._encoder, self._enc_opts = self._detect_encoder()

    def _detect_encoder(self) -> Tuple[str, List[str]]:
        """Pick the fastest available H.264 encoder once at startup."""
        probe = subprocess.run(
            ['ffmpeg', '-f', 'lavfi', '-i', 'nullsrc=s=16x16:d=0.1',
             '-c:v', 'h264_videotoolbox', '-b:v', '1M', '-f', 'null', '-'],
            capture_output=True
        )
        if probe.returncode == 0:
            print("Using hardware encoder: h264_videotoolbox")
            return 'h264_videotoolbox', ['-b:v', '6M']
        print("Using software encoder: libx264 ultrafast")
        return 'libx264', ['-preset', 'ultrafast', '-crf', '22']

    def get_video_metadata(self, video_path: str) -> Dict:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception(f"ffprobe failed: {result.stderr}")

        data = json.loads(result.stdout)
        video_stream = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
        if not video_stream:
            raise Exception("No video stream found")

        total_frames = int(video_stream.get('nb_frames', 0)) or int(
            float(data['format']['duration']) * eval(video_stream['r_frame_rate'])
        )
        return {
            'duration': float(data['format']['duration']),
            'width': int(video_stream['width']),
            'height': int(video_stream['height']),
            'fps': eval(video_stream['r_frame_rate']),
            'total_frames': total_frames,
            'frame_count': total_frames,
        }

    def extract_frames_at_fps(self, video_path: str, fps: float = 5.0, progress_callback: callable = None) -> List[Dict[str, str]]:
        video_name = Path(video_path).stem
        output_pattern = str(self.frames_dir / f"{video_name}_frame_%06d.jpg")

        cmd = [
            'ffmpeg', '-i', video_path,
            '-vf', f'fps={fps}',
            '-q:v', '2',
            output_pattern
        ]

        if progress_callback:
            process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)
            progress = 0

            def monitor_progress():
                nonlocal progress
                duration = None
                for line in process.stderr:
                    if duration is None:
                        match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', line)
                        if match:
                            h, m, s = map(float, match.groups())
                            duration = h * 3600 + m * 60 + s
                    match = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                    if match and duration:
                        h, m, s = map(float, match.groups())
                        current_time = h * 3600 + m * 60 + s
                        new_progress = min(100, int((current_time / duration) * 100))
                        if new_progress > progress:
                            progress = new_progress
                            progress_callback(progress)

            thread = threading.Thread(target=monitor_progress, daemon=True)
            thread.start()
            process.wait()
            thread.join()

            if process.returncode != 0:
                raise Exception(f"ffmpeg frame extraction failed")
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ffmpeg frame extraction failed: {result.stderr}")

        frames = []
        for frame_file in sorted(self.frames_dir.glob(f"{video_name}_frame_*.jpg")):
            frame_num = int(frame_file.stem.split('_')[-1])
            timestamp = (frame_num - 1) / fps
            frames.append({
                'path': str(frame_file),
                'timestamp': f"{timestamp:.2f}s",
                'frame_number': frame_num
            })
        return frames

    def apply_blur_to_frames(self, frame_paths: List[str], blur_strength: int = 99) -> None:
        for frame_path in frame_paths:
            img = cv2.imread(frame_path)
            blurred = cv2.GaussianBlur(img, (blur_strength, blur_strength), 0)
            cv2.imwrite(frame_path, blurred)

    def _merge_blur_ranges(self, sorted_timestamps: List[float], window: float = 0.2) -> List[Tuple[float, float]]:
        """Merge adjacent/overlapping 0.2s preview windows into contiguous time ranges."""
        if not sorted_timestamps:
            return []
        ranges = []
        start = sorted_timestamps[0]
        end = start + window
        for ts in sorted_timestamps[1:]:
            if ts <= end + 0.001:
                end = max(end, ts + window)
            else:
                ranges.append((start, end))
                start = ts
                end = ts + window
        ranges.append((start, end))
        return ranges

    def _encode_segment(self, original_video: str, start: float, duration: float,
                        blur: bool, seg_path: str,
                        seg_idx: int, total_segs: int,
                        progress_callback) -> None:
        """Encode one segment, with or without blur, reporting progress."""
        vf = ['-vf', 'gblur=sigma=30'] if blur else []
        cmd = [
            'ffmpeg', '-y',
            '-ss', f'{start:.4f}',
            '-t', f'{duration:.4f}',
            '-i', original_video,
            *vf,
            '-c:v', self._encoder, *self._enc_opts,
            '-pix_fmt', 'yuv420p',
            '-c:a', 'copy',
            '-avoid_negative_ts', 'make_zero',
            seg_path
        ]

        if not progress_callback:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                raise Exception(f"Segment {seg_idx} failed: {r.stderr}")
            return

        p_start = int(seg_idx / total_segs * 95)
        p_end   = int((seg_idx + 1) / total_segs * 95)
        lines = []
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

        def monitor():
            for line in proc.stderr:
                lines.append(line)
                m = re.search(r'time=(\d+):(\d+):(\d+\.\d+)', line)
                if m and duration > 0:
                    h, mn, s = map(float, m.groups())
                    t = h * 3600 + mn * 60 + s
                    p = p_start + int(min(t / duration, 1.0) * (p_end - p_start))
                    progress_callback(p, "Exporting")

        th = threading.Thread(target=monitor, daemon=True)
        th.start()
        proc.wait()
        th.join()

        if proc.returncode != 0:
            raise Exception(f"Segment {seg_idx} failed: {''.join(lines).strip()}")

    def create_blurred_video(self, original_video: str, frame_timestamps: List[float],
                             output_path: str, progress_callback: callable = None) -> str:
        """
        Segment-based export: re-encode only blurred segments with gblur, re-encode
        unblurred segments without any filter, then concatenate. This avoids running
        gblur on every frame, cutting export time dramatically for long videos.
        """
        metadata = self.get_video_metadata(original_video)
        duration  = metadata['duration']

        ranges = self._merge_blur_ranges(sorted(frame_timestamps), window=0.2)

        # Build (start, end, needs_blur) segments
        segments: List[Tuple[float, float, bool]] = []
        prev = 0.0
        for start, end in ranges:
            if start > prev + 0.001:
                segments.append((prev, start, False))
            segments.append((start, min(end, duration), True))
            prev = end
        if prev < duration - 0.001:
            segments.append((prev, duration, False))

        temp_dir = Path(tempfile.mkdtemp())
        seg_files: List[str] = []

        try:
            n = len(segments)
            for i, (seg_start, seg_end, blur) in enumerate(segments):
                seg_path = str(temp_dir / f"seg_{i:04d}.mp4")
                self._encode_segment(
                    original_video, seg_start, seg_end - seg_start,
                    blur, seg_path, i, n, progress_callback
                )
                seg_files.append(seg_path)

            # Write concat manifest and merge with stream copy
            concat_list = temp_dir / "concat.txt"
            with open(concat_list, 'w') as f:
                for seg in seg_files:
                    f.write(f"file '{seg}'\n")

            if progress_callback:
                progress_callback(97, "Finalizing")

            result = subprocess.run([
                'ffmpeg', '-y',
                '-f', 'concat', '-safe', '0', '-i', str(concat_list),
                '-c', 'copy',
                '-movflags', '+faststart',
                output_path
            ], capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"Concatenation failed: {result.stderr}")

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return output_path
