"""
planner_service.py — LLM Planner / Refiner Layer for Project JARVIS.

Responsibility:
    Accept raw user text → build a schema-first prompt → call the Groq LLM API
    → parse and validate the JSON response → return a PlannerOutput or PlannerFailure.

This module is INTERPRETATION ONLY.
It never calls desktop tools, browser agents, or any execution layer.
All real actions stay in deterministic specialist agents.
"""

import os
import sys
import json
import logging
import re
from typing import Union

# Ensure the project root is on the path for shared imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from shared.contracts.schemas import PlannerOutput, PlannerFailure, TargetAgent, RiskLevel
from shared.config.settings import settings

logger = logging.getLogger("planner-service")

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

PLANNER_PROMPT_VERSION = "1.0"

# High-risk action keywords — any input containing these forces risk_level=high
HIGH_RISK_KEYWORDS = [
    "delete", "remove", "uninstall", "format", "wipe", "shutdown", "restart",
    "force kill", "forcekill", "rm -rf", "purge", "drop database", "factory reset",
    "credential", "password", "admin", "sudo", "registry edit"
]

SYSTEM_PROMPT = """\
You are a strict JSON task planner for an AI desktop assistant called JARVIS.
Your ONLY job is to convert a raw user instruction into a structured JSON task object.

## Output Rules
- Return ONLY valid JSON — no markdown fences, no explanations, no extra text.
- Every response must be a single JSON object conforming to the schema below.
- Do NOT include any field not listed in the schema.
- If the intent is unclear, still return JSON with your best guess and a lower confidence.

## Schema Contract
{
  "schema_version": "1.0",
  "raw_user_input": "<exact user input, never altered>",
  "intent": "<one of the allowed intent strings>",
  "target_agent": "<one of: desktop | browser | memory | voice | system | unknown>",
  "action": "<atomic verb: open | close | focus | search | navigate | remember | recall | speak | screenshot | list | unknown>",
  "target": "<specific app name, folder name, URL, or search query — null if not applicable>",
  "parameters": {},
  "confidence": <float between 0.0 and 1.0>,
  "requires_confirmation": <true | false>,
  "risk_level": "<low | medium | high>",
  "reasoning_summary": "<one sentence explaining the decision>"
}

## Allowed Intent Values
- open_app        → opening an application by name
- close_app       → closing/terminating an application
- focus_app       → bringing an application window to front
- list_open_apps  → listing currently open/running apps
- open_folder     → opening a known system folder (downloads, documents, desktop, etc.)
- screenshot      → taking a screenshot of the current screen
- search_web      → searching the web for information
- browse_web      → navigating to a specific URL or website
- navigate_url    → going to a specific URL directly
- remember        → storing information in memory
- recall          → retrieving information from memory
- speak           → text-to-speech output
- transcribe      → speech-to-text input
- system_control  → system-level actions (shutdown, restart, volume, etc.)
- conversation    → conversational queries, greetings (e.g. 'hello I am audible', 'hi jarvis'), questions, explanations, coding, writing, math, reasoning, or generic assistant tasks that do not manipulate OS windows or search engines
- unknown         → intent cannot be determined

## Risk Classification Rules
- risk_level="high": delete, uninstall, format, wipe, shutdown, restart, force kill, purge, credential, password, admin, sudo
- risk_level="medium": close_app, system_control, browse_web, navigate_url
- risk_level="low": everything else

## Confirmation Rules
- requires_confirmation=true when risk_level="high"
- requires_confirmation=true for system_control with destructive parameters
- requires_confirmation=false for everything else

## Few-Shot Examples

Input: "hello I am audible"
Output: {"schema_version":"1.0","raw_user_input":"hello I am audible","intent":"conversation","target_agent":"system","action":"reply","target":null,"parameters":{},"confidence":0.99,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User is greeting and testing audio audibility; conversational reply required."}

Input: "open whatsapp"
Output: {"schema_version":"1.0","raw_user_input":"open whatsapp","intent":"open_app","target_agent":"desktop","action":"open","target":"whatsapp","parameters":{},"confidence":0.98,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open WhatsApp."}

Input: "open what's app"
Output: {"schema_version":"1.0","raw_user_input":"open what's app","intent":"open_app","target_agent":"desktop","action":"open","target":"whatsapp","parameters":{},"confidence":0.98,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open WhatsApp."}

Input: "open WhatsApp and message Siddhartha"
Output: {"schema_version":"1.0","raw_user_input":"open WhatsApp and message Siddhartha","intent":"open_app","target_agent":"desktop","action":"open","target":"whatsapp","parameters":{"contact":"Siddhartha","message":null},"confidence":0.97,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open WhatsApp to message Siddhartha."}

Input: "open WhatsApp and message Siddhartha hello"
Output: {"schema_version":"1.0","raw_user_input":"open WhatsApp and message Siddhartha hello","intent":"open_app","target_agent":"desktop","action":"open","target":"whatsapp","parameters":{"contact":"Siddhartha","message":"hello"},"confidence":0.98,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open WhatsApp and message Siddhartha with text hello."}

Input: "open whatsapp and text someone"
Output: {"schema_version":"1.0","raw_user_input":"open whatsapp and text someone","intent":"open_app","target_agent":"desktop","action":"open","target":"whatsapp","parameters":{},"confidence":0.96,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open WhatsApp to message someone."}

Input: "open YouTube and play rrr song"
Output: {"schema_version":"1.0","raw_user_input":"open YouTube and play rrr song","intent":"open_app","target_agent":"desktop","action":"open","target":"youtube","parameters":{"query":"rrr song"},"confidence":0.98,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open YouTube and play rrr song."}

Input: "open Notepad and write a new nucleus algorithm"
Output: {"schema_version":"1.0","raw_user_input":"open Notepad and write a new nucleus algorithm","intent":"open_app","target_agent":"desktop","action":"open","target":"notepad","parameters":{"content":"a new nucleus algorithm"},"confidence":0.98,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open Notepad and write an algorithm."}

Input: "what is 25 * 14?"
Output: {"schema_version":"1.0","raw_user_input":"what is 25 * 14?","intent":"conversation","target_agent":"system","action":"reply","target":null,"parameters":{},"confidence":0.99,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"Generic calculation question."}

Input: "explain quantum computing in 2 lines"
Output: {"schema_version":"1.0","raw_user_input":"explain quantum computing in 2 lines","intent":"conversation","target_agent":"system","action":"reply","target":null,"parameters":{},"confidence":0.99,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"Generic explanation query."}

Input: "open downloads folder"
Output: {"schema_version":"1.0","raw_user_input":"open downloads folder","intent":"open_folder","target_agent":"desktop","action":"open","target":"downloads","parameters":{},"confidence":0.96,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open the downloads folder on the desktop."}

Input: "open file manager"
Output: {"schema_version":"1.0","raw_user_input":"open file manager","intent":"open_app","target_agent":"desktop","action":"open","target":"file_explorer","parameters":{},"confidence":0.95,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open File Explorer application."}

Input: "search best laptops under 50000"
Output: {"schema_version":"1.0","raw_user_input":"search best laptops under 50000","intent":"search_web","target_agent":"browser","action":"search","target":"best laptops under 50000","parameters":{},"confidence":0.93,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants a web search for laptop recommendations."}

Input: "close notepad"
Output: {"schema_version":"1.0","raw_user_input":"close notepad","intent":"close_app","target_agent":"desktop","action":"close","target":"notepad","parameters":{},"confidence":0.88,"requires_confirmation":false,"risk_level":"medium","reasoning_summary":"User wants to close the Notepad application."}

Input: "take a screenshot"
Output: {"schema_version":"1.0","raw_user_input":"take a screenshot","intent":"screenshot","target_agent":"desktop","action":"screenshot","target":null,"parameters":{},"confidence":0.97,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to capture the current screen."}

Input: "delete all files in downloads"
Output: {"schema_version":"1.0","raw_user_input":"delete all files in downloads","intent":"system_control","target_agent":"desktop","action":"delete","target":"downloads","parameters":{},"confidence":0.91,"requires_confirmation":true,"risk_level":"high","reasoning_summary":"Destructive action detected — deleting files is high risk and requires confirmation."}

Input: "open teams"
Output: {"schema_version":"1.0","raw_user_input":"open teams","intent":"open_app","target_agent":"desktop","action":"open","target":"teams","parameters":{},"confidence":0.94,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open Microsoft Teams."}

Input: "open microsoft store"
Output: {"schema_version":"1.0","raw_user_input":"open microsoft store","intent":"open_app","target_agent":"desktop","action":"open","target":"microsoft store","parameters":{},"confidence":0.95,"requires_confirmation":false,"risk_level":"low","reasoning_summary":"User wants to open the Microsoft Store app."}
"""


def _build_user_message(raw_input: str) -> str:
    """Wraps the raw user input for the Groq chat message."""
    return f'Convert this user instruction to a JSON task object:\n"{raw_input}"'


def _strip_markdown_fences(text: str) -> str:
    """Removes ```json ... ``` or ``` ... ``` fences that the model may add despite instructions."""
    # Remove fenced code blocks
    text = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    return text.strip()


def _call_groq(raw_input: str) -> str:
    """
    Calls the Groq Chat Completion API and returns the raw model response text.
    Raises RuntimeError on connection failure or missing API key.
    """
    api_key = settings.groq_api_key
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to your .env file to enable the LLM Planner. "
            "Get a free key at https://console.groq.com"
        )

    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError(
            "The 'groq' package is not installed. Run: pip install groq>=0.9.0"
        )

    client = Groq(api_key=api_key)
    model = settings.groq_model

    logger.debug(f"[Planner] Calling Groq model='{model}' for input='{raw_input[:60]}'")

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(raw_input)},
        ],
        temperature=0.0,   # Deterministic — we want strict JSON, not creative output
        max_tokens=512,
        top_p=1.0,
    )

    return completion.choices[0].message.content or ""


def _parse_and_validate(raw_output: str, raw_input: str) -> PlannerOutput:
    """
    Strips markdown fences, parses JSON, and validates against PlannerOutput schema.
    Raises ValueError on parse or validation failure.
    """
    cleaned = _strip_markdown_fences(raw_output)

    if not cleaned:
        raise ValueError("Empty response received from LLM")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned non-JSON output: {e}. Raw: '{cleaned[:200]}'")

    # Always override raw_user_input with the actual original input (safety guard)
    data["raw_user_input"] = raw_input

    # Validate with Pydantic (raises ValidationError on schema mismatch)
    return PlannerOutput.model_validate(data)


def plan(raw_input: str, max_retries: int = 2) -> Union[PlannerOutput, PlannerFailure]:
    """
    Main entry point for the LLM Planner.

    Accepts raw user input text and returns either:
    - PlannerOutput  → validated structured task (success path)
    - PlannerFailure → structured error with reason (fallback path)

    Retries up to `max_retries` times on parse/validation errors.
    Never raises an exception — all errors are captured in PlannerFailure.

    Logs:
        raw_user_input, model_name, schema_version, retry_count, confidence,
        planner_failure_reason. Never logs API keys.
    """
    model_name = settings.groq_model
    retry_count = 0
    last_error = "Unknown error"

    logger.info(
        f"[Planner] START | prompt_version={PLANNER_PROMPT_VERSION} "
        f"model={model_name} input='{raw_input[:80]}'"
    )

    for attempt in range(max_retries + 1):
        retry_count = attempt
        try:
            raw_output = _call_groq(raw_input)
            result = _parse_and_validate(raw_output, raw_input)

            logger.info(
                f"[Planner] SUCCESS | attempt={attempt + 1} "
                f"intent={result.intent} target_agent={result.target_agent} "
                f"confidence={result.confidence:.2f} risk={result.risk_level} "
                f"schema_version={result.schema_version}"
            )
            return result

        except RuntimeError as e:
            # Hard failures (missing API key, package not installed) — do not retry
            last_error = str(e)
            logger.warning(f"[Planner] HARD FAILURE (no retry): {last_error}")
            break

        except Exception as e:
            last_error = str(e)
            logger.warning(
                f"[Planner] Attempt {attempt + 1}/{max_retries + 1} failed: {last_error}"
            )
            if attempt < max_retries:
                logger.info(f"[Planner] Retrying ({attempt + 2}/{max_retries + 1})...")

    logger.error(
        f"[Planner] FAILED after {retry_count + 1} attempt(s). "
        f"reason='{last_error}' input='{raw_input[:80]}'"
    )

    return PlannerFailure(
        raw_user_input=raw_input,
        failure_reason=last_error,
        retry_count=retry_count,
        fallback_used=False,
    )


def generate_conversational_response(raw_input: str, system_context: str = None) -> str:
    """
    Directly answers conversational queries, greetings, questions, reasoning,
    and generic assistant tasks using Groq LLM with a friendly, intelligent JARVIS persona.
    """
    api_key = settings.groq_api_key
    if not api_key:
        return "I am JARVIS. How may I assist you today?"

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        model = settings.groq_model

        system_prompt = (
            "You are JARVIS (Just A Rather Very Intelligent System), an articulate, polite, "
            "warm, and highly capable AI assistant.\n"
            "Guidelines:\n"
            "- If the user greets you or checks if their voice/microphone is working or audible "
            "(e.g., 'hello I am audible', 'can you hear me'), warmly confirm that they are loud "
            "and clear, and ask how you can help them.\n"
            "- For questions, general tasks, coding, calculations, or explanations, provide direct, "
            "accurate, well-crafted, and concise answers.\n"
            "- Keep responses conversational, natural, and friendly for both voice readout and text display.\n"
            "- Never mention internal routing, schemas, or confidence percentages."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_input}
        ]

        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=600,
            top_p=0.95,
        )
        return (completion.choices[0].message.content or "").strip()
    except Exception as e:
        logger.error(f"[Planner] Conversational generation error: {e}")
        return "I hear you clearly, sir. How can I assist you with your tasks today?"
