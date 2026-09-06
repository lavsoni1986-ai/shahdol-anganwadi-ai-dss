# app/services/gemini_assistant.py
# =====================================================================
# BharatOS — Shahdol Anganwadi MVP
# Gemini Conversational Provider — AI Officer Copilot / Personal Journal
#
# Provides a real multi-turn conversation capability on top of the existing
# DSS. The provider is backend-only; the browser never talks to Gemini
# directly. The Gemini API key is resolved via Secret Manager (production)
# or the existing env/.env configuration (local development).
#
# Never logs API keys or full sensitive prompt content.
# =====================================================================

import time
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services.secret_manager import resolve_gemini_api_key
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are the AI Officer Copilot for the District Shahdol Anganwadi Digital "
    "Decision Support System (DSS). You assist district officers with "
    "brainstorming, reflection, case notes, field observations, planning, and "
    "decision support related to Anganwadi operations and child nutrition. "
    "Be concise, professional, and actionable. You may respond in Hindi or "
    "English. You are not a medical diagnosis tool."
)

SUMMARY_SYSTEM_PROMPT = (
    "You summarize an AI officer conversation for a government Anganwadi "
    "decision-support system. Produce a concise, structured, professional "
    "summary (2-4 short bullet points) in the language of the conversation. "
    "Do not invent facts not present in the conversation."
)

ACTION_PLAN_SYSTEM_PROMPT = (
    "You convert an Anganwadi officer AI conversation into a structured field "
    "action plan. Return strictly valid JSON with these exact keys: "
    '"key_observations" (array of short strings), "risks_issues" (array of short '
    'strings), "recommended_actions" (array of short strings), "priority" '
    '("LOW"/"MEDIUM"/"HIGH"), "suggested_next_step" (one short string). '
    "Base everything strictly on the conversation. Do not invent facts."
)


# ─────────────────────────────────────────────
# Structured Intelligence Models (Phase 5B)
# ─────────────────────────────────────────────

class ConversationSummary(BaseModel):
    """Structured summary of an officer AI conversation."""
    summary: str = ""
    key_observations: List[str] = Field(default_factory=list)
    important_issues: List[str] = Field(default_factory=list)
    conclusions: List[str] = Field(default_factory=list)
    priority_items: List[str] = Field(default_factory=list)
    relevant_context: Optional[str] = None


class FieldInsight(BaseModel):
    """A single field insight derived from the conversation."""
    issue: str = ""
    evidence_or_context: str = ""
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    affected_location: Optional[str] = None
    why_it_matters: str = ""


class ActionPlanItem(BaseModel):
    """A single recommended action for a field insight."""
    recommended_action: str = ""
    priority: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    responsible_level: str = ""
    next_step: str = ""
    rationale: str = ""


class SummaryBundle(BaseModel):
    """Validated structured output: summary + field insights + action plan."""
    summary: ConversationSummary = Field(default_factory=ConversationSummary)
    field_insights: List[FieldInsight] = Field(default_factory=list)
    action_plan: List[ActionPlanItem] = Field(default_factory=list)


INTELLIGENCE_SYSTEM_PROMPT = (
    "You are the intelligence engine for the District Shahdol Anganwadi "
    "Decision Support System. Convert the officer's conversation into "
    "structured administrative intelligence.\n"
    "Return ONLY strict valid JSON matching exactly this schema (no extra keys):\n"
    '{\n'
    '  "summary": {\n'
    '    "summary": "concise 2-4 sentence summary",\n'
    '    "key_observations": ["short observation"],\n'
    '    "important_issues": ["short issue"],\n'
    '    "conclusions": ["short conclusion"],\n'
    '    "priority_items": ["short priority item"],\n'
    '    "relevant_context": "only if block/AWC/district is explicitly mentioned, else null"\n'
    '  },\n'
    '  "field_insights": [\n'
    '    {\n'
    '      "issue": "the issue",\n'
    '      "evidence_or_context": "evidence only from the conversation",\n'
    '      "priority": "LOW" | "MEDIUM" | "HIGH",\n'
    '      "affected_location": "block/AWC only if explicitly known, else null",\n'
    '      "why_it_matters": "why it matters administratively"\n'
    '    }\n'
    '  ],\n'
    '  "action_plan": [\n'
    '    {\n'
    '      "recommended_action": "practical action",\n'
    '      "priority": "LOW" | "MEDIUM" | "HIGH",\n'
    '      "responsible_level": "AWC Worker | Supervisor | CDPO | District",\n'
    '      "next_step": "operational next step",\n'
    '      "rationale": "reason"\n'
    '    }\n'
    '  ]\n'
    '}\n'
    "RULES: Base everything strictly on the conversation. Do NOT invent facts, "
    "locations, numbers, people, dates, or evidence. Keep recommendations "
    "operational and realistic for an Anganwadi administrative workflow. "
    "You may respond in the language of the conversation."
)


class GeminiAssistantService:
    """Backend-only multi-turn Gemini assistant."""

    def __init__(self):
        self.model = settings.gemini_model
        self._client = None
        self._api_key: Optional[str] = None

    # ─────────────────────────────────────────────
    # Internals
    # ─────────────────────────────────────────────

    def _resolve_key(self) -> str:
        if self._api_key is None:
            self._api_key = resolve_gemini_api_key()
        return self._api_key

    def _get_client(self):
        if self._client is None:
            key = self._resolve_key()
            if not key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            from google import genai

            self._client = genai.Client(api_key=key)
        return self._client

    @staticmethod
    def _to_contents(history: List[Dict[str, str]]) -> List:
        """Converts a persisted history list into Google GenAI Content objects."""
        from google.genai import types

        contents = []
        for msg in history:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "assistant":
                role = "model"
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=content)])
            )
        return contents

    def generate_response(
        self,
        history: List[Dict[str, str]],
        user_message: str,
        system_prompt: str = SYSTEM_PROMPT,
    ) -> Dict:
        """
        Sends the full conversation history + the new user message to Gemini.

        history: list of {"role": "user"|"assistant", "content": str} messages.
        Returns {"success": bool, "content": str, "latency_ms": int}
        """
        from google.genai import types

        try:
            client = self._get_client()
        except Exception as e:
            logger.warning("assistant_client_unavailable", error_type=type(e).__name__)
            return {"success": False, "content": "", "error": "AI service not configured"}

        contents = self._to_contents(history)
        contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        )

        start = time.monotonic()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.7,
                ),
            )
            latency_ms = round((time.monotonic() - start) * 1000, 1)
            text = (response.text or "").strip() if response is not None else ""
            if not text:
                logger.warning("assistant_empty_response", model=self.model)
                return {"success": False, "content": "", "error": "Empty AI response"}
            logger.info("assistant_response", model=self.model, latency_ms=latency_ms)
            return {"success": True, "content": text, "latency_ms": latency_ms}
        except Exception as e:
            logger.warning("assistant_gemini_failed", error_type=type(e).__name__)
            return {"success": False, "content": "", "error": "AI request failed"}

    def summarize(self, history: List[Dict[str, str]]) -> str:
        """Generates a concise summary of the conversation."""
        if not history:
            return ""
        result = self.generate_response(
            history,
            "Please summarize this conversation.",
            system_prompt=SUMMARY_SYSTEM_PROMPT,
        )
        return result.get("content") or ""

    def generate_action_plan(self, history: List[Dict[str, str]]) -> Dict:
        """Generates the 'Field Insight -> Action Plan' structured output."""
        if not history:
            return {}
        result = self.generate_response(
            history,
            "Please generate the field action plan.",
            system_prompt=ACTION_PLAN_SYSTEM_PROMPT,
        )
        content = result.get("content") or ""
        import json as _json
        import re as _re

        try:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                plan = _json.loads(content[start : end + 1])
                if isinstance(plan, dict):
                    return plan
        except Exception:
            pass
        logger.warning("assistant_action_plan_parse_failed")
        return {}

    # ─────────────────────────────────────────────
    # Structured intelligence (Phase 5B)
    # ─────────────────────────────────────────────

    @staticmethod
    def _extract_json_dict(text: str) -> Dict:
        """Defensively extracts the largest valid JSON object from model output."""
        import json as _json

        try:
            parsed = _json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
        for i in range(len(text)):
            if text[i] == "{":
                nesting = 0
                in_string = False
                escape = False
                for j in range(i, len(text)):
                    ch = text[j]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"':
                        in_string = not in_string
                        continue
                    if not in_string:
                        if ch == "{":
                            nesting += 1
                        elif ch == "}":
                            nesting -= 1
                            if nesting == 0:
                                candidate = text[i : j + 1]
                                try:
                                    parsed = _json.loads(candidate)
                                    if isinstance(parsed, dict):
                                        return parsed
                                except Exception:
                                    pass
                                break
        return {}

    def generate_intelligence(self, history: List[Dict[str, str]]) -> Dict:
        """
        Generates a validated structured intelligence bundle:
        ConversationSummary + FieldInsights + ActionPlan.

        Returns:
            {"success": True, "bundle": SummaryBundle} on success, or
            {"success": False, "error": "<safe message>"} on any failure.
        Never exposes API keys, credentials, or internal exceptions.
        """
        if not history:
            return {"success": False, "error": "No conversation messages to summarize"}
        result = self.generate_response(
            history,
            "Please generate the structured field intelligence.",
            system_prompt=INTELLIGENCE_SYSTEM_PROMPT,
        )
        content = result.get("content") or ""
        if not content:
            return {"success": False, "error": "AI service returned no output"}
        raw = self._extract_json_dict(content)
        if not raw:
            logger.warning("assistant_intelligence_json_parse_failed")
            return {"success": False, "error": "AI output could not be parsed as structured JSON"}
        try:
            bundle = SummaryBundle.model_validate(raw)
            return {"success": True, "bundle": bundle}
        except ValidationError as e:
            logger.warning("assistant_intelligence_validation_failed", error=str(e)[:200])
            return {"success": False, "error": "AI output failed schema validation"}


# Singleton
gemini_assistant = GeminiAssistantService()
