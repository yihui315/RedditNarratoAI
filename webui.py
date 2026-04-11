"""
RedditNarratoAI Web界面
Reddit帖子 / YouTube短剧 → AI影视解说视频
"""

import streamlit as st
import toml
import os
import sys
import json
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.config import config
from app.pipeline import RedditVideoPipeline, run_pipeline

st.set_page_config(
    page_title="RedditNarratoAI",
    page_icon="🎬",
    layout="wide"
)

# 标题
st.title("🎬 RedditNarratoAI")
st.markdown("**Reddit帖子 / YouTube短剧 → AI文案改写 → 带字幕配音的影视视频**")

# 侧边栏配置
with st.sidebar:
    st.header("⚙️ 配置")
    
    # 加载配置
    config_path = Path(__file__).parent / "config.toml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            app_config = toml.load(f)
    else:
        st.warning("config.toml 不存在，使用默认配置")
        app_config = {}
    
    # LLM配置
    st.subheader("LLM 设置")
    llm_provider = st.selectbox(
        "Provider", ["openai", "ollama", "azure", "deepseek"],
        index=["openai", "ollama", "azure", "deepseek"].index(
            app_config.get("llm", {}).get("provider", "openai")
        )
    )
    llm_api_base = st.text_input(
        "API Base",
        value=app_config.get("llm", {}).get("api_base", "http://localhost:11434/v1")
    )
    llm_api_key = st.text_input(
        "API Key",
        value=app_config.get("llm", {}).get("api_key", "not-needed"),
        type="password"
    )
    llm_model = st.text_input(
        "Model",
        value=app_config.get("llm", {}).get("model", "deepseek-r1:32b")
    )

    llm_config = {
        "provider": llm_provider,
        "api_base": llm_api_base,
        "api_key": llm_api_key,
        "model": llm_model,
        "max_tokens": app_config.get("llm", {}).get("max_tokens", 4096),
        "temperature": app_config.get("llm", {}).get("temperature", 0.7),
    }
    
    # TTS配置
    st.subheader("TTS 设置")
    voice = st.selectbox(
        "语音", 
        ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunyangNeural",
         "zh-CN-YunjianNeural", "en-US-AriaNeural", "en-US-GuyNeural"],
        index=0
    )
    tts_rate = st.slider("语速 (%)", -50, 100, 0, help="+50%=加速50%")
    tts_rate_str = f"+{tts_rate}%" if tts_rate >= 0 else f"{tts_rate}%"

    # 合并配置
    full_config = {
        **app_config,
        "llm": llm_config,
        "tts": {
            "provider": "edge",
            "voice": voice,
            "rate": tts_rate_str,
            "pitch": "+0Hz",
        },
        "app": app_config.get("app", {"output_dir": "./output"}),
    }

# 主界面 - Tab切换
tab_reddit, tab_agent = st.tabs(["📰 Reddit 模式", "🎬 短剧解说 (Agent)"])

# ==================== Reddit模式 ====================
with tab_reddit:
    st.subheader("Reddit帖子转视频")

    # Reddit配置
    with st.expander("Reddit 凭证", expanded=False):
        reddit_creds = {
            "client_id": st.text_input(
                "Client ID",
                value=app_config.get("reddit", {}).get("creds", {}).get("client_id", ""),
                key="reddit_client_id",
            ),
            "client_secret": st.text_input(
                "Client Secret",
                value=app_config.get("reddit", {}).get("creds", {}).get("client_secret", ""),
                type="password",
                key="reddit_client_secret",
            ),
            "username": st.text_input(
                "Username",
                value=app_config.get("reddit", {}).get("creds", {}).get("username", ""),
                key="reddit_username",
            ),
            "password": st.text_input(
                "Password",
                value=app_config.get("reddit", {}).get("creds", {}).get("password", ""),
                type="password",
                key="reddit_password",
            ),
        }
        full_config["reddit"] = {"creds": reddit_creds}

    col1, col2 = st.columns([1, 1])
    
    with col1:
        reddit_url = st.text_input(
            "Reddit帖子URL",
            placeholder="https://reddit.com/r/AskReddit/comments/xxx 或帖子ID",
            help="支持完整URL或纯帖子ID"
        )
        use_story_mode = st.checkbox("故事模式", value=True, help="帖子作为开头，评论作为内容")
        reddit_btn = st.button("🚀 开始生成", type="primary", use_container_width=True, key="reddit_btn")
    
    with col2:
        reddit_status = st.empty()
        reddit_progress = st.progress(0)

    if reddit_btn and reddit_url:
        def reddit_progress_cb(step: str, percent: int):
            reddit_progress.progress(percent / 100.0)
            reddit_status.info(step)
        
        try:
            reddit_status.info("开始处理...")
            result = run_pipeline(
                reddit_url=reddit_url,
                config_dict=full_config,
                progress_callback=reddit_progress_cb
            )
            
            if result.success:
                reddit_status.success("🎉 视频生成成功!")
                st.balloons()
                st.subheader("📤 结果")
                c1, c2 = st.columns(2)
                with c1:
                    st.video(result.video_path)
                with c2:
                    st.markdown("**解说文案:**")
                    st.text_area("文案", value=result.script, height=200, disabled=True)
                with open(result.video_path, "rb") as f:
                    st.download_button("📥 下载视频", f, file_name=Path(result.video_path).name, mime="video/mp4")
            else:
                reddit_status.error(f"生成失败: {result.error}")
                
        except Exception as e:
            reddit_status.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# ==================== Agent短剧解说模式 ====================
with tab_agent:
    st.subheader("YouTube短剧自动解说")
    st.markdown("搜索YouTube短剧 → AI剧情分析 → 爆款文案 → 配音 → 视频合成")

    input_mode = st.radio("输入方式", ["🔍 关键词搜索", "🔗 直接输入URL"], horizontal=True)

    if input_mode == "🔍 关键词搜索":
        keywords = st.text_input(
            "搜索关键词",
            placeholder="例如：短剧 复仇 逆袭",
            help="支持中文或英文关键词"
        )
        agent_urls = []
    else:
        keywords = ""
        urls_text = st.text_area(
            "YouTube视频URL（每行一个）",
            placeholder="https://www.youtube.com/watch?v=xxx\nhttps://www.youtube.com/watch?v=yyy",
            height=100,
        )
        agent_urls = [u.strip() for u in urls_text.split("\n") if u.strip()]

    max_videos = st.slider("最多处理视频数", 1, 10, 3)
    agent_btn = st.button("🎬 开始批量生成", type="primary", use_container_width=True, key="agent_btn")

    agent_status = st.empty()
    agent_progress = st.progress(0)

    if agent_btn and (keywords or agent_urls):
        try:
            from app.agents.orchestrator import AgentOrchestrator

            agent_status.info("初始化Agent编排器...")
            orch = AgentOrchestrator(full_config)

            def agent_progress_cb(agent_name: str, percent: int, msg: str):
                agent_progress.progress(percent / 100.0)
                agent_status.info(f"[{agent_name}] {msg}")

            orch.set_progress_callback(agent_progress_cb)

            results = orch.run(
                keywords=keywords,
                urls=agent_urls if agent_urls else None,
                max_videos=max_videos,
            )

            success_count = sum(1 for r in results if r.get("success"))
            if success_count > 0:
                agent_status.success(f"🎉 完成！成功 {success_count}/{len(results)} 条视频")
                st.balloons()
            else:
                agent_status.error("所有视频生成失败")

            for i, res in enumerate(results):
                with st.expander(f"{'✅' if res.get('success') else '❌'} 视频 {i+1}: {res.get('title', '未知')}", expanded=res.get("success", False)):
                    if res.get("success"):
                        video_path = res.get("video_path", "")
                        if video_path and os.path.exists(video_path):
                            st.video(video_path)
                            with open(video_path, "rb") as f:
                                st.download_button(
                                    f"📥 下载视频 {i+1}",
                                    f,
                                    file_name=Path(video_path).name,
                                    mime="video/mp4",
                                    key=f"dl_{i}",
                                )
                        if res.get("script"):
                            st.text_area("文案", value=res["script"], height=150, disabled=True, key=f"script_{i}")
                        if res.get("metadata"):
                            st.json(res["metadata"])
                    else:
                        st.error(f"失败阶段: {res.get('stage', '未知')}")
                        st.error(f"错误: {res.get('error', '未知错误')}")

        except Exception as e:
            agent_status.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 两种模式

    #### 📰 Reddit 模式
    将Reddit帖子（AskReddit等）转为AI解说视频：
    1. 配置Reddit API凭证（侧边栏）
    2. 输入Reddit帖子URL
    3. 选择故事模式（推荐）
    4. 点击开始生成

    #### 🎬 Agent 短剧解说模式
    自动搜索YouTube短剧并生成解说视频：
    1. 输入搜索关键词或直接粘贴YouTube链接
    2. 系统自动：搜索 → 下载字幕 → AI分析剧情 → 生成爆款文案 → TTS配音 → 合成视频
    3. 支持批量处理多条视频

    ### 配置要求
    - **LLM**: Ollama本地运行（推荐）或OpenAI/DeepSeek API
    - **TTS**: 默认使用Edge TTS（免费，无需配置）
    - **视频**: 需安装FFmpeg
    """)

# 底部信息
st.markdown("---")
st.markdown(
    "<center>RedditNarratoAI v0.2.0 | Reddit + YouTube → AI解说视频</center>",
    unsafe_allow_html=True
)
