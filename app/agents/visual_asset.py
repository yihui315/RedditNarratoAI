"""
Agent: VisualAssetAgent (v5.0)
多厂商文生图 + 平台风格卡片自动生成（小红书/TikTok风格）
灵感来源: baoyu-skills 视觉卡片 + 多平台内容技能

输入: script + seo_data → 生成封面图/卡片/缩略图
输出: visual_assets 路径列表
优雅降级: 无API Key时使用Pillow本地生成简约风格卡片
"""

import os
import json
from typing import Any, Dict, List, Optional
from pathlib import Path
from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class VisualAssetAgent(BaseAgent):
    """
    视觉资产生成Agent (v5.0)

    支持:
    1. AI文生图模式: MiniMax / DALL-E / Vidu（需API Key）
    2. 本地Pillow模式: 简约风格封面卡片（默认降级，免费）

    生成资产类型:
    - 封面缩略图（16:9 视频封面）
    - 小红书风格竖版卡片（3:4）
    - TikTok封面（9:16 竖版）
    """

    def __init__(self, config: dict):
        super().__init__(config, name="VisualAsset")
        self.output_dir = Path(
            config.get("agents", {}).get("work_dir", "./output/agents")
        ) / "visual_assets"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        visual_cfg = config.get("visual_asset", {})
        self.minimax_api_key = (
            visual_cfg.get("minimax_api_key", "")
            or os.getenv("MINIMAX_API_KEY", "")
        )
        self.vidu_api_key = (
            visual_cfg.get("vidu_api_key", "")
            or os.getenv("VIDU_API_KEY", "")
        )

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            title (str): 视频标题
            script (str): 解说文案（提取关键画面）
            seo (dict): SEO数据（标签、描述等）
            session_id (str): 会话ID
            styles (list): 需要生成的风格列表（默认["thumbnail"]）
        """
        title = input_data.get("title", "")
        script = input_data.get("script", "")
        session_id = input_data.get("session_id", "default")
        styles = input_data.get("styles", ["thumbnail"])

        if not title and not script:
            return AgentResult(
                success=False,
                error="缺少标题(title)或文案(script)输入",
            )

        session_dir = self.output_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        assets = []
        text_for_image = title or script[:100]

        for style in styles:
            asset_path = self._generate_asset(
                text_for_image, style, session_dir
            )
            if asset_path:
                assets.append({
                    "style": style,
                    "path": asset_path,
                })

        return AgentResult(
            success=True,
            data={
                "visual_assets": assets,
                "asset_count": len(assets),
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 至少生成1个资产"""
        if not result.success:
            return False
        assets = result.data.get("visual_assets", [])
        return len(assets) > 0

    def _generate_asset(
        self, text: str, style: str, output_dir: Path
    ) -> Optional[str]:
        """生成单个视觉资产"""
        # 尝试AI文生图
        if self.minimax_api_key:
            try:
                return self._generate_minimax(text, style, output_dir)
            except Exception as e:
                logger.warning(f"[VisualAsset] MiniMax生图失败: {e}")

        # 降级：Pillow本地生成
        try:
            return self._generate_pillow_card(text, style, output_dir)
        except Exception as e:
            logger.error(f"[VisualAsset] Pillow生成失败: {e}")
            return None

    def _generate_minimax(
        self, text: str, style: str, output_dir: Path
    ) -> Optional[str]:
        """使用MiniMax API生成图片"""
        import requests

        size_map = {
            "thumbnail": "1280x720",
            "xhs_card": "1080x1440",
            "tiktok_cover": "720x1280",
        }
        size = size_map.get(style, "1280x720")
        w, h = size.split("x")

        prompt = f"Professional video thumbnail, dramatic, cinematic: {text[:200]}"

        headers = {
            "Authorization": f"Bearer {self.minimax_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "width": int(w),
            "height": int(h),
            "model": "abab6.5-chat",
        }

        resp = requests.post(
            "https://api.minimax.chat/v1/text/image",
            json=payload,
            headers=headers,
            timeout=60,
        )

        if resp.status_code != 200:
            logger.error(
                f"[VisualAsset] MiniMax API错误: {resp.status_code}"
            )
            return None

        img_url = resp.json().get("data", {}).get("image_url")
        if not img_url:
            return None

        output_path = str(output_dir / f"{style}_minimax.png")
        img_resp = requests.get(img_url, timeout=60)
        with open(output_path, "wb") as f:
            f.write(img_resp.content)

        return output_path

    def _generate_pillow_card(
        self, text: str, style: str, output_dir: Path
    ) -> Optional[str]:
        """降级方案：使用Pillow生成简约风格卡片"""
        from PIL import Image, ImageDraw, ImageFont

        size_map = {
            "thumbnail": (1280, 720),
            "xhs_card": (1080, 1440),
            "tiktok_cover": (720, 1280),
        }
        width, height = size_map.get(style, (1280, 720))

        # 创建渐变背景
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # 渐变色: 深紫→深蓝
        for y in range(height):
            ratio = y / height
            r = int(30 + ratio * 10)
            g = int(10 + ratio * 20)
            b = int(60 + ratio * 40)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 添加文字
        display_text = text[:30]
        if len(text) > 30:
            display_text += "..."

        # 尝试加载字体，降级到默认
        try:
            font = ImageFont.truetype("SimHei", size=min(width, height) // 15)
        except (OSError, IOError):
            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                    size=min(width, height) // 15,
                )
            except (OSError, IOError):
                font = ImageFont.load_default()

        # 居中绘制
        bbox = draw.textbbox((0, 0), display_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        x = (width - text_w) // 2
        y = (height - text_h) // 2

        # 文字阴影
        draw.text((x + 2, y + 2), display_text, fill=(0, 0, 0), font=font)
        draw.text((x, y), display_text, fill=(255, 255, 255), font=font)

        output_path = str(output_dir / f"{style}_card.png")
        img.save(output_path, "PNG")

        logger.info(f"[VisualAsset] Pillow卡片生成: {output_path}")
        return output_path
