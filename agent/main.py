"""FastAPI Agent Service for Capital Planning.

This service provides a chatbot interface that streams responses from the
LangGraph agent using Server-Sent Events (SSE).

Session Management:
- Each chat request includes OIDC tokens from the frontend
- Agent creates an MCP session at the start of each invocation
- Agent deletes the MCP session when the invocation completes
- This ensures sessions are scoped to agent invocations, not browser sessions
"""
import os
import asyncio
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langsmith import traceable
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from .agent_instruction import capital_planner_instruction
from .guardrails import (
    GuardrailMiddleware,
    check_guardrail_server_health,
    GUARDRAIL_SERVER_URL,
    GUARDRAIL_ENABLED,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure LangSmith
os.environ["LANGSMITH_PROJECT"] = "Capital Planner Agent"
os.environ["LANGSMITH_TRACING"] = "true"

# MCP Server configuration
MCP_SERVER_URL = "http://localhost:8002/mcp/streamable"
MCP_SESSION_URL = "http://localhost:8002/sessions"

# Global LLM instance (shared across requests)
llm = None

# HTTP client for MCP session management
http_client: httpx.AsyncClient = None

# Guardrail middleware (shared across requests)
guardrails_middleware: GuardrailMiddleware | None = None


async def create_mcp_session(
    access_token: str,
    refresh_token: str,
    scopes: list[str],
    user_id: str
) -> str:
    """Create an MCP session with the provided OIDC tokens.

    Args:
        access_token: OIDC access token
        refresh_token: OIDC refresh token
        scopes: List of granted scopes
        user_id: User identifier

    Returns:
        session_id: The created session ID
    """
    response = await http_client.post(
        MCP_SESSION_URL,
        json={
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scopes": scopes,
            "user_id": user_id
        }
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Failed to create MCP session: {response.text}"
        )

    data = response.json()
    session_id = data["session_id"]
    logger.info(f"[Agent] Created MCP session: {session_id[:16]}...")
    return session_id


async def delete_mcp_session(session_id: str):
    """Delete an MCP session.

    Args:
        session_id: The session ID to delete
    """
    try:
        response = await http_client.delete(f"{MCP_SESSION_URL}/{session_id}")
        if response.status_code == 200:
            logger.info(f"[Agent] Deleted MCP session: {session_id[:16]}...")
        else:
            logger.warning(
                f"[Agent] Failed to delete MCP session {session_id[:16]}...: "
                f"{response.status_code} - {response.text}"
            )
    except Exception as e:
        logger.error(f"[Agent] Error deleting MCP session: {e}")


async def create_agent_with_session(session_id: str):
    """Create an agent with MCP tools configured for a specific session.

    Each request gets its own MCP client with the session_id in headers.
    This ensures per-user session isolation.
    """
    # Create MCP client with session-specific headers
    mcp_client = MultiServerMCPClient(
        {
            "capital_planner_tools": {
                "transport": "streamable_http",
                "url": MCP_SERVER_URL,
                "headers": {
                    "X-Session-ID": session_id,
                }
            }
        }
    )

    # Get tools from MCP server
    mcp_tools = await mcp_client.get_tools()
    logger.info(f"[Agent] Loaded {len(mcp_tools)} tools for session {session_id[:16]}...")

    # Create agent with these tools and guardrails middleware
    middleware = [guardrails_middleware] if guardrails_middleware else []
    agent = create_agent(
        model=llm,
        tools=mcp_tools,
        system_prompt=capital_planner_instruction,
        middleware=middleware,
    )

    return agent, mcp_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global llm, http_client, guardrails_middleware

    logger.info("[Agent] Starting Capital Planning Agent Service")

    # Initialize HTTP client for MCP session management
    http_client = httpx.AsyncClient(timeout=30.0)

    # Initialize LLM (shared across all requests)
    llm = ChatOpenAI(
        model_name="gpt-5-mini-2025-08-07",
        # model_name="qwen3-next-80b-a3b-thinking",
        # base_url="http://127.0.0.1:1234/v1",
        temperature=0
    )

    logger.info("[Agent] LLM initialized, ready to accept requests")

    # Initialize guardrails middleware if enabled
    if GUARDRAIL_ENABLED:
        guardrails_healthy = await check_guardrail_server_health()
        if guardrails_healthy:
            guardrails_middleware = GuardrailMiddleware()
            logger.info(f"[Agent] Guardrails middleware initialized (server={GUARDRAIL_SERVER_URL})")
        else:
            logger.warning(
                f"[Agent] Guardrail server not available at {GUARDRAIL_SERVER_URL} - "
                "running WITHOUT guardrails protection"
            )
            guardrails_middleware = None
    else:
        logger.info("[Agent] Guardrails disabled via GUARDRAIL_ENABLED=false")
        guardrails_middleware = None

    yield

    # Cleanup
    logger.info("[Agent] Shutting down...")
    if guardrails_middleware:
        await guardrails_middleware.client.close()
    if http_client:
        await http_client.aclose()


app = FastAPI(
    title="Capital Planning Agent Service",
    lifespan=lifespan
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# Request/Response Models
# ==============================================================================

class ChatMessage(BaseModel):
    """A chat message."""
    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    metadata: dict | None = Field(default=None, description="Optional metadata")


class ChatRequest(BaseModel):
    """Request for chat endpoint."""
    message: str = Field(..., description="User's message")
    access_token: str = Field(..., description="OIDC access token")
    refresh_token: str = Field(..., description="OIDC refresh token")
    scopes: list[str] = Field(..., description="Granted scopes")
    user_id: str = Field(..., description="User identifier")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation history"
    )


# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "capital-planning-agent",
        "llm_ready": llm is not None,
        "guardrails_enabled": guardrails_middleware is not None,
    }


@traceable()
async def stream_agent_response(
    user_message: str,
    access_token: str,
    refresh_token: str,
    scopes: list[str],
    user_id: str,
    history: list[ChatMessage]
) -> AsyncGenerator[str, None]:
    """Stream agent responses as SSE events.

    Session lifecycle:
    - Creates an MCP session at the start of the agent invocation
    - Deletes the MCP session when the agent completes (success or error)

    Args:
        user_message: The user's message
        access_token: OIDC access token
        refresh_token: OIDC refresh token
        scopes: Granted scopes
        user_id: User identifier
        history: Conversation history

    Yields SSE-formatted messages with the following event types:
    - message_start: Indicates a new message is starting
    - message_chunk: Content chunk for the current message
    - tool_call: Indicates a tool is being called
    - message_end: Indicates the message is complete
    - error: An error occurred
    """
    session_id = None
    try:
        # Create MCP session for this agent invocation
        session_id = await create_mcp_session(access_token, refresh_token, scopes, user_id)

        # Create agent with session-specific MCP client
        logger.info(f"[Agent] Creating agent for session: {session_id[:16]}...")
        agent, mcp_client = await create_agent_with_session(session_id)

        # Convert history to LangChain format
        lc_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]
        lc_messages.append({"role": "user", "content": user_message})

        # Track current message
        current_message_content = ""
        message_started = False
        chunk_count = 0

        logger.info(f"[Agent] Starting to stream response for message: {user_message[:50]}...")

        # Stream agent responses
        async for chunk in agent.astream({"messages": lc_messages}):
            chunk_count += 1
            logger.info(f"[Agent] Chunk #{chunk_count}: {chunk.keys() if isinstance(chunk, dict) else type(chunk)}")

            message_type = next(iter(chunk))
            logger.info(f"[Agent] Message type: {message_type}")

            if message_type == "tools":
                # Tool call event
                for step in chunk["tools"]:
                    tool_name = chunk[message_type]['messages'][0].name
                    logger.info(f"[Agent] Tool call: {tool_name}")
                    yield f"event: tool_call\n"
                    yield f"data: {tool_name}\n\n"

            elif message_type == "model":
                # Message content from model
                chunk_content = chunk[message_type]['messages'][0].content
                logger.info(f"[Agent] Model content (raw, {len(chunk_content)} chars): {chunk_content[:200]}...")

                # Remove thinking tags if present
                chunk_content = chunk_content.split("</think>")[-1].strip()

                if not chunk_content:
                    chunk_content = "Thinking..."

                # Send message_start event if not started
                if not message_started:
                    logger.info("[Agent] Sending message_start event")
                    yield f"event: message_start\n"
                    yield f"data: assistant\n\n"
                    message_started = True

                # Send content chunk
                # For SSE, multi-line data must be sent as multiple "data:" lines
                logger.info(f"[Agent] Sending message_chunk ({len(chunk_content)} chars): {chunk_content[:200]}...")
                yield f"event: message_chunk\n"

                # Split content by newlines and send each line as a separate data: field
                for line in chunk_content.split('\n'):
                    yield f"data: {line}\n"
                yield f"\n"  # Empty line to end the SSE message

                current_message_content = chunk_content
            else:
                logger.warning(f"[Agent] Unexpected message type: {message_type}")

        # Send message_end event
        logger.info(f"[Agent] Stream complete. Total chunks: {chunk_count}, message_started: {message_started}")
        if message_started:
            logger.info("[Agent] Sending message_end event")
            yield f"event: message_end\n"
            yield f"data: \n\n"
        else:
            logger.warning("[Agent] Stream ended but no message was started!")

    except Exception as e:
        logger.error(f"[Agent] Error during streaming: {e}", exc_info=True)
        yield f"event: error\n"
        yield f"data: {str(e)}\n\n"

    finally:
        # Always clean up the MCP session
        if session_id:
            await delete_mcp_session(session_id)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat responses using Server-Sent Events.

    Session lifecycle:
    - MCP session is created at the start of the agent invocation
    - MCP session is deleted when the agent completes

    The response stream contains SSE events with the following types:
    - message_start: New message starting
    - message_chunk: Content chunk
    - tool_call: Tool being used
    - message_end: Message complete
    - error: Error occurred
    """
    if not llm:
        raise HTTPException(
            status_code=503,
            detail="LLM not initialized. Please try again later."
        )

    return StreamingResponse(
        stream_agent_response(
            request.message,
            request.access_token,
            request.refresh_token,
            request.scopes,
            request.user_id,
            request.history
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


@app.post("/chat")
async def chat(request: ChatRequest):
    """Non-streaming chat endpoint (for testing).

    Session lifecycle:
    - MCP session is created at the start of the agent invocation
    - MCP session is deleted when the agent completes

    Returns the complete response after the agent finishes.
    """
    if not llm:
        raise HTTPException(
            status_code=503,
            detail="LLM not initialized. Please try again later."
        )

    session_id = None
    try:
        # Create MCP session for this agent invocation
        session_id = await create_mcp_session(
            request.access_token,
            request.refresh_token,
            request.scopes,
            request.user_id
        )

        # Create agent with session-specific MCP client
        logger.info(f"[Agent] Creating agent for session: {session_id[:16]}...")
        agent, mcp_client = await create_agent_with_session(session_id)

        # Convert history to LangChain format
        lc_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]
        lc_messages.append({"role": "user", "content": request.message})

        # Get response
        result = await agent.ainvoke({"messages": lc_messages})

        # Extract final message
        final_message = result["messages"][-1].content

        return {
            "role": "assistant",
            "content": final_message
        }
    except Exception as e:
        logger.error(f"[Agent] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Always clean up the MCP session
        if session_id:
            await delete_mcp_session(session_id)


if __name__ == "__main__":
    import uvicorn

    logger.info("[Agent] Starting Capital Planning Agent Service on port 8003")
    uvicorn.run(app, host="0.0.0.0", port=8003)
