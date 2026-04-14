"""
创建测试视频 - 带音频的标准MP4
"""
import subprocess
import os

output = '/home/ubuntu/RedditNarratoAI/test_movie/test_movie.mp4'
os.makedirs('/home/ubuntu/RedditNarratoAI/test_movie', exist_ok=True)

# Create a 20-second test video using FFmpeg with proper encoding
# Use a color gradient pattern instead of testsrc (which can be slow)
result = subprocess.run([
    'ffmpeg', '-y',
    # Generate color bars pattern
    '-f', 'lavfi', '-i', 'testsrc2=size=1280x720:rate=30:d=20',
    # Generate audio tone
    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=44100',
    # Video settings
    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
    '-pix_fmt', 'yuv420p',
    # Audio settings
    '-c:a', 'aac', '-b:a', '96k',
    # Output
    '-t', '20',
    output,
], capture_output=True, text=True, timeout=90)

if result.returncode == 0 and os.path.exists(output):
    size = os.path.getsize(output)
    print(f"✅ Test video created: {output}")
    print(f"   Size: {size:,} bytes ({size/1024:.1f} KB)")
else:
    print(f"❌ Failed to create test video")
    print(f"stdout: {result.stdout[-200:]}")
    print(f"stderr: {result.stderr[-200:]}")
