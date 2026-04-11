"""
Agent v4.0: DailyOperator — 每日操盘手Supervisor
一键启动全流程:
  选题(TopicEngine) → 文案(ScriptWriter) → 诊断(ReviewDiagnosis)
  → 内容日历排期 → 批量生产

灵感来源: binghe Agent 的 ~daily 功能
"""

import json
import os
import time
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from app.agents.base import BaseAgent, AgentResult


class DailyOperatorAgent(BaseAgent):
    """
    每日操盘手Supervisor Agent

    输入: 运行配置（批量数/模式/是否需要人工确认）
    输出: 完整的每日内容计划 + 内容日历
    """

    def __init__(self, config: dict):
        super().__init__(config, name="DailyOperator")
        root_dir = config.get("app", {}).get("root_dir", ".")
        self.calendar_dir = os.path.join(root_dir, "config", "content-calendar")
        os.makedirs(self.calendar_dir, exist_ok=True)

    def run(self, input_data: Dict[str, Any]) -> AgentResult:
        """
        input_data keys:
            batch_size (int): 每日产出数量（默认5）
            topic_mode (str): 选题模式 (hot/mine/rival/flash)
            persona (dict): 创作者画像
            topics (list): 已选好的选题（可选，跳过选题步骤）
            scripts (list): 已写好的文案（可选，跳过文案步骤）
            auto_mode (bool): 全自动模式（无人工确认）
        """
        batch_size = input_data.get("batch_size", 5)
        topic_mode = input_data.get("topic_mode", "hot")
        persona = input_data.get("persona", {})
        pre_topics = input_data.get("topics", [])
        pre_scripts = input_data.get("scripts", [])
        auto_mode = input_data.get("auto_mode", True)

        daily_plan = {
            "date": time.strftime("%Y-%m-%d"),
            "batch_size": batch_size,
            "topic_mode": topic_mode,
            "status": "planned",
            "topics": pre_topics,
            "scripts": pre_scripts,
            "reviews": [],
            "calendar_entries": [],
        }

        # Phase 1: Topic Selection (if not pre-provided)
        if not pre_topics:
            daily_plan["topics"] = self._generate_placeholder_topics(
                batch_size, topic_mode, persona
            )

        # Phase 2: Script Outline (if not pre-provided)
        if not pre_scripts:
            daily_plan["scripts"] = [
                {
                    "topic_index": i,
                    "title": t.get("title", f"选题{i+1}"),
                    "status": "pending_generation",
                }
                for i, t in enumerate(daily_plan["topics"][:batch_size])
            ]

        # Phase 3: Generate calendar entries
        daily_plan["calendar_entries"] = self._generate_calendar(
            daily_plan["topics"][:batch_size]
        )

        # Phase 4: Save daily plan
        plan_path = self._save_daily_plan(daily_plan)

        daily_plan["status"] = "ready"

        return AgentResult(
            success=True,
            data={
                "daily_plan": daily_plan,
                "plan_path": plan_path,
                "topic_count": len(daily_plan["topics"]),
                "auto_mode": auto_mode,
                "next_steps": self._get_next_steps(daily_plan, auto_mode),
            },
        )

    def verify(self, result: AgentResult) -> bool:
        """验证: 日计划必须有至少1个选题和日历条目"""
        if not result.success:
            return False
        plan = result.data.get("daily_plan", {})
        has_topics = len(plan.get("topics", [])) > 0
        has_calendar = len(plan.get("calendar_entries", [])) > 0
        return has_topics and has_calendar

    def _generate_placeholder_topics(
        self, count: int, mode: str, persona: dict
    ) -> List[dict]:
        """生成占位选题（实际由TopicEngine填充）"""
        niche = persona.get("niche", "短剧解说")
        return [
            {
                "title": f"待生成选题 {i+1}",
                "mode": mode,
                "niche": niche,
                "status": "pending_topic_engine",
            }
            for i in range(count)
        ]

    def _generate_calendar(self, topics: List[dict]) -> List[dict]:
        """生成内容日历排期"""
        # Default posting schedule (3 slots per day)
        posting_times = ["09:00", "14:00", "20:00"]
        today = time.strftime("%Y-%m-%d")

        entries = []
        for i, topic in enumerate(topics):
            slot_index = i % len(posting_times)
            day_offset = i // len(posting_times)

            # Simple date calculation
            import datetime
            post_date = datetime.datetime.strptime(today, "%Y-%m-%d") + datetime.timedelta(days=day_offset)

            entries.append({
                "date": post_date.strftime("%Y-%m-%d"),
                "time": posting_times[slot_index],
                "title": topic.get("title", f"内容{i+1}"),
                "status": "scheduled",
                "topic_index": i,
            })

        return entries

    def _save_daily_plan(self, plan: dict) -> str:
        """保存每日操盘计划"""
        date_str = plan.get("date", time.strftime("%Y-%m-%d"))
        plan_path = os.path.join(self.calendar_dir, f"daily_{date_str}.json")
        try:
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False, indent=2)
            logger.info(f"[DailyOperator] 日计划已保存: {plan_path}")
        except IOError as e:
            logger.error(f"[DailyOperator] 保存日计划失败: {e}")
            plan_path = ""
        return plan_path

    @staticmethod
    def _get_next_steps(plan: dict, auto_mode: bool) -> List[str]:
        """生成下一步行动指引"""
        steps = []
        topics = plan.get("topics", [])
        scripts = plan.get("scripts", [])

        pending_topics = [t for t in topics if t.get("status") == "pending_topic_engine"]
        pending_scripts = [s for s in scripts if s.get("status") == "pending_generation"]

        if pending_topics:
            steps.append(f"运行TopicEngine生成{len(pending_topics)}个选题")
        if pending_scripts:
            steps.append(f"运行ScriptWriter生成{len(pending_scripts)}条文案")
        steps.append("运行ReviewDiagnosis对文案进行爆款评分")
        steps.append("进入9-Agent Pipeline批量生产视频")

        if not auto_mode:
            steps.insert(0, "⏸️ 等待人工确认选题后继续")

        return steps
