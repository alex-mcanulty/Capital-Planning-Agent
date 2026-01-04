"""
Guardrail Middleware for Capital Planning Agent

This module provides middleware for input validation (prompt injection detection)
and output validation (toxicity/HAP detection) by calling the Guardrail Server API.

The middleware is lightweight and does not load models directly - it relies on
the guardrail_server.py to handle model inference.

Server must be running at: http://localhost:8004
"""
import logging
import os
from typing import Any, Callable

import httpx
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

GUARDRAIL_SERVER_URL = os.getenv("GUARDRAIL_SERVER_URL", "http://localhost:8004")
GUARDRAIL_ENABLED = os.getenv("GUARDRAIL_ENABLED", "true").lower() == "true"
INJECTION_THRESHOLD = float(os.getenv("INJECTION_THRESHOLD", "0.5"))
TOXICITY_THRESHOLD = float(os.getenv("TOXICITY_THRESHOLD", "0.5"))


# =============================================================================
# Async API Client
# =============================================================================

class GuardrailClient:
    """
    Async client for the Guardrail Detection Server API.

    Provides methods to check text for prompt injection and toxicity
    by calling the server endpoints.
    """

    def __init__(
        self,
        base_url: str = GUARDRAIL_SERVER_URL,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        """
        Initialize the guardrail API client.

        Args:
            base_url: Base URL of the guardrail server
            timeout: Request timeout in seconds
            http_client: Optional shared AsyncClient instance
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = http_client
        self._owns_client = http_client is None

        logger.info(f"GuardrailClient initialized (server={self.base_url})")

    @property
    def client(self) -> httpx.AsyncClient:
        """Lazy-initialize the HTTP client if not provided."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
            )
            self._owns_client = True
        return self._client

    async def health_check(self) -> dict[str, Any]:
        """Check server health."""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}

    async def detect_injection(
        self, text: str, threshold: float = 0.5
    ) -> tuple[bool, float, str]:
        """
        Check text for prompt injection.

        Args:
            text: Text to analyze
            threshold: Detection threshold (0.0-1.0)

        Returns:
            Tuple of (is_injection, score, label)
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/detect/injection",
                json={"text": text, "threshold": threshold},
            )
            response.raise_for_status()
            data = response.json()
            return data["detected"], data["score"], data["label"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Injection detection API error: {e}")
            # Fail open on API errors (configurable behavior)
            return False, 0.0, "ERROR"
        except Exception as e:
            logger.error(f"Injection detection failed: {e}")
            return False, 0.0, "ERROR"

    async def detect_toxicity(
        self, text: str, threshold: float = 0.5
    ) -> tuple[bool, float, str]:
        """
        Check text for toxicity (HAP).

        Args:
            text: Text to analyze
            threshold: Detection threshold (0.0-1.0)

        Returns:
            Tuple of (is_toxic, score, label)
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/detect/toxicity",
                json={"text": text, "threshold": threshold},
            )
            response.raise_for_status()
            data = response.json()
            return data["detected"], data["score"], data["label"]
        except httpx.HTTPStatusError as e:
            logger.error(f"Toxicity detection API error: {e}")
            return False, 0.0, "ERROR"
        except Exception as e:
            logger.error(f"Toxicity detection failed: {e}")
            return False, 0.0, "ERROR"

    async def close(self):
        """Close the HTTP client if we own it."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# LangChain Middleware
# =============================================================================

class GuardrailMiddleware(AgentMiddleware):
    """
    LangChain middleware for input and output guardrails via API.

    This middleware:
    - Checks user input for prompt injection attacks (before_agent)
    - Checks agent output for toxic content (after_agent)

    Requires the Guardrail Server to be running on port 8004.
    """

    def __init__(
        self,
        # Server settings
        server_url: str = GUARDRAIL_SERVER_URL,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
        # Feature toggle
        enabled: bool = GUARDRAIL_ENABLED,
        # Input guardrail settings
        enable_input_guardrail: bool = True,
        injection_threshold: float = INJECTION_THRESHOLD,
        input_refusal_message: str = (
            "I cannot help you with this. This incident has been logged and reported."
        ),
        # Output guardrail settings
        enable_output_guardrail: bool = True,
        toxicity_threshold: float = TOXICITY_THRESHOLD,
        output_refusal_message: str = (
            "I apologize, but I cannot provide that response as it may "
            "contain inappropriate content."
        ),
        # Callbacks for custom handling
        on_injection_detected: Callable[[str, float], None] | None = None,
        on_toxicity_detected: Callable[[str, float], None] | None = None,
    ):
        """
        Initialize the guardrail middleware.

        Args:
            server_url: URL of the Guardrail Detection Server
            timeout: API request timeout in seconds
            http_client: Optional shared AsyncClient instance
            enabled: Global toggle for guardrails (can be set via GUARDRAIL_ENABLED env var)
            enable_input_guardrail: Whether to check inputs for prompt injection
            injection_threshold: Confidence threshold (0.0-1.0) for blocking injections
            input_refusal_message: Message returned when input is blocked
            enable_output_guardrail: Whether to check outputs for toxicity
            toxicity_threshold: Confidence threshold (0.0-1.0) for blocking toxic output
            output_refusal_message: Message returned when output is blocked
            on_injection_detected: Optional callback when injection is detected
            on_toxicity_detected: Optional callback when toxicity is detected
        """
        super().__init__()

        self.enabled = enabled
        self.enable_input_guardrail = enable_input_guardrail
        self.enable_output_guardrail = enable_output_guardrail
        self.injection_threshold = injection_threshold
        self.toxicity_threshold = toxicity_threshold
        self.input_refusal_message = input_refusal_message
        self.output_refusal_message = output_refusal_message
        self.on_injection_detected = on_injection_detected
        self.on_toxicity_detected = on_toxicity_detected

        # Initialize API client
        self._client = GuardrailClient(
            base_url=server_url,
            timeout=timeout,
            http_client=http_client,
        )

        if self.enabled:
            logger.info(
                f"GuardrailMiddleware initialized "
                f"(server={server_url}, input={enable_input_guardrail}, "
                f"output={enable_output_guardrail})"
            )
        else:
            logger.warning("GuardrailMiddleware is DISABLED via configuration")

    @property
    def client(self) -> GuardrailClient:
        """Get the API client."""
        return self._client

    def _get_last_user_message(self, state: AgentState) -> str | None:
        """Extract the last user message from state."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]

        if not isinstance(last_message, HumanMessage):
            return None

        content = last_message.content
        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, str):
                    text_parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
            return " ".join(text_parts)

        return str(content)

    def _get_last_ai_message(self, state: AgentState) -> str | None:
        """Extract the last AI message from state."""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_message = messages[-1]

        if not isinstance(last_message, AIMessage):
            return None

        content = last_message.content
        if isinstance(content, str):
            return content

        return str(content)

    @hook_config(can_jump_to=["end"])
    def before_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """
        Sync version - not used when agent is invoked with ainvoke/astream.
        """
        return None

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """
        Check user input for prompt injection before agent execution.

        This hook runs once at the start of each agent invocation.
        """
        if not self.enabled or not self.enable_input_guardrail:
            return None

        user_input = self._get_last_user_message(state)
        if not user_input:
            return None

        # Call the API for prompt injection detection
        is_injection, score, label = await self._client.detect_injection(
            user_input, self.injection_threshold
        )

        if is_injection:
            logger.warning(
                f"Prompt injection detected (score={score:.4f}): "
                f"{user_input[:100]}..."
            )

            if self.on_injection_detected:
                try:
                    self.on_injection_detected(user_input, score)
                except Exception as e:
                    logger.error(f"Error in on_injection_detected callback: {e}")

            return {
                "messages": [AIMessage(content=self.input_refusal_message)],
                "jump_to": "end",
            }

        logger.debug(f"Input passed guardrail check (label={label}, score={score:.4f})")
        return None

    @hook_config(can_jump_to=["end"])
    def after_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """
        Sync version - not used when agent is invoked with ainvoke/astream.
        """
        return None

    @hook_config(can_jump_to=["end"])
    async def aafter_agent(
        self, state: AgentState, runtime: Runtime
    ) -> dict[str, Any] | None:
        """
        Check agent output for toxic content (HAP) after execution.

        This hook runs once after the agent completes.
        """
        if not self.enabled or not self.enable_output_guardrail:
            return None

        agent_output = self._get_last_ai_message(state)
        if not agent_output:
            return None

        # Call the API for toxicity detection
        is_toxic, score, label = await self._client.detect_toxicity(
            agent_output, self.toxicity_threshold
        )

        if is_toxic:
            logger.warning(
                f"Toxic output detected (score={score:.4f}): "
                f"{agent_output[:100]}..."
            )

            if self.on_toxicity_detected:
                try:
                    self.on_toxicity_detected(agent_output, score)
                except Exception as e:
                    logger.error(f"Error in on_toxicity_detected callback: {e}")

            return {
                "messages": [AIMessage(content=self.output_refusal_message)],
                "jump_to": "end",
            }

        logger.debug(f"Output passed guardrail check (label={label}, score={score:.4f})")
        return None


# =============================================================================
# Convenience Functions
# =============================================================================

def create_guardrail_middleware(
    server_url: str = GUARDRAIL_SERVER_URL,
    injection_threshold: float = INJECTION_THRESHOLD,
    toxicity_threshold: float = TOXICITY_THRESHOLD,
    http_client: httpx.AsyncClient | None = None,
    **kwargs,
) -> GuardrailMiddleware:
    """
    Factory function to create a GuardrailMiddleware with common defaults.

    Args:
        server_url: URL of the Guardrail Detection Server
        injection_threshold: Threshold for injection detection
        toxicity_threshold: Threshold for toxicity detection
        http_client: Optional shared AsyncClient instance
        **kwargs: Additional arguments passed to GuardrailMiddleware

    Returns:
        Configured GuardrailMiddleware instance
    """
    return GuardrailMiddleware(
        server_url=server_url,
        injection_threshold=injection_threshold,
        toxicity_threshold=toxicity_threshold,
        http_client=http_client,
        **kwargs,
    )


async def check_guardrail_server_health(
    server_url: str = GUARDRAIL_SERVER_URL,
    timeout: float = 5.0,
) -> bool:
    """
    Check if the guardrail server is running and healthy.

    Args:
        server_url: URL of the Guardrail Detection Server
        timeout: Request timeout in seconds

    Returns:
        True if server is healthy, False otherwise
    """
    client = GuardrailClient(base_url=server_url, timeout=timeout)
    try:
        health = await client.health_check()
        return health.get("status") == "healthy"
    finally:
        await client.close()
