FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-cjk \
    fonts-wqy-zenhei \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建输出和缓存目录
RUN mkdir -p /app/output /app/cache/broll /app/resource/bgm/tense /app/resource/bgm/emotional /app/resource/bgm/upbeat /app/resource/bgm/calm

# 默认入口
ENTRYPOINT ["python", "cli.py"]
CMD ["--help"]
