FROM python:3.11-slim

WORKDIR /app

# System dependencies (FFmpeg + yt-dlp support)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "webui.py", "--server.port=8501", "--server.address=0.0.0.0"]
