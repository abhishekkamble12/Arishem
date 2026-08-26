"""
Meeting Summarizer — LLM Map-Reduce summarization + title generation.

Uses ChatGroq to:
  1. Generate a concise title for a meeting transcript.
  2. Perform map-reduce summarization over large transcripts:
     - Map step: split transcript into 3,000 character chunks, summarize each chunk.
     - Reduce step: combine chunk summaries into a structured, bullet-point meeting summary.
"""

import json
import logging
from typing import List

from decouple import config
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

GROQ_MODEL = config("GROQ_MODEL_ID", default="llama-3.3-70b-versatile")
_llm = None


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        _llm = ChatGroq(
            model=GROQ_MODEL,
            temperature=0.3,
            max_tokens=2048,
        )
    return _llm


_TITLE_PROMPT = """You are an executive assistant. Generate a concise, clear title (max 7-10 words) for the following meeting transcript.
Respond ONLY with the title string, no quotes, no extra formatting or explanations."""

_MAP_PROMPT = """Summarize this portion of a meeting transcript concisely. Focus on key topics discussed, main points raised, and decisions made. Keep it short (2-4 bullet points)."""

_REDUCE_PROMPT = """You are an executive assistant. Below are partial summaries from different sections of a meeting.
Combine them into a single coherent, well-structured executive meeting summary.

Use the following format (plain text, no markdown headers):
Overview:
(A 2-3 sentence executive summary of the meeting's core purpose and outcome)

Key Topics Discussed:
- Topic 1: details...
- Topic 2: details...

Summary & Conclusion:
(A closing sentence summarizing next steps or state of project)
"""


def generate_title(transcript: str) -> str:
    """Generate a short title for a transcript using LLM."""
    if not transcript or not transcript.strip():
        return "Untitled Meeting"

    try:
        # Use first 3000 chars for title generation
        sample = transcript[:3000]
        llm = _get_llm()
        messages = [
            SystemMessage(content=_TITLE_PROMPT),
            HumanMessage(content=f"Transcript sample:\n{sample}"),
        ]
        response = llm.invoke(messages)
        title = response.content.strip().strip('"').strip("'")
        return title if title else "Untitled Meeting"
    except Exception as e:
        logger.exception("Failed to generate title: %s", e)
        return "Meeting Transcript"


def summarize(transcript: str) -> str:
    """
    Perform map-reduce summarization over a full meeting transcript.
    """
    if not transcript or not transcript.strip():
        return "No transcript content available to summarize."

    # If short transcript, single-pass summarize directly
    if len(transcript) <= 3500:
        try:
            llm = _get_llm()
            messages = [
                SystemMessage(content=_REDUCE_PROMPT),
                HumanMessage(content=f"Full Transcript:\n{transcript}"),
            ]
            response = llm.invoke(messages)
            return response.content.strip()
        except Exception as e:
            logger.exception("Single-pass summarization failed: %s", e)
            return f"Summary generation failed: {e}"

    # Map-Reduce for long transcripts
    try:
        splitter = RecursiveCharacterTextSplitter(chunk_size=3000, chunk_overlap=200)
        chunks: List[str] = splitter.split_text(transcript)
        logger.info("Summarizer: Split transcript into %d chunks for map-reduce", len(chunks))

        llm = _get_llm()
        chunk_summaries = []

        # Map step
        for i, chunk in enumerate(chunks, 1):
            messages = [
                SystemMessage(content=_MAP_PROMPT),
                HumanMessage(content=f"Transcript chunk {i}/{len(chunks)}:\n{chunk}"),
            ]
            res = llm.invoke(messages)
            chunk_summaries.append(res.content.strip())

        # Reduce step
        combined_text = "\n\n".join(chunk_summaries)
        messages = [
            SystemMessage(content=_REDUCE_PROMPT),
            HumanMessage(content=f"Partial Summaries:\n{combined_text}"),
        ]
        final_response = llm.invoke(messages)
        return final_response.content.strip()

    except Exception as e:
        logger.exception("Map-reduce summarization failed: %s", e)
        return f"Summary generation failed: {e}"
