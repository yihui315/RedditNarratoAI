FROM python:3.11-slim

WORKDIR /app

# System dependencies (FFmpeg + CJK fonts for subtitles)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create necessary directories
RUN mkdir -p /app/output /app/output/agents /app/config

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "webui.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
