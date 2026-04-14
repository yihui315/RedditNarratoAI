"""
Vanilla RAG 知识库 - 爆款解说模板库
========================================
用于：
- 写脚本前的风格检索
- 标题生成
- 结尾CTA生成
- 封面文案

不依赖 embedding 模型，用关键词 + BM25 轻量检索
"""

import json
import math
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── 内置知识库 ─────────────────────────────────────────────────────────────

BUILTIN_TEMPLATES = {
    "hooks": [
        {
            "id": "hook_001",
            "text": "就在所有人以为结局已定时，导演用最后三分钟，彻底颠覆了你的认知。",
            "style": "悬疑反转",
            "platform": "通用",
            "tags": ["反转", "结局", "震撼", "悬疑"],
            "avg_ctr": 0.82,
        },
        {
            "id": "hook_002",
            "text": "这个男人，每天都会杀掉自己的妻子一次。听起来疯狂？但第九集之后，你会开始同情他。",
            "style": "悬疑反转",
            "platform": "抖音/快手",
            "tags": ["悬疑", "惊悚", "丈夫", "妻子", "开局即冲突"],
            "avg_ctr": 0.88,
        },
        {
            "id": "hook_003",
            "text": "她等了丈夫二十年。二十年里，他从没回过一条消息。结局揭示的那天，全网都哭了。",
            "style": "强狗血",
            "platform": "抖音/快手",
            "tags": ["爱情", "等待", "反转", "催泪"],
            "avg_ctr": 0.85,
        },
        {
            "id": "hook_004",
            "text": "从被人踩在脚底，到让整座城市颤抖，他只用了这一部电影的时间。",
            "style": "爽文逆袭",
            "platform": "抖音/快手",
            "tags": ["逆袭", "爽文", "翻身", "热血"],
            "avg_ctr": 0.79,
        },
        {
            "id": "hook_005",
            "text": "这部电影没有一个好人，但每个角色都会让你想起自己。",
            "style": "文艺深刻",
            "platform": "B站",
            "tags": ["人性", "深刻", "文艺", "共鸣"],
            "avg_ctr": 0.74,
        },
    ],
    "titles": [
        {
            "id": "title_001",
            "text": "结局反转震撼到失眠的5部电影 | 最后一部90%的人没猜到",
            "style": "悬疑反转",
            "platform": "抖音",
            "tags": ["反转", "结局", "悬疑", "推荐"],
            "views": "500万+",
        },
        {
            "id": "title_002",
            "text": "看完这5部爽片，治好了我一年的精神内耗",
            "style": "爽文逆袭",
            "platform": "抖音",
            "tags": ["逆袭", "解压", "爽片", "治愈"],
            "views": "800万+",
        },
        {
            "id": "title_003",
            "text": "她以为自己是第三者，没想到是小四：这部泰剧狗血到离谱",
            "style": "强狗血",
            "platform": "快手",
            "tags": ["狗血", "泰剧", "出轨", "第三者"],
            "views": "300万+",
        },
        {
            "id": "title_004",
            "text": "如果可以重启人生，你会选择不同的路吗？",
            "style": "文艺深刻",
            "platform": "B站",
            "tags": ["人生", "选择", "深刻", "文艺"],
            "views": "200万+",
        },
    ],
    "cta_endings": [
        {
            "id": "cta_001",
            "text": "觉得有意思？点个关注，下期更精彩。",
            "style": "通用",
            "platform": "通用",
        },
        {
            "id": "cta_002",
            "text": "这个结局你猜到了吗？评论区告诉我。",
            "style": "悬疑反转",
            "platform": "通用",
        },
        {
            "id": "cta_003",
            "text": "觉得爽的话三连，我们下期见。",
            "style": "爽文逆袭",
            "platform": "抖音/快手",
        },
        {
            "id": "cta_004",
            "text": "如果你也喜欢这类题材，欢迎关注，我会持续更新。",
            "style": "文艺深刻",
            "platform": "B站",
        },
    ],
    "pacing_rules": [
        {
            "id": "rule_001",
            "style": "悬疑反转",
            "rule": "每30秒一个小悬念，每90秒一个中等悬念，每段结尾一个大悬念",
            "hook_first_n_sec": 20,
            "avg_sentence_duration_sec": 4.5,
            "max_sentence_duration_sec": 7,
        },
        {
            "id": "rule_002",
            "style": "强狗血",
            "rule": "情绪不断叠加，冲突连续升级，每句话都在制造张力",
            "hook_first_n_sec": 15,
            "avg_sentence_duration_sec": 3.5,
            "max_sentence_duration_sec": 6,
        },
        {
            "id": "rule_003",
            "style": "爽文逆袭",
            "rule": "前半段压（抑），后半段扬（爆），节奏类似股票K线",
            "hook_first_n_sec": 25,
            "avg_sentence_duration_sec": 5.0,
            "max_sentence_duration_sec": 8,
        },
    ],
}


class KnowledgeBase:
    """
    轻量 RAG 知识库

    BM25 关键词检索，无需 embedding 模型
    支持自定义添加模板（持久化到本地 JSON）
    """

    def __init__(self, custom_db_path: str = None):
        self.db_path = custom_db_path
        self._db: Dict[str, List] = {**BUILTIN_TEMPLATES}
        if custom_db_path and os.path.exists(custom_db_path):
            self._load()

    def _load(self):
        with open(self.db_path, encoding="utf-8") as f:
            extra = json.load(f)
        for key, items in extra.items():
            if key in self._db:
                self._db[key].extend(items)
            else:
                self._db[key] = items

    def save(self):
        if self.db_path:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self._db, f, ensure_ascii=False, indent=2)

    def add_template(self, category: str, template: Dict):
        """添加自定义模板"""
        if category not in self._db:
            self._db[category] = []
        # 去重
        existing_ids = {t.get("id") for t in self._db[category]}
        if template.get("id") not in existing_ids:
            self._db[category].append(template)
            self.save()

    def retrieve(
        self,
        query: str,
        category: str = "hooks",
        top_k: int = 3,
        style: str = None,
        platform: str = None,
    ) -> List[Dict]:
        """
        BM25 检索

        Args:
            query: 查询文本（旁白/主题/类型描述）
            category: 模板类别 ("hooks", "titles", "cta_endings", "pacing_rules")
            top_k: 返回前k条
            style: 风格过滤
            platform: 平台过滤

        Returns:
            按相关性排序的模板列表
        """
        items = self._db.get(category, [])
        if not items:
            return []

        # BM25 scoring
        query_terms = self._tokenize(query)
        scored = []
        for item in items:
            # Apply filters
            if style and item.get("style") and style not in item.get("style", ""):
                continue
            if platform and platform not in item.get("platform", ""):
                continue

            # BM25
            score = self._bm25(query_terms, item)
            scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]

    def retrieve_hook(self, query: str, style: str = None, top_k: int = 3) -> List[Dict]:
        return self.retrieve(query, "hooks", top_k, style=style)

    def retrieve_title(self, query: str, style: str = None, top_k: int = 5) -> List[Dict]:
        return self.retrieve(query, "titles", top_k, style=style)

    def get_pacing_rule(self, style: str) -> Optional[Dict]:
        rules = self._db.get("pacing_rules", [])
        for r in rules:
            if r.get("style") == style:
                return r
        return rules[0] if rules else None

    # ── BM25 实现 ─────────────────────────────────────────────────────────

    AVG_DOC_LEN = 50  # 平均文档 token 数（估算）

    def _tokenize(self, text: str) -> List[str]:
        """简单分词：中文按字符，英文按空格"""
        text = text.lower()
        chinese = re.findall(r"[\u4e00-\u9fff]+", text)
        english = re.findall(r"[a-z0-9]+", text)
        tokens = []
        for chunk in chinese:
            tokens.extend(list(chunk))  # 每字一token
        tokens.extend(english)
        return tokens

    def _bm25(self, query_terms: List[str], item: Dict) -> float:
        """BM25 评分"""
        if not query_terms:
            return 0.0
        text = json.dumps(item, ensure_ascii=False).lower()
        doc_terms = self._tokenize(text)
        doc_len = len(doc_terms)
        k1, b = 1.5, 0.75

        score = 0.0
        for term in query_terms:
            tf = doc_terms.count(term)
            if tf == 0:
                continue
            # IDF（简化版）
            idf = math.log((len(self._db.get("hooks", [item])) + 1) / (tf + 1))
            term_freq = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / self.AVG_DOC_LEN))
            score += idf * term_freq
        return score
