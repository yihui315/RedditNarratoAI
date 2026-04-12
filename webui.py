"""
RedditNarratoAI Web界面
Reddit帖子转AI影视解说视频 / Agent全自动短剧解说
RedditNarratoAI v5.0 Web界面 — 短剧超级操盘手版
双模式: 解说模式 + 原创短剧模式
18-Agent Pipeline / 操盘手模式 / 竞品拆解 / 智能选题 / 爆款评分
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
from app.services.prompt_templates import get_style_names, DEFAULT_STYLE
from app.models.errors import format_user_error

st.set_page_config(
    page_title="RedditNarratoAI v5.0 - 短剧超级操盘手",
    page_icon="🚀",
    layout="wide"
)

# 标题
st.title("🚀 RedditNarratoAI v5.0 — 短剧超级操盘手")
st.markdown("**双模式**: 解说模式 + 原创短剧模式 → 18-Agent全自动生产 → 多平台发布")

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
        "tts": {
            "provider": "edge",
            "voice": voice,
            "rate": tts_rate_str,
            "pitch": "+0Hz",
        },
        "app": app_config.get("app", {"output_dir": "./output"}),
    }

    # v3.0: 视频生成配置
    st.subheader("🎥 视频生成")
    video_gen_mode = st.selectbox(
        "视频生成模式",
        ["moviepy", "kling", "runway"],
        index=0,
        help="moviepy=本地合成(免费), kling/runway=AI生成(需API Key)"
    )
    full_config["video_gen"] = {"mode": video_gen_mode}

    # v5.0: 高质配音配置
    st.subheader("🎙️ v5.0 高质配音")
    gpt_sovits_api = st.text_input(
        "GPT-SoVITS API",
        value=app_config.get("dubbing", {}).get("gpt_sovits_api", ""),
        help="留空则使用标准Edge TTS（免费）",
    )
    full_config["dubbing"] = {
        "enabled": True,
        "gpt_sovits_api": gpt_sovits_api,
    }

    # v3.0: 发布配置
    st.subheader("📤 自动发布")
    auto_publish = st.checkbox("启用自动发布", value=False)
    publish_platforms = st.multiselect(
        "发布平台",
        ["tiktok", "youtube_shorts", "instagram_reels"],
        default=[]
    )
    full_config["publish"] = {
        "auto_publish": auto_publish,
        "platforms": publish_platforms,
    }

# 主界面 - Tab切换 (v5.0: 6个Tab)
tab_daily, tab_drama, tab_decode, tab_reddit, tab_agent, tab_review = st.tabs([
    "🎯 操盘手模式", "🎬 原创短剧 (v5.0)", "🔍 竞品拆解", "📰 Reddit 模式",
    "🎬 短剧解说 (18-Agent v5.0)", "📊 质量诊断"
])

# ==================== 操盘手模式 (v4.0) ====================
with tab_daily:
    st.subheader("每日操盘手 — 一键全流程")
    st.markdown("""
    🔥 **v4.0核心功能**: 大白话输入 → 自动选题 → 批量文案 → 爆款评分 → 内容日历
    """)

    col_d1, col_d2 = st.columns([2, 1])
    with col_d1:
        daily_input = st.text_area(
            "大白话描述你的需求（自然语言意图识别）",
            placeholder="例如：我今天想发5条短剧解说，风格偏悬疑的\n或：帮我找最近Reddit上最火的故事",
            height=100,
        )
        topic_mode = st.selectbox(
            "选题模式",
            options=["hot", "mine", "rival", "flash"],
            format_func=lambda x: {
                "hot": "🔥 热门 (Reddit/YouTube热榜)",
                "mine": "💎 挖掘 (历史数据新角度)",
                "rival": "👀 竞品 (分析对手爆款)",
                "flash": "⚡ 热点 (突发事件/热搜)",
            }[x],
        )
    with col_d2:
        batch_size = st.number_input("每日产出数量", min_value=1, max_value=50, value=5)
        auto_mode = st.checkbox("全自动模式（无需人工确认）", value=True)

    # 画像管理
    with st.expander("👤 创作者画像设置", expanded=False):
        persona_input = st.text_area(
            "描述你的创作者定位",
            placeholder="例如：我是短剧解说博主，风格犀利吐槽，目标受众18-35岁",
            height=80,
        )
        if st.button("💾 保存/更新画像", key="save_persona"):
            try:
                from app.agents.orchestrator import AgentOrchestrator
                orch = AgentOrchestrator(full_config)
                persona_result = orch.persona_master.execute({
                    "user_input": persona_input,
                    "force_refresh": True,
                })
                if persona_result.success:
                    st.success("✅ 画像已保存!")
                    st.json(persona_result.data.get("persona", {}))
            except Exception as e:
                st.error(f"保存失败: {e}")

    daily_btn = st.button(
        "🚀 一键启动今日操盘手",
        type="primary",
        use_container_width=True,
        key="daily_btn",
    )

    daily_status = st.empty()
    daily_progress = st.progress(0)

    if daily_btn:
        try:
            from app.agents.orchestrator import AgentOrchestrator

            daily_status.info("正在启动操盘手模式...")
            orch = AgentOrchestrator(full_config)
            orch.set_progress_callback(
                lambda a, p, m: (
                    daily_progress.progress(p / 100.0),
                    daily_status.info(f"[{a}] {m}"),
                )
            )

            result = orch.run_daily(
                batch_size=batch_size,
                topic_mode=topic_mode,
                auto_mode=auto_mode,
                user_input=daily_input,
            )

            if result.get("success"):
                daily_status.success(
                    f"✅ 操盘手计划就绪！"
                    f"生成了 {len(result.get('topics', []))} 个选题"
                )

                st.subheader("📋 今日选题")
                for i, topic in enumerate(result.get("topics", [])):
                    st.markdown(f"**{i+1}. {topic.get('title', '未知')}**")
                    if topic.get("hook"):
                        st.caption(f"🎣 钩子: {topic['hook']}")

                if result.get("daily_plan", {}).get("calendar_entries"):
                    st.subheader("📅 内容日历")
                    for entry in result["daily_plan"]["calendar_entries"]:
                        st.markdown(
                            f"📌 {entry.get('date')} {entry.get('time')} — "
                            f"{entry.get('title')}"
                        )

                st.subheader("📝 下一步")
                for step in result.get("next_steps", []):
                    st.markdown(f"- {step}")
            else:
                daily_status.error("操盘手模式启动失败")

        except Exception as e:
            daily_status.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# ==================== 原创短剧模式 (v5.0) ====================
with tab_drama:
    st.subheader("原创短剧生成 — 一句话主题 → 全自动短剧制作")
    st.markdown("""
    🔥 **v5.0核心功能**: 输入主题/小说片段 → 自动角色生成 → 分镜拆解 → 高质配音 → AI视频 → 成品
    """)

    drama_theme = st.text_area(
        "一句话输入（主题/小说片段/灵感描述）",
        placeholder="例如：复仇短剧 女主被渣男抛弃后逆袭成为女总裁\n或：深夜加班的程序员发现公司AI系统有了自我意识",
        height=100,
        key="drama_theme",
    )

    col_dr1, col_dr2 = st.columns([1, 1])
    with col_dr1:
        drama_episodes = st.number_input("生成集数", min_value=1, max_value=10, value=1, key="drama_eps")
    with col_dr2:
        drama_user_input = st.text_input(
            "创作者定位（可选）",
            placeholder="悬疑风格、犀利吐槽...",
            key="drama_persona",
        )

    drama_btn = st.button(
        "🎬 开始生成原创短剧",
        type="primary",
        use_container_width=True,
        key="drama_btn",
    )

    drama_status = st.empty()
    drama_progress = st.progress(0)

    if drama_btn and drama_theme:
        try:
            from app.agents.orchestrator import AgentOrchestrator

            drama_status.info("启动原创短剧模式...")
            orch = AgentOrchestrator(full_config)
            orch.set_progress_callback(
                lambda a, p, m: (
                    drama_progress.progress(min(p, 100) / 100.0),
                    drama_status.info(f"[{a}] {m}"),
                )
            )

            results = orch.run_drama(
                theme=drama_theme,
                episodes=drama_episodes,
                user_input=drama_user_input,
            )

            success_count = sum(1 for r in results if r.get("success"))
            if success_count > 0:
                drama_status.success(f"🎉 完成！成功 {success_count}/{len(results)} 集")
                st.balloons()
            else:
                drama_status.error("所有集数生成失败")

            for i, res in enumerate(results):
                with st.expander(
                    f"{'✅' if res.get('success') else '❌'} 第{i+1}集: {res.get('title', '未知')}",
                    expanded=res.get("success", False),
                ):
                    if res.get("success"):
                        video_path = res.get("video_path", "")
                        if video_path and os.path.exists(video_path):
                            st.video(video_path)
                            with open(video_path, "rb") as f:
                                st.download_button(
                                    f"📥 下载视频 第{i+1}集",
                                    f,
                                    file_name=Path(video_path).name,
                                    mime="video/mp4",
                                    key=f"drama_dl_{i}",
                                )

                        if res.get("script"):
                            st.text_area(
                                "剧本", value=res["script"], height=150,
                                disabled=True, key=f"drama_script_{i}",
                            )

                        if res.get("characters"):
                            st.markdown("**🎭 角色**")
                            for ch in res["characters"]:
                                st.markdown(
                                    f"- **{ch.get('name', '?')}** ({ch.get('role', '')}): "
                                    f"{ch.get('personality', '')}"
                                )

                        if res.get("visual_assets"):
                            st.markdown("**🖼️ 视觉资产**")
                            for va in res["visual_assets"]:
                                va_path = va.get("path", "")
                                if va_path and os.path.exists(va_path):
                                    st.image(va_path, caption=va.get("style", ""), width=300)

                        seo = res.get("seo", {})
                        if seo:
                            st.markdown("**🔍 SEO**")
                            if seo.get("seo_title"):
                                st.info(f"📝 {seo['seo_title']}")
                            if seo.get("tags"):
                                st.write("🏷️ " + ", ".join(seo["tags"][:10]))
                    else:
                        st.error(f"失败阶段: {res.get('stage', '未知')}")
                        st.error(f"错误: {res.get('error', '未知错误')}")

        except Exception as e:
            drama_status.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# ==================== 竞品拆解 (v4.0) ====================
with tab_decode:
    st.subheader("竞品拆解 — 拆框架、存公式、秒懂爆款逻辑")
    st.markdown("粘贴竞品文案 → 自动拆解结构/情绪曲线/钩子公式 → 存入公式库")

    competitor_text = st.text_area(
        "粘贴竞品文案",
        placeholder="粘贴一条竞品的解说文案...",
        height=200,
    )
    decode_source = st.selectbox(
        "来源平台", ["reddit", "youtube", "douyin", "tiktok", "other"]
    )

    decode_btn = st.button(
        "🔍 开始拆解",
        type="primary",
        use_container_width=True,
        key="decode_btn",
    )

    if decode_btn and competitor_text:
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(full_config)
            result = orch.run_decode(competitor_text, source=decode_source)

            if result.get("success"):
                decode = result["decode"]
                st.success("✅ 拆解完成!")

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("### 📐 结构骨架")
                    structure = decode.get("structure", {})
                    st.markdown(f"**🎣 钩子:** {structure.get('hook', '')}")
                    st.markdown(f"**📖 铺垫:** {structure.get('setup', '')}")
                    st.markdown(f"**💥 核心:** {structure.get('core', '')}")
                    st.markdown(f"**🔚 收束:** {structure.get('closure', '')}")

                with col2:
                    st.markdown("### 📈 情绪曲线")
                    for point in decode.get("emotion_curve", []):
                        intensity = point.get("intensity", 0)
                        bar = "█" * intensity + "░" * (10 - intensity)
                        st.markdown(
                            f"{point.get('timestamp', '')} "
                            f"{point.get('emotion', '')} [{bar}] {intensity}/10"
                        )

                st.markdown("### ✨ 金句")
                for line in decode.get("golden_lines", []):
                    st.markdown(f"> {line}")

                formula = decode.get("hook_formula", {})
                if formula:
                    st.markdown("### 🧪 钩子公式 (已入库)")
                    st.info(
                        f"**{formula.get('name', '')}**: "
                        f"{formula.get('template', '')}\n\n"
                        f"例: {formula.get('example', '')}"
                    )

                st.markdown("### 🔄 迁移角度")
                for angle in decode.get("transferable_angles", []):
                    st.markdown(f"- {angle}")

                st.metric("爆款指数", f"{decode.get('viral_score', 0)}/10")
            else:
                st.error(f"拆解失败: {result.get('error', '未知错误')}")

        except Exception as e:
            st.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

    # 公式库展示
    with st.expander("📚 公式库 & 钩子库", expanded=False):
        formula_path = Path(__file__).parent / "config" / "formula-library.json"
        hooks_path = Path(__file__).parent / "config" / "hooks-library.json"

        if formula_path.exists():
            with open(formula_path, "r", encoding="utf-8") as f:
                formulas = json.load(f)
            st.markdown("**🧪 爆款公式库**")
            for fm in formulas.get("formulas", []):
                st.markdown(f"- **{fm.get('name', '')}**: {fm.get('template', '')}")

        if hooks_path.exists():
            with open(hooks_path, "r", encoding="utf-8") as f:
                hooks = json.load(f)
            st.markdown("**🎣 钩子库**")
            for hook in hooks.get("hooks", [])[:10]:
                st.markdown(f"> {hook}")

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
    st.subheader("YouTube短剧自动解说 (v5.0 18-Agent Pipeline)")
    st.markdown("""
    🔥 **v5.0**: 画像 → 选题 → 拆解 → 搜索 → 分析 → 文案 → 评分 → 配音 → B-roll → AI视频 → 剪辑 → 封面 → SEO → 发布 + 操盘手Supervisor
    """)

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

                        # v3.0: SEO数据展示
                        seo = res.get("seo", {})
                        if seo:
                            st.markdown("**🔍 SEO优化**")
                            if seo.get("seo_title"):
                                st.info(f"📝 优化标题: {seo['seo_title']}")
                            if seo.get("tags"):
                                st.write("🏷️ 标签: " + ", ".join(seo["tags"][:10]))
                            if seo.get("hashtags"):
                                st.write("🏷️ 话题: " + " ".join(seo["hashtags"][:8]))

                        # v3.0: 发布状态
                        publish = res.get("publish", {})
                        if publish:
                            st.markdown("**📤 发布状态**")
                            if publish.get("auto_publish"):
                                st.write(f"自动发布: {publish.get('success_count', 0)}/{publish.get('total_platforms', 0)} 平台")
                            else:
                                st.write("📦 发布包已准备，可手动上传")

                        if res.get("metadata"):
                            st.json(res["metadata"])
                    else:
                        st.error(f"失败阶段: {res.get('stage', '未知')}")
                        st.error(f"错误: {res.get('error', '未知错误')}")

        except Exception as e:
            agent_status.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# ==================== 质量诊断 (v4.0) ====================
with tab_review:
    st.subheader("爆款评分 & 质量诊断")
    st.markdown("5维度评分：钩子强度 / 情绪曲线 / 节奏时长 / 算法友好度 / 转化路径")

    review_script = st.text_area(
        "粘贴待诊断文案",
        placeholder="粘贴你写的解说文案...",
        height=200,
        key="review_script",
    )
    review_title = st.text_input("视频标题（可选）", key="review_title")

    review_btn = st.button(
        "📊 开始诊断",
        type="primary",
        use_container_width=True,
        key="review_btn",
    )

    if review_btn and review_script:
        try:
            from app.agents.orchestrator import AgentOrchestrator

            orch = AgentOrchestrator(full_config)
            result = orch.run_review(review_script, title=review_title)

            if result.get("success"):
                review = result["review"]
                st.success("✅ 诊断完成!")

                # Overall score
                overall = review.get("overall_score", 0)
                viral = review.get("viral_probability", "N/A")
                col_m1, col_m2 = st.columns(2)
                col_m1.metric("综合评分", f"{overall}/10")
                col_m2.metric("爆款概率", viral)

                # 5-dimension scores
                st.markdown("### 📊 5维度评分")
                scores = review.get("scores", {})
                dim_names = {
                    "hook_power": "🎣 钩子强度",
                    "emotion_arc": "📈 情绪曲线",
                    "pacing": "⏱️ 节奏时长",
                    "algorithm_fit": "🤖 算法友好",
                    "conversion_clarity": "🎯 转化路径",
                }
                for key, label in dim_names.items():
                    dim = scores.get(key, {})
                    score = dim.get("score", 0)
                    st.markdown(f"**{label}**: {'⭐' * score}{'☆' * (10 - score)} ({score}/10)")
                    if dim.get("reason"):
                        st.caption(f"分析: {dim['reason']}")
                    if dim.get("suggestion"):
                        st.caption(f"💡 建议: {dim['suggestion']}")

                # Issues and suggestions
                if review.get("top_issues"):
                    st.markdown("### ⚠️ 最需要改进")
                    for issue in review["top_issues"]:
                        st.warning(issue)

                if review.get("rewrite_suggestions"):
                    st.markdown("### 💡 修改建议")
                    for sug in review["rewrite_suggestions"]:
                        st.info(sug)

                if review.get("comment_bait"):
                    st.markdown("### 💬 评论引导语")
                    st.success(review["comment_bait"])
            else:
                st.error(f"诊断失败: {result.get('error', '未知错误')}")

        except Exception as e:
            st.error(f"错误: {e}")
            import traceback
            st.code(traceback.format_exc())

# 使用说明
with st.expander("📖 使用说明"):
    st.markdown("""
    ### v5.0 六大模式

    #### 🎯 操盘手模式 (~daily)
    一键启动全流程：自动选题 → 批量文案 → 爆款评分 → 内容日历
    - 支持自然语言输入（大白话描述需求）
    - 4种选题模式：热门/挖掘/竞品/热点
    - 全自动或人工确认两种模式

    #### 🎬 原创短剧 (v5.0新增)
    一句话主题 → 角色生成 → 分镜拆解 → 高质配音 → AI视频 → 成品
    - 支持GPT-SoVITS角色克隆配音
    - 自动生成封面/卡片

    #### 🔍 竞品拆解 (~decode)
    粘贴竞品文案，自动拆解：
    - 结构骨架（钩子-铺垫-核心-收束）
    - 情绪曲线峰值分析
    - 核心金句 + 可迁移公式
    - 自动存入公式库 & 钩子库

    #### 📰 Reddit 模式
    将Reddit帖子（AskReddit等）转为AI解说视频

    #### 🎬 Agent 短剧解说模式 (v5.0 18-Agent Pipeline)
    自动搜索YouTube短剧并生成解说视频：
    1. PersonaMaster → TopicEngine → CompetitorDecode → MaterialScout
    2. PlotAnalyzer → ScriptWriter → ReviewDiagnosis → VoiceAgent/DubbingAgent
    3. BrollMatcher → VideoGen → VideoEditor → VisualAsset → SEO → Publish
    4. + CharacterGen + StoryboardBreaker (原创短剧模式)
    5. + DailyOperator 操盘手Supervisor

    #### 📊 质量诊断 (~review)
    5维度爆款评分：钩子强度/情绪曲线/节奏时长/算法友好/转化路径

    ### 配置要求
    - **LLM**: Ollama本地运行（推荐）或OpenAI/DeepSeek API
    - **TTS**: 默认使用Edge TTS（免费，无需配置）
    - **高质配音**: GPT-SoVITS API（可选，角色级克隆）
    - **视频**: 需安装FFmpeg
    - **Docker部署**: `docker compose up -d --build`
    """)

st.markdown("---")
st.markdown(
    "<center>RedditNarratoAI v0.2.0 | 基于 NarratoAI + RedditVideoMakerBot</center>",
    unsafe_allow_html=True,
    "<center>RedditNarratoAI v5.0 | 18-Agent Pipeline | 短剧超级操盘手 | 解说+原创双模式 → 多平台发布</center>",
    unsafe_allow_html=True
)
