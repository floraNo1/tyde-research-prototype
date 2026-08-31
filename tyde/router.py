"""Transparent reference classifier used by the diagnostic evaluation."""

from __future__ import annotations

import re
from datetime import date

from .schemas import Classification, Intent, MemoryKind, UpdateTarget

_DATE = r"\d{4}-\d{2}-\d{2}"
_CJK_REFERENCE_LOCATIONS = {
    "北京",
    "成都",
    "重庆",
    "广州",
    "杭州",
    "香港",
    "澳门",
    "南京",
    "上海",
    "深圳",
    "台北",
    "天津",
    "武汉",
    "西安",
    "新加坡",
    "东京",
    "大阪",
    "伦敦",
    "巴黎",
}
_NON_LOCATION_PHRASES = {
    "a good mood",
    "a hurry",
    "a meeting",
    "a rush",
    "bed",
    "charge",
    "class",
    "danger",
    "doubt",
    "love",
    "pain",
    "shock",
    "trouble",
}


class IntentRouter:
    """Small rule policy: inspectable by design, replaceable by an LLM in later studies."""

    def classify(self, text: str) -> Classification:
        clean = " ".join(text.strip().split())
        lower = clean.lower()

        if self._is_query(lower):
            return Classification(Intent.PROJECT_QUERY, evidence=["question form"])

        preference = self._preference(clean, lower)
        if preference:
            return preference

        location = self._location(clean)
        if location:
            return location

        project = self._project_update(clean, lower)
        if project:
            return project

        return Classification(Intent.CASUAL_DIALOGUE, evidence=["no durable-state signal"])

    @staticmethod
    def _is_query(lower: str) -> bool:
        return bool(
            lower.endswith("?")
            and re.search(r"\b(what|when|where|which|how)\b|什么|何时|哪里|哪一个|怎么", lower)
        )

    @staticmethod
    def _location(text: str) -> Classification | None:
        patterns = [
            r"(?:i(?:'ll| will)? be|i am|i'm) in ([A-Za-z][A-Za-z .'-]+?)(?: instead of| tomorrow| today|[.!?]|$)",
            r"(?:^|[，。,.]\s*)(?:明天|今天)?(?:我)?(?:会)?在([^，。,.]+?)(?:而不是|，|。|$)",
            r"(?:location is|location changed to) ([A-Za-z][A-Za-z .'-]+?)(?:[.!?]|$)",
            r"(?:地点是|地点改到)([^，。,.]+?)(?:，|。|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip(" .，。")
                if not IntentRouter._is_plausible_location(candidate):
                    continue
                scheduled = bool(re.search(r"\btomorrow\b|明天", text, flags=re.IGNORECASE))
                fields = {"location": candidate}
                if scheduled:
                    fields["valid_from"] = "tomorrow"
                return Classification(
                    Intent.STATE_UPDATE,
                    fields=fields,
                    target=UpdateTarget.SCHEDULED_STATE if scheduled else UpdateTarget.CURRENT_STATE,
                    memory_kind=MemoryKind.FACT,
                    material_fields=["location"],
                    evidence=[
                        "explicit scheduled-location update"
                        if scheduled
                        else "explicit current-location replacement"
                    ],
                )
        return None

    @staticmethod
    def _is_plausible_location(candidate: str) -> bool:
        normalized = " ".join(candidate.split())
        lower = normalized.lower()
        if lower in _NON_LOCATION_PHRASES:
            return False
        if re.search(r"[\u4e00-\u9fff]", normalized):
            if normalized in _CJK_REFERENCE_LOCATIONS:
                return True
            return bool(re.search(r"(?:省|市|县|区|镇|乡|州|国|岛)$", normalized))

        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", normalized)
        connectors = {"de", "of", "the"}
        significant = [word for word in words if word.lower() not in connectors]
        return bool(significant) and all(word[0].isupper() for word in significant)

    @staticmethod
    def _preference(text: str, lower: str) -> Classification | None:
        stable = bool(
            re.search(
                r"\b(i prefer|i usually|i work best|my preference)\b|我偏好|我通常|我习惯|我更喜欢", lower
            )
        )
        if not stable:
            return None
        fields: dict[str, str] = {}
        periods = {
            "morning": r"\bmorning\b|上午|早上",
            "afternoon": r"\bafternoon\b|下午",
            "evening": r"\bevening\b|晚上",
        }
        for value, pattern in periods.items():
            if re.search(pattern, lower):
                fields["work_period"] = value
                break
        duration = re.search(r"(\d{1,3})\s*(?:minutes?|mins?|分钟)", lower)
        if duration:
            fields["focus_minutes"] = duration.group(1)
        return Classification(
            Intent.PREFERENCE_UPDATE,
            fields=fields,
            memory_kind=MemoryKind.PREFERENCE,
            stable_preference=True,
            evidence=["stable preference expression"],
        )

    @staticmethod
    def _project_update(text: str, lower: str) -> Classification | None:
        fields: dict[str, str] = {}
        evidence: list[str] = []

        deadline_signal = re.search(r"\bdeadline\b|due date|截止|提交日期", lower)
        if deadline_signal:
            dates = re.findall(_DATE, text)
            if not dates:
                return Classification(
                    Intent.PROJECT_UPDATE,
                    confidence=0.0,
                    evidence=["deadline update missing an ISO date"],
                )
            deadline = dates[-1]
            try:
                date.fromisoformat(deadline)
            except ValueError:
                return Classification(
                    Intent.PROJECT_UPDATE,
                    confidence=0.0,
                    evidence=["invalid deadline date"],
                )
            fields["deadline"] = deadline
            evidence.append("explicit valid deadline")

        milestone = re.search(
            r"(?:milestone (?:is|changed to)|里程碑(?:是|改为))\s*[:：]?\s*([^,.。]+)", text, re.IGNORECASE
        )
        if milestone:
            fields["current_milestone"] = milestone.group(1).strip()
            evidence.append("milestone change")

        next_action = re.search(
            r"(?:next action (?:is|changed to)|下一步(?:是|改为|先))\s*[:：]?\s*([^,.。]+)",
            text,
            re.IGNORECASE,
        )
        if next_action:
            fields["next_action"] = next_action.group(1).strip()
            evidence.append("next-action change")

        if re.search(r"\bworkload (?:doubled|increased)\b|工作量(?:翻倍|增加)", lower):
            fields["workload"] = "increased"
            evidence.append("workload increase")
        elif re.search(r"\bworkload (?:halved|decreased)\b|工作量(?:减半|减少)", lower):
            fields["workload"] = "decreased"
            evidence.append("workload decrease")

        blocker = re.search(r"(?:blocked by|blocker is|被.+?卡住|阻塞项是)\s*([^,.。]+)", text, re.IGNORECASE)
        if blocker:
            fields["blocker"] = blocker.group(1).strip()
            evidence.append("blocker change")
        elif re.search(r"\b(?:experiment|baseline|test) failed\b|(?:实验|基线|测试)失败", lower):
            fields["blocker"] = "experiment failed" if not re.search(r"[\u4e00-\u9fff]", text) else "实验失败"
            evidence.append("failed experiment")

        if fields:
            return Classification(
                Intent.PROJECT_UPDATE,
                fields=fields,
                memory_kind=MemoryKind.FACT,
                material_fields=list(fields),
                evidence=evidence,
            )

        if re.search(r"\b(consistently|we found|lesson learned)\b|持续发现|经验是|事实证明", lower):
            return Classification(
                Intent.PROJECT_UPDATE,
                memory_kind=MemoryKind.EXPERIENCE,
                evidence=["candidate reusable experience"],
            )

        if re.search(r"\b(project note|decision:)\b|项目记录|项目决定", lower):
            kind = MemoryKind.DECISION if re.search(r"decision:|项目决定", lower) else MemoryKind.FACT
            return Classification(Intent.PROJECT_UPDATE, memory_kind=kind, evidence=["project-scoped memory"])
        return None
