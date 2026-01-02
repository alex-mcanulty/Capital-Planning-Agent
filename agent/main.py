"""FastAPI Agent Service for Capital Planning.

This service provides a chatbot interface that streams responses from the
LangGraph agent using Server-Sent Events (SSE).
"""
import os
import asyncio
import logging
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from langchain_openai import ChatOpenAI
from langsmith import traceable
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient

from .agent_instruction import capital_planner_instruction

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure LangSmith
os.environ["LANGSMITH_PROJECT"] = "Capital Planner Agent"
os.environ["LANGSMITH_TRACING"] = "true"

# Global variables for agent and MCP client
llm = None
mcp_client = None
mcp_tools = None
agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources."""
    global llm, mcp_client, mcp_tools, agent

    logger.info("[Agent] Starting Capital Planning Agent Service")

    # Initialize LLM
    llm = ChatOpenAI(
        model_name="gpt-4o-mini-2024-07-18"
    )

    # Initialize MCP client
    mcp_client = MultiServerMCPClient(
        {
            "capital_planner_tools": {
                "transport": "http",
                "url": "http://localhost:8002/mcp",
            }
        }
    )

    # Get tools from MCP server
    logger.info("[Agent] Connecting to MCP server and loading tools...")
    mcp_tools = await mcp_client.get_tools()
    logger.info(f"[Agent] Loaded {len(mcp_tools)} tools from MCP server")

    # Create agent
    agent = create_agent(
        model=llm,
        tools=mcp_tools,
        system_prompt=capital_planner_instruction
    )

    logger.info("[Agent] Agent initialized successfully")

    yield

    # Cleanup
    logger.info("[Agent] Shutting down...")
    if mcp_client:
        # MCP client cleanup if needed
        pass


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
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation history"
    )
    # Authentication tokens from frontend user
    access_token: str = Field(..., description="User's access token from OIDC")
    refresh_token: str = Field(..., description="User's refresh token from OIDC")
    expires_in: int = Field(..., description="Access token lifetime in seconds")
    scopes: list[str] = Field(..., description="User's granted scopes")
    user_id: str = Field(..., description="User identifier (sub claim)")


# ==============================================================================
# API Endpoints
# ==============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "capital-planning-agent",
        "agent_ready": agent is not None
    }


async def authenticate_mcp_session(
    access_token: str,
    refresh_token: str,
    expires_in: int,
    scopes: list[str],
    user_id: str
) -> None:
    """Authenticate with the MCP server using user's tokens.

    This establishes a session in the MCP server that will be used
    for all subsequent tool calls. The MCP server will automatically
    refresh the tokens as needed.
    """
    # Find the capital_authenticate tool
    authenticate_tool = None
    for tool in mcp_tools:
        if hasattr(tool, 'name') and tool.name == 'capital_authenticate':
            authenticate_tool = tool
            break

    if not authenticate_tool:
        raise RuntimeError("capital_authenticate tool not found in MCP tools")

    # Invoke the authentication tool
    result = await authenticate_tool.ainvoke({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "refresh_expires_in": 30,  # Default from OIDC config
        "scopes": scopes,
        "user_id": user_id
    })

    logger.info(f"[Agent] MCP session authenticated for user: {user_id}")
    logger.debug(f"[Agent] Authentication result: {result}")


@traceable()
async def stream_agent_response(
    user_message: str,
    history: list[ChatMessage],
    access_token: str,
    refresh_token: str,
    expires_in: int,
    scopes: list[str],
    user_id: str
) -> AsyncGenerator[str, None]:
    """Stream agent responses as SSE events.

    Yields SSE-formatted messages with the following event types:
    - message_start: Indicates a new message is starting
    - message_chunk: Content chunk for the current message
    - tool_call: Indicates a tool is being called
    - message_end: Indicates the message is complete
    - error: An error occurred
    """
    try:
        # First, authenticate with MCP server using user's tokens
        yield f"event: authenticating\n"
        yield f"data: Establishing session...\n\n"

        await authenticate_mcp_session(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=expires_in,
            scopes=scopes,
            user_id=user_id
        )
        # Convert history to LangChain format
        lc_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in history
        ]
        lc_messages.append({"role": "user", "content": user_message})

        # Track current message
        current_message_content = ""
        message_started = False

        # Stream agent responses
        async for chunk in agent.astream({"messages": lc_messages}):
            logger.debug(f"[Agent] Chunk: {chunk}")

            message_type = next(iter(chunk))

            if message_type == "tools":
                # Tool call event
                for step in chunk["tools"]:
                    tool_name = chunk[message_type]['messages'][0].name
                    yield f"event: tool_call\n"
                    yield f"data: {tool_name}\n\n"

            elif message_type == "model":
                # Message content from model
                chunk_content = chunk[message_type]['messages'][0].content

                # Remove thinking tags if present
                chunk_content = chunk_content.split("</think>")[-1].strip()

                if not chunk_content:
                    chunk_content = "Thinking..."

                # Send message_start event if not started
                if not message_started:
                    yield f"event: message_start\n"
                    yield f"data: assistant\n\n"
                    message_started = True

                # Send content chunk
                yield f"event: message_chunk\n"
                yield f"data: {chunk_content}\n\n"

                current_message_content = chunk_content

        # Send message_end event
        if message_started:
            yield f"event: message_end\n"
            yield f"data: \n\n"

    except Exception as e:
        logger.error(f"[Agent] Error during streaming: {e}", exc_info=True)
        yield f"event: error\n"
        yield f"data: {str(e)}\n\n"


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream chat responses using Server-Sent Events.

    The response stream contains SSE events with the following types:
    - message_start: New message starting
    - message_chunk: Content chunk
    - tool_call: Tool being used
    - message_end: Message complete
    - error: Error occurred
    """
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized. Please try again later."
        )

    return StreamingResponse(
        stream_agent_response(
            request.message,
            request.history,
            request.access_token,
            request.refresh_token,
            request.expires_in,
            request.scopes,
            request.user_id
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

    Returns the complete response after the agent finishes.
    """
    if not agent:
        raise HTTPException(
            status_code=503,
            detail="Agent not initialized. Please try again later."
        )

    # Authenticate with MCP server
    try:
        await authenticate_mcp_session(
            access_token=request.access_token,
            refresh_token=request.refresh_token,
            expires_in=request.expires_in,
            scopes=request.scopes,
            user_id=request.user_id
        )
    except Exception as e:
        logger.error(f"[Agent] Authentication failed: {e}", exc_info=True)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

    # Convert history to LangChain format
    lc_messages = [
        {"role": msg.role, "content": msg.content}
        for msg in request.history
    ]
    lc_messages.append({"role": "user", "content": request.message})

    # Get response
    try:
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


if __name__ == "__main__":
    import uvicorn

    logger.info("[Agent] Starting Capital Planning Agent Service on port 8003")
    uvicorn.run(app, host="0.0.0.0", port=8003)
