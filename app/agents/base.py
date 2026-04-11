"""
Agent基类 - 所有Agent的抽象基础
Boris原则: 封装可复用、Verification Loop
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from loguru import logger


@dataclass
class AgentResult:
    """Agent执行结果"""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    agent_name: str = ""
    duration_seconds: float = 0.0
    retries: int = 0


class BaseAgent(ABC):
    """
    Agent抽象基类

    每个Agent必须实现:
    - run(): 核心执行逻辑
    - verify(): 验证输出是否合法（Verification Loop）
    """

    def __init__(self, config: dict, name: str = ""):
        self.config = config
        self.name = name or self.__class__.__name__
        self.agent_id = f"{self.name}_{uuid.uuid4().hex[:6]}"
        self.max_retries = config.get("agents", {}).get("max_retries", 3)

    @abstractmethod
    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """核心执行逻辑，子类必须实现"""
        ...

    @abstractmethod
    def verify(self, result: AgentResult) -> bool:
        """验证结果是否有效，子类必须实现"""
        ...

    def execute(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        带Verification Loop的执行入口

        自动重试直到verify通过或达到max_retries
        """
        start = time.time()
        last_result = AgentResult(success=False, agent_name=self.name)

        for attempt in range(1, self.max_retries + 1):
            logger.info(f"[{self.agent_id}] 第{attempt}次执行...")
            try:
                result = self.run(input_data)
                result.agent_name = self.name
                result.retries = attempt

                if self.verify(result):
                    result.duration_seconds = time.time() - start
                    logger.info(
                        f"[{self.agent_id}] 验证通过 "
                        f"(耗时 {result.duration_seconds:.1f}s, "
                        f"重试 {attempt - 1} 次)"
                    )
                    return result

                logger.warning(
                    f"[{self.agent_id}] 第{attempt}次验证未通过，重试..."
                )
                last_result = result

            except Exception as e:
                logger.error(f"[{self.agent_id}] 第{attempt}次执行出错: {e}")
                last_result = AgentResult(
                    success=False,
                    error=str(e),
                    agent_name=self.name,
                    retries=attempt,
                )

        last_result.duration_seconds = time.time() - start
        logger.error(
            f"[{self.agent_id}] 达到最大重试次数 {self.max_retries}，最终失败"
        )
        return last_result
