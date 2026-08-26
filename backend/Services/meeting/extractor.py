"""
Meeting Extractor — Structured information extraction from transcripts.

Extracts:
  - Action items (tasks, assignees, deadlines)
  - Key decisions (decisions made during meeting)
  - Open questions (unresolved issues, questions raised)
"""

import json
import logging
from typing import List, Dict, Any

from decouple import config
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

GROQ_MODEL = config("GROQ_MODEL_ID", default="llama-3.3-70b-versatile")
_llm = None


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0.1,
            max_tokens=2048,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _llm


_EXTRACTION_SYSTEM_PROMPT = """You are an executive assistant extracting structured insights from a meeting transcript.

Analyze the transcript and extract:
1. "action_items": List of actionable tasks. Include task description, assignee (if mentioned), and due date (if mentioned).
2. "key_decisions": List of explicit decisions, agreements, or approvals made during the meeting.
3. "open_questions": List of questions asked that were left unanswered or items needing further investigation.

Respond ONLY in valid JSON matching this schema:
{
  "action_items": [
    "Task description (Assignee: Name, Due: Date)"
  ],
  "key_decisions": [
    "Decision made..."
  ],
  "open_questions": [
    "Unresolved question..."
  ]
}
"""


def extract_structured_meeting_data(transcript: str) -> Dict[str, List[str]]:
    """
    Extract action items, key decisions, and open questions from a meeting transcript.

    Returns:
        {
            "action_items": [...],
            "key_decisions": [...],
            "open_questions": [...]
        }
    """
    if not transcript or not transcript.strip():
        return {
            "action_items": [],
            "key_decisions": [],
            "open_questions": [],
        }

    try:
        # Cap transcript at ~12000 chars to avoid token overflow
        transcript_sample = transcript[:12000]
        llm = _get_llm()
        messages = [
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=f"Meeting Transcript:\n{transcript_sample}"),
        ]
        response = llm.invoke(messages)
        raw = response.content.strip()

        parsed = json.loads(raw)
        return {
            "action_items": parsed.get("action_items", []),
            "key_decisions": parsed.get("key_decisions", []),
            "open_questions": parsed.get("open_questions", []),
        }

    except Exception as e:
        logger.exception("Failed to extract structured meeting data: %s", e)
        return {
            "action_items": [],
            "key_decisions": [],
            "open_questions": [],
        }


def extract_action_items(transcript: str) -> List[str]:
    data = extract_structured_meeting_data(transcript)
    return data.get("action_items", [])


def extract_key_decisions(transcript: str) -> List[str]:
    data = extract_structured_meeting_data(transcript)
    return data.get("key_decisions", [])


def extract_open_questions(transcript: str) -> List[str]:
    data = extract_structured_meeting_data(transcript)
    return data.get("open_questions", [])
