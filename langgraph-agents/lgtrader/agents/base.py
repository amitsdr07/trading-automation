from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


def _resolve_api_key(llm_cfg: Dict[str, Any]) -> Optional[str]:
    explicit = llm_cfg.get("api_key")
    if explicit:
        return explicit
    env_var = llm_cfg.get("env", "OPENAI_API_KEY")
    return os.getenv(env_var)


def build_chat_model(llm_cfg: Dict[str, Any]) -> BaseChatModel:
    provider = (llm_cfg.get("provider") or "openai").lower()
    model = llm_cfg.get("model") or "gpt-4o-mini"
    temperature = float(llm_cfg.get("temperature", 0.2))

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = _resolve_api_key(llm_cfg)
        if not api_key:
            raise RuntimeError(
                "OpenAI API key is not configured. "
                "Provide `api_key` or set environment variable."
            )
        return ChatOpenAI(model=model, temperature=temperature, api_key=api_key, timeout=60)

    if provider == "azure-openai":
        from langchain_openai import AzureChatOpenAI

        api_key = _resolve_api_key(llm_cfg)
        endpoint = llm_cfg.get("endpoint") or os.getenv("AZURE_OPENAI_ENDPOINT")
        deployment = llm_cfg.get("deployment_name") or llm_cfg.get("deployment")
        if not api_key or not endpoint or not deployment:
            raise RuntimeError(
                "Azure OpenAI configuration requires `api_key`, `endpoint`, and `deployment_name`."
            )
        return AzureChatOpenAI(
            api_version=llm_cfg.get("api_version", "2024-05-01-preview"),
            azure_endpoint=endpoint,
            deployment_name=deployment,
            temperature=temperature,
            api_key=api_key,
            timeout=60,
        )

    raise ValueError(f"Unsupported LLM provider: {provider}")


@dataclass
class AgentIO:
    summary: str
    details: Dict[str, Any] = field(default_factory=dict)


class LLMTradingAgent:
    """
    Shared wrapper that turns inputs into structured agent responses.
    Agents keep prompts close to domain logic and share JSON schema guidelines.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        llm_cfg: Dict[str, Any],
        output_format_hint: str = "Respond with JSON containing `summary` and `details` keys.",
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.output_format_hint = output_format_hint
        self.llm_cfg = llm_cfg
        self.llm = build_chat_model(llm_cfg)

    def _format_inputs(self, inputs: Dict[str, Any]) -> str:
        return json.dumps(inputs, default=str, ensure_ascii=False, indent=2)

    def _build_messages(self, inputs: Dict[str, Any]):
        system = (
            f"{self.system_prompt.strip()}\n\n"
            f"Output requirements: {self.output_format_hint}"
        )
        human = (
            "Context for this task (JSON encoded):\n"
            f"{self._format_inputs(inputs)}"
        )
        return [
            SystemMessage(content=system),
            HumanMessage(content=human),
        ]

    def invoke(self, inputs: Dict[str, Any]) -> AgentIO:
        messages = self._build_messages(inputs)
        response = self.llm.invoke(messages)
        content = getattr(response, "content", "")
        try:
            payload = json.loads(content)
        except Exception:
            payload = {"summary": content, "details": {}}
        if isinstance(payload, dict):
            summary = payload.get("summary") or ""
            details = payload.get("details") or {}
        else:
            summary = str(payload)
            details = {}
        return AgentIO(summary=summary.strip(), details=details)
