# Video to Color list

import cv2
import numpy as np

def video_to_hex_frames_fixed_fps(path, x, y, target_fps=20, max_seconds=None):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video: {path}")

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    # Estimate duration. (Works well for CFR videos; VFR can be approximate in OpenCV.)
    duration_s = (frame_count / src_fps) if (src_fps > 0 and frame_count > 0) else None

    if max_seconds is not None:
        duration_s = float(max_seconds) if duration_s is None else min(duration_s, float(max_seconds))

    # If we know the duration, compute exactly how many output frames we want.
    # If not, we'll keep sampling until reads fail.
    if duration_s is not None:
        out_frames = int(np.floor(duration_s * target_fps + 1e-9))
        sample_indices = range(out_frames)
    else:
        sample_indices = iter(int, 1)  # infinite iterator; we'll break on read failure

    frames_hex = []

    for k in sample_indices:
        t_msec = (k * 1000.0) / target_fps

        # Seek to the exact timeline position for frame k
        cap.set(cv2.CAP_PROP_POS_MSEC, t_msec)

        ok, frame_bgr = cap.read()
        if not ok:
            break

        small_bgr = cv2.resize(frame_bgr, (x, y), interpolation=cv2.INTER_AREA)
        small_rgb = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2RGB)

        rgb = small_rgb.astype(np.uint32)
        packed = (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | (rgb[..., 2])

        hex_frame = np.vectorize(lambda v: f"#{v:06x}")(packed)
        frames_hex.append(hex_frame)  # shape: (y, x)

    cap.release()
    return np.array(frames_hex, dtype="<U7")  # shape: (num_frames, y, x)

if __name__ == "__main__":
    import sys
    
    # Use raw string (r"") or double backslashes for Windows paths
    video_path = r"C:\Users\ryanp\Downloads\Rick_Astley_Never_Gonna_Give_You_Up.mp4"
    width = 20
    height = 20
    output_path = r"C:\Users\ryanp\OneDrive\Desktop\code\Minr Scrips\Video to Color list outputJSON.msc"
    max_seconds = 30  # Set to a number like 5 to test with just 5 seconds
    lines_per_file = 24  # Number of frames per output file

    print(f"Processing video: {video_path}")
    print(f"Output size: {width}x{height} at 20 FPS")
    
    frames_hex = video_to_hex_frames_fixed_fps(video_path, width, height, target_fps=20, max_seconds=max_seconds)

    print(f"Processed {len(frames_hex)} frames")
    
    # Save to output files in JSON text-component format, split into chunks of `lines_per_file` frames.
    # Each row's first cell carries "italic":false and a leading "\n" so rows stack vertically.
    import os
    base, ext = os.path.splitext(output_path)

    total_frames = len(frames_hex)
    written_paths = []
    for chunk_start in range(0, total_frames, lines_per_file):
        chunk_num = chunk_start // lines_per_file + 1
        chunk_path = f"{base}_part{chunk_num}{ext}"
        written_paths.append(chunk_path)

        with open(chunk_path, 'w', encoding='utf-8') as out_file:
            for offset in range(min(lines_per_file, total_frames - chunk_start)):
                frame_idx = chunk_start + offset + 1
                frame = frames_hex[chunk_start + offset]

                parts = []
                for row in frame:  # frame shape: (y, x)
                    for col_idx, color in enumerate(row):
                        if col_idx == 0:
                            parts.append(f'{{\\"color\\":\\"{color}\\",\\"italic\\":false,\\"text\\":\\"\\n▇\\"}}')
                        else:
                            parts.append(f'{{\\"color\\":\\"{color}\\",\\"text\\":\\"▇\\"}}')
                out_file.write(f'@bypass /var define rickastley String frame{frame_idx}JSON = "{",".join(parts)}"\n')
    print(f"Saved {len(written_paths)} file(s):")
    for p in written_paths:
        print(f"  {p}")