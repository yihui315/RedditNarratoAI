FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FFMPEG_VERSION=8.1-essentials

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl git ffmpeg unzip \
    libgl1-mesa-glx libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp (latest)
RUN pip install --no-cache-dir yt-dlp

# Set up working dir
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Create output directory
RUN mkdir -p /app/output

EXPOSE 8501

CMD ["streamlit", "run", "webui.py", "--server.port=8501", "--server.address=0.0.0.0", "--browser.gatherUsageStats=false"]
