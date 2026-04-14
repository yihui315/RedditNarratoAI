"""
JSON Schema 定义 - 整个系统的统一数据格式
所有时间戳格式: "HH:MM:SS.mmm" (SRT标准格式)
所有路径: 相对于 work_dir 或绝对路径
"""

# ── 1. transcript.json ──────────────────────────────────────────────────────
# 输入: WhisperX 转写输出
# 格式: SRT时间格式
TRANSCRIPT_SCHEMA = {
    "type": "object",
    "required": ["transcript"],
    "properties": {
        "transcript": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["start", "end", "text"],
                "properties": {
                    "start": {"type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}\\.\\d{3}$"},
                    "end":   {"type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}\\.\\d{3}$"},
                    "text":  {"type": "string"}
                }
            }
        }
    }
}

# ── 2. scenes.json ─────────────────────────────────────────────────────────
# 输入: PySceneDetect 镜头检测
SCENES_SCHEMA = {
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene_id", "start", "end"],
                "properties": {
                    "scene_id": {"type": "integer"},
                    "start":    {"type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}$"},
                    "end":      {"type": "string", "pattern": "^\\d{2}:\\d{2}:\\d{2}$"},
                    "description": {"type": "string"}
                }
            }
        }
    }
}

# ── 3. chapter_draft.json ───────────────────────────────────────────────────
# 输入: qw3.6 (Ollama) - 基于 transcript + scenes 生成章节草稿
CHAPTER_DRAFT_SCHEMA = {
    "type": "object",
    "required": ["chapters"],
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "start_scene", "end_scene", "summary", "characters", "key_events"],
                "properties": {
                    "id":          {"type": "integer"},
                    "start_scene": {"type": "integer"},
                    "end_scene":   {"type": "integer"},
                    "summary":     {"type": "string"},
                    "characters":  {"type": "array", "items": {"type": "string"}},
                    "key_events": {"type": "array", "items": {"type": "string"}}
                }
            }
        }
    }
}

# ── 4. chapter_refined.json ─────────────────────────────────────────────────
# 输入: gemma4 (Ollama) - 精化章节，提升质量
CHAPTER_REFINED_SCHEMA = {
    "type": "object",
    "required": ["chapters"],
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "summary", "main_conflict", "importance_score"],
                "properties": {
                    "id":              {"type": "integer"},
                    "summary":         {"type": "string"},
                    "main_conflict":   {"type": "string"},
                    "importance_score": {"type": "number", "minimum": 0, "maximum": 1}
                }
            }
        }
    }
}

# ── 5. outline.json ─────────────────────────────────────────────────────────
# 输入: DeepSeek API - 生成三段式解说大纲
OUTLINE_SCHEMA = {
    "type": "object",
    "required": ["part1", "part2", "part3"],
    "properties": {
        "part1": {
            "type": "object",
            "required": ["theme", "hook", "key_points", "ending_hook"],
            "properties": {
                "theme":       {"type": "string"},
                "hook":        {"type": "string"},
                "key_points":  {"type": "array", "items": {"type": "string"}},
                "ending_hook": {"type": "string"}
            }
        },
        "part2": {
            "type": "object",
            "required": ["theme", "hook", "key_points", "ending_hook"],
            "properties": {
                "theme":       {"type": "string"},
                "hook":        {"type": "string"},
                "key_points":  {"type": "array", "items": {"type": "string"}},
                "ending_hook": {"type": "string"}
            }
        },
        "part3": {
            "type": "object",
            "required": ["theme", "hook", "key_points", "ending_hook"],
            "properties": {
                "theme":       {"type": "string"},
                "hook":        {"type": "string"},
                "key_points":  {"type": "array", "items": {"type": "string"}},
                "ending_hook": {"type": "string"}
            }
        }
    }
}

# ── 6. script_part.json ─────────────────────────────────────────────────────
# 输入: MiniMax API - 生成单段解说脚本（一段 = 一整段视频的旁白）
SCRIPT_PART_SCHEMA = {
    "type": "object",
    "required": ["paragraph_text", "sentences"],
    "properties": {
        "paragraph_text": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "text", "estimated_duration_sec"],
                "properties": {
                    "id":                      {"type": "integer"},
                    "text":                    {"type": "string"},
                    "estimated_duration_sec":  {"type": "number"}
                }
            }
        }
    }
}

# ── 7. script_review.json ───────────────────────────────────────────────────
# 输入: gemma4 (Ollama) - 脚本质量审核
SCRIPT_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["issues", "score"],
    "properties": {
        "issues": {"type": "array", "items": {"type": "string"}},
        "score":  {"type": "number", "minimum": 0, "maximum": 10}
    }
}

# ── 8. final_script.json ───────────────────────────────────────────────────
# 输入: DeepSeek API - 修复问题后的最终脚本
FINAL_SCRIPT_SCHEMA = {
    "type": "object",
    "required": ["sentences"],
    "properties": {
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "text", "duration"],
                "properties": {
                    "id":       {"type": "integer"},
                    "text":     {"type": "string"},
                    "duration": {"type": "number"}
                }
            }
        }
    }
}

# ── 9. scene_prompts.json ───────────────────────────────────────────────────
# 输入: MiniMax API - 为每句旁白生成 HyDE 镜头检索提示
SCENE_PROMPTS_SCHEMA = {
    "type": "object",
    "required": ["scene_prompts"],
    "properties": {
        "scene_prompts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["sentence_id", "prompt"],
                "properties": {
                    "sentence_id": {"type": "integer"},
                    "prompt":      {"type": "string"}
                }
            }
        }
    }
}

# ── 10. render_manifest.json ────────────────────────────────────────────────
# 输入: 所有阶段输出 - 生成 FFmpeg 渲染指令
RENDER_MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["clips", "audio_file", "subtitle_file"],
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene_id", "start", "end"],
                "properties": {
                    "scene_id": {"type": "integer"},
                    "start":    {"type": "string"},
                    "end":      {"type": "string"}
                }
            }
        },
        "audio_file":    {"type": "string"},
        "subtitle_file": {"type": "string"}
    }
}
