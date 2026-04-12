"""
RedditNarratoAI Web界面
Reddit帖子转AI影视解说视频 / Agent全自动短剧解说
"""

import streamlit as st
import toml
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.pipeline import RedditVideoPipeline, run_pipeline
from app.services.prompt_templates import get_style_names, DEFAULT_STYLE
from app.models.errors import format_user_error

st.set_page_config(
    page_title="RedditNarratoAI",
    page_icon="🎬",
    layout="wide"
)

# 标题
st.title("🎬 RedditNarratoAI")
st.markdown("**Reddit帖子 → AI文案改写 → 带字幕配音的影视视频**")

# ==============================
# Configuration sidebar
# ==============================
CONFIG_PATH = Path(__file__).parent / "config.toml"


def _load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return toml.load(f)
    return {}


def _save_config(cfg):
    """持久化配置到config.toml"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        toml.dump(cfg, f)


app_config = _load_config()

with st.sidebar:
    st.header("⚙️ 配置")

    # --- 模式选择 ---
    mode = st.radio(
        "运行模式",
        ["Reddit流水线", "Agent短剧解说"],
        index=0,
        help="Reddit: 输入帖子URL → Agent: 搜索YouTube短剧",
    )

    # --- LLM配置 ---
    st.subheader("LLM 设置")
    llm_config = {
        "provider": st.selectbox(
            "Provider",
            ["openai", "ollama", "azure"],
            index=["openai", "ollama", "azure"].index(
                app_config.get("llm", {}).get("provider", "openai")
            ),
        ),
        "api_base": st.text_input(
            "API Base",
            value=app_config.get("llm", {}).get("api_base", "http://localhost:11434/v1"),
        ),
        "api_key": st.text_input(
            "API Key",
            value=app_config.get("llm", {}).get("api_key", "not-needed"),
            type="password",
        ),
        "model": st.text_input(
            "Model",
            value=app_config.get("llm", {}).get("model", "deepseek-r1:32b"),
        ),
    }

    # --- TTS配置 ---
    st.subheader("TTS 语音")
    voice_options = [
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-YunxiNeural",
        "zh-CN-YunyangNeural",
        "zh-CN-XiaoyiNeural",
        "zh-CN-YunjianNeural",
        "zh-CN-XiaochenNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural",
        "en-US-JennyNeural",
        "ja-JP-NanamiNeural",
        "ko-KR-SunHiNeural",
    ]
    current_voice = app_config.get("tts", {}).get("voice", "zh-CN-XiaoxiaoNeural")
    voice_idx = voice_options.index(current_voice) if current_voice in voice_options else 0
    voice = st.selectbox("语音", voice_options, index=voice_idx)

    # --- 风格选择 ---
    st.subheader("文案风格")
    style_list = get_style_names()
    style_labels = [f"{name}({key})" for key, name in style_list]
    style_keys = [key for key, _ in style_list]
    default_style_key = app_config.get("style", {}).get("default", DEFAULT_STYLE)
    style_idx = style_keys.index(default_style_key) if default_style_key in style_keys else 0
    selected_style = st.selectbox("预设", style_labels, index=style_idx)
    style_key = style_keys[style_labels.index(selected_style)]

    # --- 视频输出 ---
    st.subheader("视频输出")
    aspect = st.selectbox(
        "画面比例",
        ["自定义", "landscape (16:9横屏)", "portrait (9:16竖屏)", "square (1:1方形)"],
        index=0,
    )
    aspect_map = {
        "landscape (16:9横屏)": "landscape",
        "portrait (9:16竖屏)": "portrait",
        "square (1:1方形)": "square",
    }
    aspect_value = aspect_map.get(aspect, "")

    # --- Reddit配置 (条件显示) ---
    reddit_creds = {}
    if mode == "Reddit流水线":
        st.subheader("Reddit 凭证")
        reddit_creds = {
            "client_id": st.text_input(
                "Client ID",
                value=app_config.get("reddit", {}).get("creds", {}).get("client_id", ""),
            ),
            "client_secret": st.text_input(
                "Client Secret",
                value=app_config.get("reddit", {}).get("creds", {}).get("client_secret", ""),
                type="password",
            ),
            "username": st.text_input(
                "Username",
                value=app_config.get("reddit", {}).get("creds", {}).get("username", ""),
            ),
            "password": st.text_input(
                "Password",
                value=app_config.get("reddit", {}).get("creds", {}).get("password", ""),
                type="password",
            ),
        }

    # --- 保存配置按钮 ---
    if st.button("💾 保存配置", use_container_width=True):
        save_cfg = _load_config()
        save_cfg.setdefault("llm", {}).update(llm_config)
        save_cfg.setdefault("tts", {})["voice"] = voice
        save_cfg.setdefault("tts", {})["provider"] = "edge"
        save_cfg.setdefault("video", {})["aspect"] = aspect_value
        save_cfg.setdefault("style", {})["default"] = style_key
        if reddit_creds:
            save_cfg.setdefault("reddit", {})["creds"] = reddit_creds
        _save_config(save_cfg)
        st.success("配置已保存到 config.toml ✅")

    # 合并配置（运行时使用）
    full_config = {
        "reddit": {"creds": reddit_creds},
        "llm": llm_config,
        "tts": {"provider": "edge", "voice": voice},
        "video": {"aspect": aspect_value},
        "subtitle": app_config.get("subtitle", {}),
        "app": {"output_dir": "./output"},
        "style": {"default": style_key},
    }


# ==============================
# Main area
# ==============================
if mode == "Reddit流水线":
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("📥 输入")
        reddit_url = st.text_input(
            "Reddit帖子URL",
            placeholder="https://reddit.com/r/AskReddit/comments/xxx 或帖子ID",
            help="支持完整URL或纯帖子ID",
        )
        use_story_mode = st.checkbox("故事模式", value=True, help="帖子作为开头，评论作为内容")
        generate_btn = st.button("🚀 开始生成", type="primary", use_container_width=True)

    with col2:
        st.subheader("📊 状态")
        status_placeholder = st.empty()
        progress_bar = st.progress(0)
        log_placeholder = st.empty()

    if generate_btn and reddit_url:
        log_lines = []

        def progress_callback(step: str, percent: int):
            progress_bar.progress(min(percent / 100.0, 1.0))
            status_placeholder.info(step)
            log_lines.append(f"[{percent}%] {step}")
            log_placeholder.text_area("日志", value="\n".join(log_lines), height=200)

        try:
            status_placeholder.info("开始处理...")
            result = run_pipeline(
                reddit_url=reddit_url,
                config_dict=full_config,
                progress_callback=progress_callback,
                style=style_key,
            )

            if result.success:
                status_placeholder.success("🎉 视频生成成功!")
                st.balloons()

                st.subheader("📤 结果")
                r_col1, r_col2 = st.columns(2)
                with r_col1:
                    st.video(result.video_path)
                with r_col2:
                    st.markdown("**解说文案:**")
                    st.text_area("文案", value=result.script, height=200, disabled=True)

                with open(result.video_path, "rb") as f:
                    st.download_button(
                        "📥 下载视频",
                        f,
                        file_name=Path(result.video_path).name,
                        mime="video/mp4",
                    )
            else:
                status_placeholder.error(f"生成失败: {result.error}")

        except Exception as e:
            status_placeholder.error(format_user_error(e))

elif mode == "Agent短剧解说":
    st.subheader("🤖 Agent全自动短剧解说")
    col1, col2 = st.columns([1, 1])

    with col1:
        input_type = st.radio("输入方式", ["搜索关键词", "指定视频URL"], index=0)

        if input_type == "搜索关键词":
            keywords = st.text_input(
                "YouTube搜索关键词",
                placeholder="短剧 复仇 逆袭",
            )
            video_url = ""
        else:
            video_url = st.text_input(
                "YouTube视频URL",
                placeholder="https://youtube.com/watch?v=...",
            )
            keywords = ""

        max_videos = st.slider("最多处理视频数", 1, 10, 3)
        agent_btn = st.button("🚀 开始Agent流水线", type="primary", use_container_width=True)

    with col2:
        st.subheader("📊 Agent状态")
        agent_status = st.empty()
        agent_progress = st.progress(0)
        agent_log = st.empty()

    if agent_btn and (keywords or video_url):
        from app.agents.orchestrator import AgentOrchestrator
        from app.config.config import load_config as _load_cfg

        agent_log_lines = []
        cfg = _load_cfg()

        def agent_progress_cb(agent_name, pct, msg):
            agent_progress.progress(min(pct / 100.0, 1.0))
            agent_status.info(f"[{agent_name}] {msg}")
            agent_log_lines.append(f"[{agent_name}][{pct}%] {msg}")
            agent_log.text_area("日志", value="\n".join(agent_log_lines), height=300)

        try:
            orch = AgentOrchestrator(cfg)
            orch.set_progress_callback(agent_progress_cb)

            urls = [video_url] if video_url else []
            results = orch.run(
                keywords=keywords,
                urls=urls,
                max_videos=max_videos,
            )

            success_count = sum(1 for r in results if r.get("success"))
            if success_count > 0:
                agent_status.success(f"✅ {success_count}/{len(results)} 条视频生成成功！")
                for r in results:
                    if r.get("success"):
                        st.markdown(f"**{r.get('title', '未知')}**")
                        if r.get("video_path") and os.path.exists(r["video_path"]):
                            st.video(r["video_path"])
            else:
                agent_status.error("全部失败")
                for r in results:
                    st.error(f"{r.get('title', '?')}: {r.get('error', '未知')}")

        except Exception as e:
            agent_status.error(format_user_error(e))


# ==============================
# Help section
# ==============================
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 快速开始

    1. **配置LLM** (左侧面板)
       - Ollama: 确保 `ollama serve` 运行中，模型推荐 `deepseek-r1:32b`
       - OpenAI: 填入 API Key 和模型名

    2. **选择风格** — 悬疑/搞笑/震惊/温情/科普

    3. **选择模式**
       - **Reddit流水线**: 输入帖子URL，自动改写+配音+字幕+视频
       - **Agent短剧解说**: 搜索YouTube或指定视频，全自动分析+解说

    4. **保存配置** — 点击"💾 保存配置"，下次打开自动加载

    ### 视频输出格式
    | 预设 | 分辨率 | 适用平台 |
    |------|--------|---------|
    | 横屏 16:9 | 1920×1080 | YouTube/B站 |
    | 竖屏 9:16 | 1080×1920 | 抖音/快手/小红书 |
    | 方形 1:1 | 1080×1080 | Instagram/微信 |
    """)

st.markdown("---")
st.markdown(
    "<center>RedditNarratoAI v0.2.0 | 基于 NarratoAI + RedditVideoMakerBot</center>",
    unsafe_allow_html=True,
)
