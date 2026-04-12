"""
爆款文案Prompt模板库
支持多种风格预设，为不同类型的内容提供优化的Prompt模板
"""

from typing import Dict

# 风格预设：每种风格包含 system_prompt + user_prompt_template + 情绪节奏标注
STYLE_PRESETS: Dict[str, dict] = {
    "suspense": {
        "name": "悬疑",
        "system_prompt": "你是一个专业的悬疑解说博主，擅长制造紧张氛围和悬念，让观众欲罢不能。",
        "opening_hooks": [
            "当{角色}推开那扇门的时候，所有人都屏住了呼吸……",
            "这个案件，整整{数字}年没人敢碰，直到{角色}的出现……",
            "千万不要在深夜独自看这个故事，因为结局会让你后背发凉……",
        ],
        "emotion_guide": "全程保持低沉神秘，关键转折处突然加速，结尾留悬念",
        "tts_rate_pattern": ["-10%", "-10%", "+0%", "+0%", "+10%", "-5%"],
        "tts_pitch_pattern": ["-5Hz", "-5Hz", "+0Hz", "+5Hz", "+10Hz", "-5Hz"],
    },
    "humor": {
        "name": "搞笑",
        "system_prompt": "你是一个幽默风趣的解说博主，擅长用夸张的语气和出人意料的吐槽逗观众笑。",
        "opening_hooks": [
            "我打赌你看完这个故事，下巴一定合不上……",
            "你见过最离谱的事是什么？听完这个你会刷新认知……",
            "这是我今年听过最炸裂的故事，没有之一！",
        ],
        "emotion_guide": "语气活泼，适当夸张，吐槽要犀利但不刻薄",
        "tts_rate_pattern": ["+5%", "+5%", "+10%", "+0%", "+10%", "+5%"],
        "tts_pitch_pattern": ["+5Hz", "+5Hz", "+10Hz", "+0Hz", "+10Hz", "+5Hz"],
    },
    "shock": {
        "name": "震惊",
        "system_prompt": "你是一个擅长制造震撼效果的解说博主，用惊人的数据和反转抓住观众眼球。",
        "opening_hooks": [
            "万万没想到，一个普通的{角色}，竟然做出了这种事……",
            "全网{数字}万人看呆了！这事儿你敢信吗？",
            "如果不是亲眼所见，我绝对不会相信世界上还有这种操作……",
        ],
        "emotion_guide": "开头就炸裂，中间步步惊心，结尾再来一个反转",
        "tts_rate_pattern": ["+10%", "+0%", "+5%", "+0%", "+10%", "+5%"],
        "tts_pitch_pattern": ["+10Hz", "+0Hz", "+5Hz", "+5Hz", "+10Hz", "+5Hz"],
    },
    "warm": {
        "name": "温情",
        "system_prompt": "你是一个善于讲述温暖故事的解说博主，能用细腻的笔触打动人心。",
        "opening_hooks": [
            "这是一个关于{角色}的故事，平凡却让无数人泪目……",
            "在这个浮躁的世界里，还有人愿意为了{目标}默默坚持……",
            "看完这个故事，我在屏幕前哭了整整三分钟……",
        ],
        "emotion_guide": "娓娓道来，情感递进，高潮处放慢语速让情绪沉淀",
        "tts_rate_pattern": ["+0%", "-5%", "-5%", "+0%", "-10%", "-5%"],
        "tts_pitch_pattern": ["+0Hz", "+0Hz", "-5Hz", "+0Hz", "-5Hz", "+0Hz"],
    },
    "educational": {
        "name": "科普",
        "system_prompt": "你是一个知识渊博的科普解说博主，擅长把复杂的概念讲得通俗易懂又有趣。",
        "opening_hooks": [
            "你知道{主题}背后隐藏的真相是什么吗？",
            "99%的人都不知道，{主题}其实是这样的……",
            "今天聊一个细思极恐的知识点，关于{主题}……",
        ],
        "emotion_guide": "语速适中，重点概念稍慢，用类比让抽象概念具象化",
        "tts_rate_pattern": ["+5%", "+0%", "-5%", "+0%", "+0%", "+0%"],
        "tts_pitch_pattern": ["+0Hz", "+0Hz", "+0Hz", "+0Hz", "+0Hz", "+0Hz"],
    },
}

# 默认风格
DEFAULT_STYLE = "shock"


def get_style_names() -> list:
    """返回所有可用的风格名称列表"""
    return [(k, v["name"]) for k, v in STYLE_PRESETS.items()]


def get_prompt_template(style: str = DEFAULT_STYLE) -> dict:
    """获取指定风格的Prompt模板"""
    return STYLE_PRESETS.get(style, STYLE_PRESETS[DEFAULT_STYLE])


def build_reddit_prompt(
    title: str,
    post_content: str,
    comments_text: str = "",
    style: str = DEFAULT_STYLE,
    use_story_mode: bool = True,
    target_duration: str = "2-4分钟",
) -> tuple:
    """
    构建Reddit视频的完整Prompt

    Args:
        title: 帖子标题
        post_content: 帖子内容
        comments_text: 评论文本
        style: 风格预设
        use_story_mode: 是否故事模式
        target_duration: 目标时长

    Returns:
        (system_prompt, user_prompt)
    """
    preset = get_prompt_template(style)
    system_prompt = preset["system_prompt"]

    if use_story_mode and comments_text:
        user_prompt = f"""请将下面的内容改写成吸引人的解说文案。

原始标题: {title}
原始内容: {post_content or '无'}

精彩回复:
{comments_text}

## 创作要求:
1. **开头3句必须炸裂**——用冲突、悬念或反问直接抓住观众（参考爆款开头风格）
2. 文案朗读时长{target_duration}，全程口语化
3. 将回复中的精彩内容自然融入解说
4. 语言生动有画面感，像朋友在讲一个刚听来的猛料
5. 不要出现"帖子""评论""网友"等词，用"他""这个人""故事"代替
6. 段落之间用换行分隔，每段2-3句话，便于配音节奏控制
7. 关键转折处用短句 + 感叹号制造节奏感
8. 结尾要有余韵或反思，让人意犹未尽

## 情绪节奏:
{preset['emotion_guide']}

请直接输出解说文案，不要加标题或说明:
"""
    else:
        user_prompt = f"""请将下面的内容改写成吸引人的解说文案。

原始标题: {title}
原始内容: {post_content or '无'}

## 创作要求:
1. **开头3句必须炸裂**——用冲突、悬念或反问直接抓住观众
2. 文案朗读时长{target_duration}，全程口语化
3. 语言生动有画面感，适合朗读
4. 段落之间用换行分隔，每段2-3句话
5. 关键转折处用短句 + 感叹号制造节奏感
6. 结尾要有余韵

## 情绪节奏:
{preset['emotion_guide']}

请直接输出解说文案，不要加标题或说明:
"""

    return system_prompt, user_prompt


def get_tts_params_for_paragraph(
    paragraph_index: int,
    total_paragraphs: int,
    style: str = DEFAULT_STYLE,
    base_rate: str = "+0%",
    base_pitch: str = "+0Hz",
) -> dict:
    """
    根据段落位置和风格，返回该段落的TTS参数

    Args:
        paragraph_index: 当前段落索引
        total_paragraphs: 总段落数
        style: 风格预设
        base_rate: 基础语速
        base_pitch: 基础音调

    Returns:
        dict: {"rate": str, "pitch": str}
    """
    preset = get_prompt_template(style)
    rate_pattern = preset.get("tts_rate_pattern", ["+0%"] * 6)
    pitch_pattern = preset.get("tts_pitch_pattern", ["+0Hz"] * 6)

    # 将段落位置映射到6段式节奏
    if total_paragraphs <= 0:
        total_paragraphs = 1
    position_ratio = paragraph_index / total_paragraphs
    pattern_index = min(int(position_ratio * len(rate_pattern)), len(rate_pattern) - 1)

    return {
        "rate": rate_pattern[pattern_index],
        "pitch": pitch_pattern[pattern_index],
    }
