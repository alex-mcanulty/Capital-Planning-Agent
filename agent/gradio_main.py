import os
import asyncio 
import requests

from langchain_openai import ChatOpenAI
from langsmith import traceable
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient  

from agent_instruction import capital_planner_instruction

os.environ["LANGSMITH_PROJECT"] = "Capital Planner Agent"
os.environ["LANGSMITH_TRACING"] = "true"

llm = ChatOpenAI(
    model_name="gpt-5-mini-2025-08-07"
    # model_name="qwen/qwen3-next-80b",
    # base_url="http://127.0.0.1:1234/v1"
)

mcp_client = MultiServerMCPClient(
    {
        "capital_planner_tools": {
            "transport": "http",
            "url": "http://localhost:8002/mcp",
        }
    }
)

mcp_tools = asyncio.run(mcp_client.get_tools())

agent = create_agent(model=llm, tools=mcp_tools, system_prompt=capital_planner_instruction)

import gradio as gr
from gradio import ChatMessage

# OIDC Server Configuration
OIDC_SERVER_URL = "http://localhost:8000"
CLIENT_ID = "capital-planning-client"

def authenticate(username, password):
    """Authenticate user against OIDC server"""
    try:
        response = requests.get(
            f"{OIDC_SERVER_URL}/authorize",
            params={
                "username": username,
                "password": password,
                "client_id": CLIENT_ID,
                "response_type": "code"
            }
        )
        if response.status_code == 200 and "code" in response.json():
            return True
        return False
    except Exception as e:
        print(f"[AUTH] Authentication error: {e}")
        return False

def logout(request: gr.Request):
    print("logged out")


@traceable()
async def converse_agent(prompt, messages, request: gr.Request):
    lc_messages = messages.copy()
    messages.append(ChatMessage(role="user", content=prompt))
    yield messages

    lc_messages.append({"role": "user", "content": prompt})

    session_id = request.session_hash
    tokens = user_tokens.get(session_id)

    if not tokens:
        # Handle missing auth
        return

    async with mcp_client.session("capital_planner_tools") as session:
        tools = await load_mcp_tools(session)
        
        # Find and call the authenticate tool directly
        auth_tool = next(t for t in tools if t.name == "capital_authenticate")
        await auth_tool.ainvoke({
            "params": {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_in": tokens.get("expires_in", 3600),
                "refresh_expires_in": tokens.get("refresh_expires_in", 3600),
                "scopes": tokens.get("scope", "").split(),
                "user_id": tokens.get("sub", "unknown"),
            }
        })
        
        # Now run the agent - session is already established
        agent = create_agent(model=llm, tools=tools, system_prompt=capital_planner_instruction)
        
        async for chunk in agent.astream(
            {"messages": lc_messages}
        ):
            print("")
            print(chunk)

            message_type = next(iter(chunk))

            if message_type == "tools":
                for step in chunk["tools"]:
                    messages.append(ChatMessage(role="assistant", content=chunk[message_type]['messages'][0].name,
                                    metadata={"title": f"🛠️ Used tool {chunk[message_type]['messages'][0].name}"}))
                    yield messages
            if message_type == "model":
                chunk_content = chunk[message_type]['messages'][0].content.split("</think>")[-1].strip()
                if not chunk_content: 
                    chunk_content = "Thinking..."
                messages.append(ChatMessage(role="assistant", content=chunk_content))
                yield messages

with gr.Blocks() as demo:
    chatbot = gr.Chatbot(
        label="Capital Planner Agent",
    )
    input = gr.Textbox(lines=1, label="Chat Message", value="Analyze the top 5 assets at risk of failure and propose an optimized investment plan for next year.")
    input.submit(converse_agent, [input, chatbot], [chatbot])
    logout_button = gr.Button(value = "Logout")
    logout_button.click(logout)

if __name__ == "__main__":
    demo.launch(auth=authenticate, share=True, server_port=6111)
