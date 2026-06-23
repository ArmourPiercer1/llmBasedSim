"""LLM structured output helper using prompt-based JSON + Pydantic parsing.

DeepSeek does not support the native `response_format` structured output API.
Instead, we instruct the LLM to output JSON and parse it manually with Pydantic.
"""

import json
import re
from typing import TypeVar

import structlog
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
logger = structlog.get_logger()

JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


async def generate_structured(
    llm: ChatOpenAI,
    messages: list[BaseMessage],
    output_model: type[T],
    max_retries: int = 2,
) -> T:
    """Generate a response and parse it into the given Pydantic model.

    Appends JSON formatting instructions to the last message.
    On parse failure, retries with error feedback.
    """
    schema_json = json.dumps(output_model.model_json_schema(), ensure_ascii=False, indent=2)

    json_instruction = (
        f"\n\n## 输出格式要求\n"
        f"你必须严格按照以下 JSON Schema 输出一个 JSON 对象，不要输出任何其他内容（不要用 markdown 代码块包裹，直接输出原始 JSON）：\n"
        f"```json\n{schema_json}\n```"
    )
    # Append instruction to the last message
    messages_with_instruction = list(messages)
    last = messages_with_instruction[-1]
    messages_with_instruction[-1] = last.__class__(content=last.content + json_instruction)

    for attempt in range(max_retries + 1):
        response = await llm.ainvoke(messages_with_instruction)
        text = response.content if isinstance(response.content, str) else str(response.content)

        # Try to extract JSON from the response
        json_text = _extract_json(text)

        try:
            return output_model.model_validate_json(json_text)
        except Exception as e:
            logger.warning(
                "structured_output_parse_failed",
                attempt=attempt,
                error=str(e),
                raw_preview=text[:200],
            )
            if attempt < max_retries:
                # Retry with error feedback
                retry_msg = (
                    f"上一次输出格式不正确: {e}\n"
                    f"请严格按照 JSON Schema 输出。直接输出 JSON，不要用 markdown 代码块包裹。"
                )
                messages_with_instruction.append(
                    messages_with_instruction[-1].__class__(content=retry_msg)
                )

    raise ValueError(f"Failed to parse structured output after {max_retries + 1} attempts")


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, handling markdown code blocks."""
    text = text.strip()
    # Try markdown code block extraction first
    match = JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()
    # Try to find the first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    # Fallback: return the raw text
    return text
