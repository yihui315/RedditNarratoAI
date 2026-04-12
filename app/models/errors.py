"""Structured pipeline error types with user-friendly messages and fix suggestions."""


class PipelineError(Exception):
    """Base error for all pipeline failures."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "视频生成流程出错",
        fix_suggestion: str = "请检查日志获取详细信息",
    ):
        self.detail = detail
        self.user_message = user_message
        self.fix_suggestion = fix_suggestion
        super().__init__(detail or user_message)

    def __str__(self) -> str:
        return f"{self.user_message}\n💡 {self.fix_suggestion}"


class ConfigError(PipelineError):
    """Configuration issues: missing API keys, invalid config values, etc."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "配置项缺失或无效",
        fix_suggestion: str = "请检查config.toml文件，确认所有必填配置项已正确填写",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


class NetworkError(PipelineError):
    """Network and API connectivity issues."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "网络连接失败",
        fix_suggestion: str = "请检查网络连接，确认代理设置正确，然后重试",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


class LLMError(PipelineError):
    """LLM API failures: rate limits, timeouts, invalid responses."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "LLM接口调用失败",
        fix_suggestion: str = "请确认API密钥有效且有额度，稍后重试或更换模型",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


class TTSError(PipelineError):
    """TTS generation failures."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "语音合成失败",
        fix_suggestion: str = "请检查TTS服务配置，确认语音引擎可用",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


class VideoError(PipelineError):
    """Video generation failures."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "视频生成失败",
        fix_suggestion: str = "请检查素材文件是否完整，确认FFmpeg已正确安装",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


class RedditError(PipelineError):
    """Reddit API failures."""

    def __init__(
        self,
        detail: str = "",
        user_message: str = "Reddit内容获取失败",
        fix_suggestion: str = "请检查Reddit API凭据配置，确认网络可访问Reddit",
    ):
        super().__init__(detail=detail, user_message=user_message, fix_suggestion=fix_suggestion)


def format_user_error(error: Exception) -> str:
    """Format any exception into a user-friendly message string.

    - PipelineError subtypes: returns user_message + fix_suggestion.
    - ConnectionError / TimeoutError: wraps into a NetworkError-style message.
    - All others: returns a generic unknown-error message.
    """
    if isinstance(error, PipelineError):
        return str(error)

    if isinstance(error, (ConnectionError, TimeoutError)):
        wrapped = NetworkError(detail=str(error))
        return str(wrapped)

    return f"发生未知错误: {error}"
