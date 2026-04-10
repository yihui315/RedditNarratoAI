"""
动态字幕样式服务
根据情绪标签切换字幕的颜色、字号和风格
"""

import re
from typing import Dict, List, Optional, Tuple
from loguru import logger


# 情绪标签对应的字幕样式
MOOD_STYLES: Dict[str, Dict] = {
    "tense": {
        "color": "#FF4444",       # 红色高亮
        "font_size": 40,          # 略大
        "bg_color": "#000000CC",  # 深色半透明底
        "stroke_color": "#880000",
        "stroke_width": 2,
        "description": "紧张 - 红色加粗",
    },
    "emotional": {
        "color": "#FFFFFF",       # 白色
        "font_size": 36,          # 标准
        "bg_color": "#00000066",  # 淡透明底
        "stroke_color": "#666666",
        "stroke_width": 1,
        "description": "感动 - 白色柔和",
    },
    "upbeat": {
        "color": "#FFD700",       # 金黄色
        "font_size": 38,          # 略大
        "bg_color": "#00000099",  # 中透明底
        "stroke_color": "#CC9900",
        "stroke_width": 1,
        "description": "欢快 - 黄色活力",
    },
    "calm": {
        "color": "#CCCCCC",       # 淡灰色
        "font_size": 34,          # 略小
        "bg_color": "#00000044",  # 淡透明底
        "stroke_color": "#888888",
        "stroke_width": 0,
        "description": "平静 - 灰色淡雅",
    },
}

# 默认样式
DEFAULT_STYLE = MOOD_STYLES["calm"]


class DynamicSubtitleService:
    """
    动态字幕服务

    根据情绪标签为每段字幕应用不同的视觉样式:
    - tense → 红色高亮、加粗
    - emotional → 白色、柔和阴影
    - upbeat → 黄色、活力风格
    - calm → 淡灰、透明底
    """

    def __init__(self, config: dict):
        self.config = config
        subtitle_config = config.get("subtitle", {})
        self.font = subtitle_config.get("font", "SimHei")
        self.position = subtitle_config.get("position", "bottom")
        self.base_font_size = subtitle_config.get("font_size", 36)

    def get_style_for_mood(self, mood: str) -> Dict:
        """
        获取情绪对应的字幕样式

        Args:
            mood: 情绪标签

        Returns:
            dict: 样式配置
        """
        style = MOOD_STYLES.get(mood, DEFAULT_STYLE).copy()
        # 可根据配置覆盖
        return style

    def create_styled_srt(
        self,
        timeline: List[dict],
        output_path: str
    ) -> str:
        """
        生成带样式标注的 SRT 字幕文件

        注意: 标准 SRT 不支持样式，这里输出带注释的 SRT。
        如需 ASS 格式可扩展 create_styled_ass()。

        Args:
            timeline: [{text, start_ms, end_ms, mood}, ...]
            output_path: 输出路径

        Returns:
            str: 输出文件路径
        """
        import os
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        lines = []
        for i, segment in enumerate(timeline):
            text = segment.get("text", "")
            start_ms = segment.get("start_ms", 0)
            end_ms = segment.get("end_ms", start_ms + 3000)
            mood = segment.get("mood", "calm")

            # 清理标注
            clean_text = re.sub(r'\[(?:mood|broll):[^\]]*\]', '', text).strip()
            if not clean_text:
                continue

            start_ts = _ms_to_srt_time(start_ms)
            end_ts = _ms_to_srt_time(end_ms)

            lines.append(str(i + 1))
            lines.append(f"{start_ts} --> {end_ts}")
            lines.append(clean_text)
            lines.append("")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"动态字幕文件已生成: {output_path}")
        return output_path

    def create_styled_ass(
        self,
        timeline: List[dict],
        output_path: str,
        width: int = 1920,
        height: int = 1080
    ) -> str:
        """
        生成 ASS 格式字幕（支持完整样式：颜色、描边、位置）

        Args:
            timeline: [{text, start_ms, end_ms, mood}, ...]
            output_path: 输出路径
            width: 视频宽度
            height: 视频高度

        Returns:
            str: 输出文件路径
        """
        import os
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        # ASS 头部
        header = f"""[Script Info]
Title: RedditNarratoAI Dynamic Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
Timer: 100.0000

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
"""
        # 为每种情绪创建样式
        styles = []
        for mood, style in MOOD_STYLES.items():
            color_ass = _hex_to_ass_color(style["color"])
            outline_ass = _hex_to_ass_color(style["stroke_color"])
            bg_ass = _hex_to_ass_color(style["bg_color"])
            bold = 1 if mood == "tense" else 0
            font_size = style["font_size"]
            outline_width = style["stroke_width"]

            styles.append(
                f"Style: {mood},{self.font},{font_size},{color_ass},&H000000FF,{outline_ass},{bg_ass},{bold},0,0,0,100,100,0,0,1,{outline_width},0,2,10,10,30,1"
            )

        header += "\n".join(styles)
        header += "\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"

        # 生成事件
        events = []
        for segment in timeline:
            text = segment.get("text", "")
            start_ms = segment.get("start_ms", 0)
            end_ms = segment.get("end_ms", start_ms + 3000)
            mood = segment.get("mood", "calm")

            clean_text = re.sub(r'\[(?:mood|broll):[^\]]*\]', '', text).strip()
            if not clean_text:
                continue

            start_ts = _ms_to_ass_time(start_ms)
            end_ts = _ms_to_ass_time(end_ms)

            # 换行处理
            display_text = clean_text.replace('\n', '\\N')

            events.append(
                f"Dialogue: 0,{start_ts},{end_ts},{mood},,0,0,0,,{display_text}"
            )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(header + "\n".join(events) + "\n")

        logger.info(f"ASS 字幕文件已生成: {output_path}")
        return output_path

    def get_moviepy_text_params(self, mood: str) -> Dict:
        """
        获取 MoviePy TextClip 参数（用于 MoviePy 渲染字幕）

        Args:
            mood: 情绪标签

        Returns:
            dict: TextClip 参数
        """
        style = self.get_style_for_mood(mood)
        return {
            "color": style["color"],
            "font_size": style["font_size"],
            "font": self.font,
            "stroke_color": style["stroke_color"],
            "stroke_width": style["stroke_width"],
        }


def _ms_to_srt_time(ms: int) -> str:
    """毫秒 → SRT 时间格式 00:01:23,456"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _ms_to_ass_time(ms: int) -> str:
    """毫秒 → ASS 时间格式 0:01:23.45"""
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    centis = (ms % 1000) // 10
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _hex_to_ass_color(hex_color: str) -> str:
    """
    HEX 颜色 → ASS 颜色格式
    #RRGGBB → &H00BBGGRR
    #RRGGBBAA → &HAABBGGRR
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 8:
        r, g, b, a = hex_color[0:2], hex_color[2:4], hex_color[4:6], hex_color[6:8]
    elif len(hex_color) == 6:
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        a = "00"
    else:
        # Unsupported format — default to white
        return "&H00FFFFFF"

    return f"&H{a}{b}{g}{r}"
