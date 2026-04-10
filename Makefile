# RedditNarratoAI Makefile

.PHONY: setup run batch webui docker-build docker-run test clean help

# 默认目标
help:
	@echo "🎬 RedditNarratoAI - Reddit帖子转AI影视解说视频"
	@echo ""
	@echo "Usage:"
	@echo "  make setup              安装依赖"
	@echo "  make run URL=<url>      处理单个 Reddit URL"
	@echo "  make batch URLS=<file>  批量处理"
	@echo "  make dry-run URL=<url>  只生成文案不合成视频"
	@echo "  make webui              启动 Web 界面"
	@echo "  make docker-build       构建 Docker 镜像"
	@echo "  make docker-run URL=<url> Docker 中运行"
	@echo "  make test               运行测试"
	@echo "  make clean              清理输出文件"

# 安装依赖
setup:
	pip install -r requirements.txt

# 处理单个 URL
run:
ifndef URL
	$(error URL is required. Usage: make run URL=https://reddit.com/r/AskReddit/comments/xxx)
endif
	python cli.py single $(URL)

# Dry run (只生成文案)
dry-run:
ifndef URL
	$(error URL is required. Usage: make dry-run URL=https://reddit.com/r/AskReddit/comments/xxx)
endif
	python cli.py single $(URL) --dry-run

# 批量处理
batch:
ifndef URLS
	$(error URLS is required. Usage: make batch URLS=urls.txt)
endif
	python cli.py batch $(URLS)

# 启动 Web 界面
webui:
	streamlit run webui.py

# Docker 构建
docker-build:
	docker-compose build

# Docker 运行
docker-run:
ifndef URL
	$(error URL is required. Usage: make docker-run URL=https://reddit.com/r/AskReddit/comments/xxx)
endif
	docker-compose run --rm app single $(URL)

# Docker 启动所有服务（含 WebUI + Ollama）
docker-up:
	docker-compose up -d

# Docker 停止
docker-down:
	docker-compose down

# 运行测试
test:
	python -m pytest tests/ -v

# 清理输出
clean:
	rm -rf output/*
	rm -rf cache/*
	@echo "✅ 输出和缓存已清理"
