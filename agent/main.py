import os
import asyncio 

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

@traceable()
async def converse_agent(prompt, messages):
    lc_messages = messages.copy()
    messages.append(ChatMessage(role="user", content=prompt))
    yield messages

    lc_messages.append({"role": "user", "content": prompt})

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

if __name__ == "__main__":
    demo.launch(share=True, server_port=6111)
    