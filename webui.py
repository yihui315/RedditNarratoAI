"""
RedditNarratoAI Web界面
Reddit帖子转AI影视解说视频
"""

import streamlit as st
import toml
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from app.config_loader import config
from app.pipeline import RedditVideoPipeline, run_pipeline

st.set_page_config(
    page_title="RedditNarratoAI",
    page_icon="🎬",
    layout="wide"
)

# 标题
st.title("🎬 RedditNarratoAI")
st.markdown("**Reddit帖子 → AI文案改写 → 带字幕配音的影视视频**")

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
    
    # Reddit配置
    st.subheader("Reddit 凭证")
    reddit_creds = app_config.get("reddit", {}).get("creds", {})
    reddit_creds = {
        "client_id": st.text_input("Client ID", value=reddit_creds.get("client_id", "")),
        "client_secret": st.text_input("Client Secret", value=reddit_creds.get("client_secret", ""), type="password"),
        "username": st.text_input("Username", value=reddit_creds.get("username", "")),
        "password": st.text_input("Password", value=reddit_creds.get("password", ""), type="password"),
    }
    
    # LLM配置
    st.subheader("LLM 设置")
    llm_config = app_config.get("llm", {})
    llm_config = {
        "provider": st.selectbox("Provider", ["openai", "ollama", "azure"], index=0),
        "api_base": st.text_input("API Base", value=llm_config.get("api_base", "http://localhost:11434/v1")),
        "model": st.text_input("Model", value=llm_config.get("model", "deepseek-r1:32b")),
    }
    
    # TTS配置
    st.subheader("TTS 设置")
    voice = st.selectbox(
        "语音", 
        ["zh-CN-XiaoxiaoNeural", "zh-CN-YunxiNeural", "zh-CN-YunyangNeural"],
        index=0
    )
    
    # 合并配置
    full_config = {
        "reddit": {"creds": reddit_creds},
        "llm": llm_config,
        "tts": {"provider": "edge", "voice": voice},
        "app": {"output_dir": "./output"}
    }

# 主界面
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📥 输入")
    
    # 输入模式选择
    input_mode = st.radio("输入模式", ["Reddit 帖子", "B站视频", "本地视频"], horizontal=True)
    
    reddit_url = None
    bilibili_id = None
    local_video_path = None
    
    if input_mode == "Reddit 帖子":
        reddit_url = st.text_input(
            "Reddit帖子URL",
            placeholder="https://reddit.com/r/AskReddit/comments/xxx 或帖子ID",
            help="支持完整URL或纯帖子ID"
        )
        use_story_mode = st.checkbox("故事模式", value=True, help="帖子作为开头，评论作为内容")
    elif input_mode == "B站视频":
        bilibili_id = st.text_input("B站视频BV号", placeholder="BVxxxxxx", help="输入B站视频的BV号")
        use_story_mode = False
    else:
        uploaded_file = st.file_uploader(
            "上传本地视频",
            type=["mp4", "mkv", "avi", "mov"],
            help="支持 MP4/MKV/AVI/MOV 格式"
        )
        if uploaded_file:
            import tempfile, os
            tmp_dir = tempfile.mkdtemp()
            local_video_path = os.path.join(tmp_dir, uploaded_file.name)
            with open(local_video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success(f"已上传: {uploaded_file.name} ({uploaded_file.size/1024/1024:.1f} MB)")
        use_story_mode = False
    
    generate_btn = st.button("🚀 开始生成", type="primary", use_container_width=True)

with col2:
    st.subheader("📊 状态")
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    log_area = st.empty()

# 处理
if generate_btn:
    if input_mode == "Reddit 帖子" and not reddit_url:
        st.error("请输入 Reddit 帖子URL")
    elif input_mode == "B站视频" and not bilibili_id:
        st.error("请输入 B站视频BV号")
    elif input_mode == "本地视频" and not local_video_path:
        st.error("请上传本地视频文件")
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
                    progress_callback=progress_callback
                )
            else:
                result = run_pipeline(
                    reddit_url=reddit_url,
                    bilibili_id=bilibili_id,
                    config_dict=full_config,
                    progress_callback=progress_callback
                )
        
        if result.success:
            status_placeholder.success("🎉 视频生成成功!")
            st.balloons()
            
            # 显示结果
            st.subheader("📤 结果")
            col1, col2 = st.columns(2)
            with col1:
                st.video(result.video_path)
            with col2:
                st.markdown("**解说文案:**")
                st.text_area("文案", value=result.script, height=200, disabled=True)
                
            # 下载按钮
            with open(result.video_path, "rb") as f:
                st.download_button(
                    "📥 下载视频",
                    f,
                    file_name=Path(result.video_path).name,
                    mime="video/mp4"
                )
        else:
            status_placeholder.error(f"生成失败: {result.error}")
            
    except Exception as e:
        status_placeholder.error(f"错误: {e}")
        import traceback
        st.code(traceback.format_exc())

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### 快速开始
    
    1. **配置Reddit凭证**
       - 访问 https://www.reddit.com/prefs/apps
       - 创建新的应用 (Script)
       - 填入 Client ID 和 Client Secret
    
    2. **配置LLM (Ollama)**
       - 确保 Ollama 运行中: `ollama serve`
       - 模型: deepseek-r1:32b 或 qwen2.5:32b
    
    3. **输入Reddit链接**
       - 支持格式:
         - 完整URL: `https://reddit.com/r/AskReddit/comments/abc123`
         - 仅Post ID: `abc123`
    
    4. **等待生成**
       - 获取帖子 → AI改写 → TTS配音 → 字幕 → 视频合成
    
    ### 支持的输入格式
    
    | 类型 | 示例 |
    |------|------|
    | 帖子URL | `https://reddit.com/r/xxx/comments/xxx` |
    | Post ID | `abc123def` |
    | Subreddit | `r/AskReddit` (需单独配置) |
    """)

# 底部信息
st.markdown("---")
st.markdown(
    "<center>RedditNarratoAI | 基于 NarratoAI + RedditVideoMakerBot</center>",
    unsafe_allow_html=True
)
