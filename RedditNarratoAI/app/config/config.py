"""
RedditNarratoAI 配置模块
简单版本，避免循环引用
"""

import os
import toml
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent.parent.absolute()
CONFIG_FILE = ROOT_DIR / "config.toml"


class Config:
    """配置类"""
    
    def __init__(self):
        self._config = {}
        self.load()
    
    def load(self):
        """加载配置"""
        if CONFIG_FILE.exists():
            try:
                self._config = toml.load(CONFIG_FILE)
            except Exception as e:
                print(f"加载配置失败: {e}")
                self._config = self._default_config()
        else:
            self._config = self._default_config()
    
    def _default_config(self):
        """默认配置"""
        return {
            "app": {
                "name": "RedditNarratoAI",
                "version": "0.1.0",
                "debug": False,
                "output_dir": "./output"
            },
            "reddit": {
                "creds": {}
            },
            "llm": {
                "provider": "openai",
                "api_base": "http://localhost:11434/v1",
                "api_key": "not-needed",
                "model": "deepseek-r1:32b",
                "max_tokens": 4096,
                "temperature": 0.7
            },
            "tts": {
                "provider": "edge",
                "voice": "zh-CN-XiaoxiaoNeural",
                "rate": "+0%",
                "pitch": "+0Hz",
                "volume": "+0%"
            },
            "video": {
                "width": 1920,
                "height": 1080,
                "fps": 30
            },
            "subtitle": {
                "font": "SimHei",
                "font_size": 36,
                "color": "#FFFFFF"
            }
        }
    
    def get(self, key, default=None):
        """获取配置，支持点号分隔的路径如 'reddit.creds.client_id'"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value
    
    def __getitem__(self, key):
        return self.get(key)
    
    def __contains__(self, key):
        return self.get(key) is not None
    
    @property
    def log_level(self):
        return "INFO"


# 全局配置实例
config = Config()
