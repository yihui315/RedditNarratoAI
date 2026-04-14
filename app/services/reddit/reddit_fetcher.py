"""
Reddit数据获取模块 - 来自RedditVideoMakerBotreddit/subreddit.py
简化版，不依赖原项目utils，直接使用PRAW
"""

import re
from dataclasses import dataclass, field
from typing import Optional
import praw
from praw.models import MoreComments


@dataclass
class RedditContent:
    """Reddit内容数据结构"""
    thread_url: str = ""
    thread_title: str = ""
    thread_id: str = ""
    thread_post: str = ""  # 帖子的正文内容（storymode时）
    is_nsfw: bool = False
    upvotes: int = 0
    upvote_ratio: float = 0.0
    num_comments: int = 0
    comments: list = field(default_factory=list)  # [{"comment_body", "comment_url", "comment_id"}]


class RedditFetcher:
    """
    Reddit数据获取器
    支持: Subreddit、Post链接、Post ID
    """
    
    def __init__(self, config: dict):
        """
        初始化Reddit fetcher
        
        Args:
            config: 配置字典，包含reddit.creds
        """
        self.config = config
        self.reddit = None
        
    def connect(self) -> bool:
        """连接Reddit API"""
        creds = self.config.get("reddit", {}).get("creds", {})
        
        try:
            self.reddit = praw.Reddit(
                client_id=creds.get("client_id"),
                client_secret=creds.get("client_secret"),
                user_agent="RedditNarratoAI/1.0",
                username=creds.get("username", ""),
                password=creds.get("password", ""),
                check_for_async=False,
            )
            # 验证连接
            self.reddit.user.me()
            return True
        except Exception as e:
            print(f"Reddit连接失败: {e}")
            return False
    
    def fetch_by_url(self, url: str) -> Optional[RedditContent]:
        """
        通过URL获取Reddit帖子内容
        
        Args:
            url: Reddit帖子URL，如:
                 - https://reddit.com/r/AskReddit/comments/abc123
                 - https://www.reddit.com/r/AskReddit/comments/abc123/
                 - r/AskReddit/abc123
                 - abc123 (post ID)
        """
        if not self.reddit:
            if not self.connect():
                return None
        
        # 解析URL/ID
        post_id = self._extract_post_id(url)
        if not post_id:
            print(f"无法解析Post ID from: {url}")
            return None
        
        try:
            submission = self.reddit.submission(id=post_id)
            return self._parse_submission(submission)
        except Exception as e:
            print(f"获取帖子失败: {e}")
            return None
    
    def fetch_by_subreddit(
        self, 
        subreddit_name: str, 
        sort: str = "hot",
        limit: int = 10
    ) -> list:
        """
        获取Subreddit帖子列表
        
        Args:
            subreddit_name: Subreddit名称（不含r/）
            sort: 排序方式 hot/new/top/rising
            limit: 获取数量
        """
        if not self.reddit:
            if not self.connect():
                return []
        
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            if sort == "hot":
                posts = subreddit.hot(limit=limit)
            elif sort == "new":
                posts = subreddit.new(limit=limit)
            elif sort == "top":
                posts = subreddit.top(limit=limit)
            else:
                posts = subreddit.rising(limit=limit)
            
            results = []
            for post in posts:
                results.append({
                    "id": post.id,
                    "title": post.title,
                    "url": f"https://reddit.com{post.permalink}",
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "created_utc": post.created_utc,
                })
            return results
        except Exception as e:
            print(f"获取Subreddit失败: {e}")
            return []
    
    def _extract_post_id(self, url_or_id: str) -> Optional[str]:
        """从URL或ID中提取post ID"""
        # 直接是ID
        if len(url_or_id) <= 6 and re.match(r'^[a-zA-Z0-9]+$', url_or_id):
            return url_or_id
        
        # r/xxx/xxx 格式
        match = re.search(r'r/\w+/comments/([a-zA-Z0-9]+)', url_or_id)
        if match:
            return match.group(1)
        
        # 仅 post ID
        match = re.search(r'comments/([a-zA-Z0-9]+)', url_or_id)
        if match:
            return match.group(1)
        
        return None
    
    def _parse_submission(self, submission) -> RedditContent:
        """解析Reddit submission为RedditContent"""
        content = RedditContent()
        content.thread_url = f"https://reddit.com{submission.permalink}"
        content.thread_title = submission.title
        content.thread_id = submission.id
        content.is_nsfw = submission.over_18
        content.upvotes = submission.score
        content.upvote_ratio = submission.upvote_ratio
        content.num_comments = submission.num_comments
        content.thread_post = submission.selftext
        
        # 解析评论
        submission.comments.replace_more(limit=3)  # 最多展开3层
        for comment in submission.comments:
            if isinstance(comment, MoreComments):
                continue
            if comment.body in ["[removed]", "[deleted]"]:
                continue
            if self._contains_blocked_words(comment.body):
                continue  # 跳过含屏蔽词的评论

            content.comments.append({
                "comment_body": comment.body,
                "comment_url": f"https://reddit.com{comment.permalink}",
                "comment_id": comment.id,
                "author": str(comment.author) if comment.author else "[deleted]",
                "score": comment.score,
            })
        
        return content

    def _contains_blocked_words(self, text: str) -> bool:
        """检查文本是否含配置中的屏蔽词"""
        blocked_raw = self.config.get("reddit", {}).get("blocked_words", "")
        if not blocked_raw:
            return False
        blocked = [w.strip().lower() for w in blocked_raw.split(",") if w.strip()]
        if not blocked:
            return False
        text_lower = text.lower()
        return any(word in text_lower for word in blocked)

    def get_askreddit_story(self, post_id: str) -> Optional[RedditContent]:
        """
        获取AskReddit风格的帖子，用于故事模式
        帖子本身是问题，评论是回答
        """
        return self.fetch_by_url(post_id)


def fetch_reddit_content(config: dict, url_or_id: str) -> Optional[RedditContent]:
    """
    便捷函数：直接获取Reddit内容
    """
    fetcher = RedditFetcher(config)
    return fetcher.fetch_by_url(url_or_id)
