"""
RedditNarratoAI Web界面
Reddit帖子转AI影视解说视频 + B站高清下载 + 本地视频智能切片
"""

import streamlit as st
import toml
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from app.config_loader import config

st.set_page_config(page_title="RedditNarratoAI", page_icon="🎬", layout="wide")

st.title("🎬 RedditNarratoAI")
st.caption("Reddit帖子 / B站视频 / 本地视频 → AI解说配音 → 影视视频")

# ── 侧边栏配置 ──────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 配置")

    config_path = Path(__file__).parent / "config.toml"
    app_config = {}
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            app_config = toml.load(f)

    # Reddit
    st.subheader("Reddit 凭证")
    reddit_creds = app_config.get("reddit", {}).get("creds", {})
    reddit_creds = {
        "client_id": st.text_input("Client ID", value=reddit_creds.get("client_id", "")),
        "client_secret": st.text_input("Client Secret", value=reddit_creds.get("client_secret", ""), type="password"),
        "username": st.text_input("Username", value=reddit_creds.get("username", "")),
        "password": st.text_input("Password", value=reddit_creds.get("password", ""), type="password"),
    }

    # LLM
    st.subheader("LLM 设置")
    llm_cfg = app_config.get("llm", {})
    llm_config = {
        "provider": st.selectbox("Provider", ["openai", "ollama", "azure"], index=0),
        "api_base": st.text_input("API Base", value=llm_cfg.get("api_base", "http://localhost:11434/v1")),
        "model": st.selectbox(
            "模型",
            ["deepseek-r1:32b", "deepseek-r1:14b", "qwen2.5:32b", "llama3.1:8b"],
            index=0,
        ),
    }

    # TTS
    st.subheader("TTS 设置")
    voice = st.selectbox(
        "配音音色",
        [
            "zh-CN-XiaoxiaoNeural",
            "zh-CN-YunxiNeural",
            "zh-CN-YunyangNeural",
            "zh-HK-HiuGaaiNeural",
            "zh-TW-HsiaoYuNeural",
        ],
        index=0,
    )

    # 背景视频
    st.subheader("🎬 背景视频")
    bg_enable = st.checkbox("启用背景视频叠加", value=False, help="在素材背景视频上叠加解说画面，画中画效果")
    bg_theme = None
    if bg_enable:
        bg_theme = st.selectbox(
            "背景主题",
            ["随机", "代码", "自然森林", "城市夜景", "抽象蓝色", "简约平静", "游戏画面", "太空黑暗", "海岸波浪"],
            index=0,
        )
    bg_volume = st.slider("背景音量", 0.0, 1.0, 0.25, help="背景音乐音量（0=静音）")

    # 内容过滤
    st.subheader("🛡️ 内容过滤")
    blocked_words = st.text_input(
        "屏蔽词（逗号分隔）",
        value="",
        placeholder="nsfw, spoiler, 政治",
        help="含这些词的帖子/评论会被自动跳过",
    )

    # GPU 加速
    st.subheader("⚡ 性能")
    use_gpu = st.checkbox("GPU 硬件加速", value=True, help="使用 NVIDIA/AMD 显卡加速编码（推荐）")

    full_config = {
        "reddit": {"creds": reddit_creds, "blocked_words": blocked_words},
        "llm": llm_config,
        "tts": {"provider": "edge", "voice": voice},
        "app": {"output_dir": "./output"},
        "background": {
            "enable": bg_enable,
            "theme": bg_theme if bg_theme and bg_theme != "随机" else None,
            "volume": bg_volume,
        },
        "video": {"use_gpu": use_gpu},
    }

# ── 主界面 ──────────────────────────────────────────────
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 输入")

    input_mode = st.radio("输入模式", ["Reddit 帖子", "B站视频", "本地视频"], horizontal=True)

    reddit_url = None
    bilibili_id = None
    local_video_path = None
    cookies_text = None
    video_description = None

    if input_mode == "Reddit 帖子":
        reddit_url = st.text_input(
            "Reddit帖子URL",
            placeholder="https://reddit.com/r/AskReddit/comments/xxx",
            help="支持完整URL或纯帖子ID",
        )
        use_story_mode = st.checkbox("故事模式（帖子作开头，评论作内容）", value=True)

    elif input_mode == "B站视频":
        bilibili_id = st.text_input("B站视频BV号", placeholder="BVxxxxxx")
        st.caption("💡 上传 cookies.txt 可解锁 1080P+ 高清下载")
        uploaded_cookies = st.file_uploader("上传 cookies.txt（可选）", type=["txt"])
        if uploaded_cookies:
            cookies_text = uploaded_cookies.getvalue().decode("utf-8", errors="replace")
            st.success("Cookies 已加载 ✓ 可下载高清画质")
        use_story_mode = False

    else:
        uploaded_file = st.file_uploader(
            "上传本地视频",
            type=["mp4", "mkv", "avi", "mov"],
            help="支持大文件（>1GB），建议用 MP4 格式",
        )
        if uploaded_file:
            import tempfile

            tmp_dir = tempfile.mkdtemp()
            local_video_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(local_video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            size_mb = uploaded_file.size / 1024 / 1024
            st.success(f"已上传: {uploaded_file.name} ({size_mb:.1f} MB)")

        st.markdown("---")
        st.subheader("✂️ 视频切片设置（本地视频）")
        split_video = st.checkbox(
            "启用智能分段",
            value=False,
            help="自动检测静音点分段，每段独立AI配音（推荐长视频使用）",
        )

        if split_video:
            video_description = st.text_area(
                "📝 视频内容描述（可选）",
                placeholder="例如：这是一个关于程序员找工作的脱口秀视频，主角分享了3个面试技巧...",
                help="描述越详细，AI生成的每段解说越精准。留空则使用通用解说。",
                max_chars=500,
            )
            st.caption("💡 建议填写，可提升每段解说的相关性和连贯性")

        use_story_mode = False

    generate_btn = st.button("🚀 开始生成", type="primary", use_container_width=True)

with col2:
    st.subheader("📊 状态")
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    log_area = st.empty()

# ── 处理逻辑 ─────────────────────────────────────────────
if generate_btn:
    has_input = (
        (input_mode == "Reddit 帖子" and reddit_url)
        or (input_mode == "B站视频" and bilibili_id)
        or (input_mode == "本地视频" and local_video_path)
    )
    if not has_input:
        st.error("请填写输入内容")
    else:
        log_area.text_area("日志", value="", height=200, key="log")

        def progress_callback(step: str, percent: int):
            progress_bar.progress(percent / 100.0)
            status_placeholder.info(step)
            st.session_state.log += f"[{percent}%] {step}\n"
            log_area.text_area("日志", value=st.session_state.log, height=200, key="log_refresh")

        try:
            status_placeholder.info("开始处理...")

            if input_mode == "本地视频":
                from app.pipeline import run_local_video_pipeline

                result = run_local_video_pipeline(
                    video_path=local_video_path,
                    config_dict=full_config,
                    progress_callback=progress_callback,
                    split_video=split_video,
                    video_description=video_description,
                )

            else:
                from app.pipeline import run_pipeline

                result = run_pipeline(
                    reddit_url=reddit_url,
                    bilibili_id=bilibili_id,
                    bilibili_cookies=cookies_text,
                    config_dict=full_config,
                    progress_callback=progress_callback,
                )

            if result.success:
                status_placeholder.success("🎉 视频生成成功!")
                st.balloons()
                st.subheader("📤 结果")

                # 判断是文件夹还是文件
                result_path = result.video_path
                if os.path.isdir(result_path):
                    clips = sorted(Path(result_path).glob("clip_*.mp4"))
                    if clips:
                        st.info(f"共生成 {len(clips)} 个片段")
                        for clip in clips:
                            st.video(str(clip))
                        # 下载整个文件夹（zip）
                        import zipfile, io

                        zip_buf = io.BytesIO()
                        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                            for clip in clips:
                                zf.write(str(clip), clip.name)
                        zip_buf.seek(0)
                        st.download_button(
                            "📥 下载所有片段 (ZIP)",
                            zip_buf.getvalue(),
                            file_name="clips.zip",
                            mime="application/zip",
                        )
                else:
                    st.video(result_path)
                    with open(result_path, "rb") as f:
                        st.download_button(
                            "📥 下载视频",
                            f,
                            file_name=Path(result_path).name,
                            mime="video/mp4",
                        )

                if result.script:
                    st.markdown("**解说文案:**")
                    st.text_area("文案", value=result.script, height=200, disabled=True)

            else:
                status_placeholder.error(f"生成失败: {result.error}")

        except Exception as e:
            status_placeholder.error(f"错误: {e}")
            import traceback

            st.code(traceback.format_exc())

# ── 使用说明 ─────────────────────────────────────────────
with st.expander("📖 使用说明"):
    st.markdown("""
    **Reddit 帖子** — 输入 Reddit URL，AI 自动抓取评论改写成解说，生成配音+字幕视频

    **B站视频** — 输入 BV 号，自动下载字幕并用 AI 重新配音（上传 cookies.txt 可解锁 1080P+）

    **本地视频** — 上传本地视频文件，用 AI 重新配音并生成字幕
      - 勾选「智能分段」后，自动找视频中的自然停顿点切成多个片段
      - 每个片段**独立生成**一段完整解说配音，不是简单地把一段配音切分
      - 填写「视频内容描述」可提升解说质量
    """)
