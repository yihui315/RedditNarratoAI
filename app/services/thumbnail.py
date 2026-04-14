"""
缩略图生成服务
自动生成 YouTube 风格的视频封面缩略图
使用 Pillow 绘制，无需联网
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DEFAULT_THUMB_SIZE = (1280, 720)  # YouTube 缩略图标准尺寸


def create_thumbnail(
    title: str,
    output_path: str,
    background_color: str = "#1a1a2e",
    text_color: str = "#ffffff",
    font_size: int = 60,
    font_path: str = None,
    size: tuple = DEFAULT_THUMB_SIZE,
    subtitle: str = None,
    logo_text: str = "RedditNarratoAI",
) -> str:
    """
    生成 YouTube 风格缩略图

    参数:
        title: 缩略图主标题
        output_path: 输出文件路径
        background_color: 背景色（十六进制）
        text_color: 文字颜色（十六进制）
        font_size: 标题字体大小
        font_path: 字体文件路径（.ttf），None则用默认
        size: 缩略图尺寸 (width, height)
        subtitle: 副标题（可选）
        logo_text: 右下角 logo 文字

    返回:
        输出文件路径
    """
    W, H = size

    # 创建背景
    img = Image.new("RGB", size, background_color)
    draw = ImageDraw.Draw(img)

    # 加载字体
    try:
        if font_path and os.path.exists(font_path):
            title_font = ImageFont.truetype(font_path, font_size)
            subtitle_font = ImageFont.truetype(font_path, font_size // 2)
            logo_font = ImageFont.truetype(font_path, font_size // 3)
        else:
            # 尝试系统字体
            title_font = ImageFont.load_default(size=font_size)
            subtitle_font = ImageFont.load_default(size=font_size // 2)
            logo_font = ImageFont.load_default(size=font_size // 3)
    except Exception:
        title_font = ImageFont.load_default()
        subtitle_font = ImageFont.load_default()
        logo_font = ImageFont.load_default()

    # 绘制装饰线条
    draw.rectangle([(0, H - 8), (W, H)], fill="#e63946")  # 底部红色条

    # 绘制渐变色块装饰（左上角）
    for i in range(5):
        alpha = 30 + i * 15
        draw.rectangle(
            [(0, 0), (W * (i + 1) // 15, H // 8)],
            fill=(int(background_color[1:3], 16), int(background_color[3:5], 16), int(background_color[5:7], 16))
        )

    # 绘制标题（居中，自动换行）
    max_chars_per_line = int(W / (font_size * 0.6))
    lines = _wrap_text(title, max_chars_per_line)
    total_text_h = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        lh = bbox[3] - bbox[1]
        line_heights.append(lh)
        total_text_h += lh + 8

    y_start = (H - total_text_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        lw = bbox[2] - bbox[0]
        x = (W - lw) // 2
        draw.text((x, y_start), line, font=title_font, fill=text_color)
        y_start += line_heights[i] + 8

    # 绘制副标题
    if subtitle:
        sub_y = y_start + 20
        bbox = draw.textbbox((0, 0), subtitle, font=subtitle_font)
        sw = bbox[2] - bbox[0]
        sx = (W - sw) // 2
        draw.text((sx, sub_y), subtitle, font=subtitle_font, fill="#aaaaaa")

    # 绘制右下角 logo
    if logo_text:
        draw.text(
            (W - 10, H - 60),
            logo_text,
            font=logo_font,
            fill="#888888",
            anchor="rt",
        )

    # 添加边框
    draw.rectangle([(0, 0), (W - 1, H - 1)], outline="#333333", width=3)

    # 保存
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", quality=95)
    return output_path


def create_thumbnail_from_video_frame(
    video_path: str,
    title: str,
    output_path: str,
    time_seconds: float = 5.0,
    **kwargs,
) -> str:
    """
    从视频中截取一帧作为缩略图背景 + 叠加标题

    参数:
        video_path: 视频文件路径
        title: 标题文字
        output_path: 输出文件路径
        time_seconds: 截取视频的时间点（秒）
        **kwargs: create_thumbnail 的其他参数

    返回:
        输出文件路径
    """
    try:
        import subprocess

        # 用 FFmpeg 截取帧
        tmp_frame = output_path + ".tmp_frame.png"
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(time_seconds),
            "-i", video_path,
            "-vframes", "1",
            "-q:v", "2",
            tmp_frame,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode == 0 and os.path.exists(tmp_frame):
            # 叠加模糊背景
            from PIL import ImageFilter
            bg = Image.open(tmp_frame).resize((1280, 720), Image.LANCZOS)
            # 模糊处理
            blurred = bg.filter(ImageFilter.GaussianBlur(radius=15))
            # 半透明暗化
            overlay = Image.new("RGBA", blurred.size, (0, 0, 0, 0))
            dark = Image.new("RGBA", blurred.size, (0, 0, 0, 120))
            overlay = Image.alpha_composite(overlay, dark)
            final_bg = Image.alpha_composite(blurred.convert("RGBA"), overlay)
            # 转为 RGB 保存临时背景
            bg_path = output_path + ".bg.png"
            final_bg.convert("RGB").save(bg_path)

            # 生成缩略图
            thumb = create_thumbnail(title, output_path, **kwargs)
            # 把标题叠加到视频帧背景上
            frame_with_title = _compose_thumbnail(bg_path, title, output_path, **kwargs)
            os.unlink(tmp_frame)
            os.unlink(bg_path)
            return frame_with_title
    except Exception as e:
        pass

    # Fallback: 直接生成纯色背景缩略图
    return create_thumbnail(title, output_path, **kwargs)


def _compose_thumbnail(
    background_path: str,
    title: str,
    output_path: str,
    text_color: str = "#ffffff",
    font_size: int = 60,
    font_path: str = None,
    **kwargs,
) -> str:
    """将标题文字叠加到图片背景上"""
    img = Image.open(background_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        if font_path and os.path.exists(font_path):
            title_font = ImageFont.truetype(font_path, font_size)
        else:
            title_font = ImageFont.load_default()
    except Exception:
        title_font = ImageFont.load_default()

    W, H = img.size
    max_chars = int(W / (font_size * 0.6))
    lines = _wrap_text(title, max_chars)
    total_h = 0
    lh_list = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        lh = bbox[3] - bbox[1]
        lh_list.append(lh)
        total_h += lh + 8

    y = (H - total_h) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        lw = bbox[2] - bbox[0]
        # 文字描边
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                draw.text(((W - lw) // 2 + dx, y + dy), line, font=title_font, fill="#000000")
        draw.text(((W - lw) // 2, y), line, font=title_font, fill=text_color)
        y += lh_list[i] + 8

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "PNG", quality=95)
    return output_path


def _wrap_text(text: str, max_chars_per_line: int) -> list:
    """简单按空格换行"""
    import textwrap
    return textwrap.wrap(text, width=max_chars_per_line)
