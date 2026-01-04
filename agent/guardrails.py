from typing import Any
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime


class CustomGuardrailMiddleware(AgentMiddleware):
    """
    Combined input/output guardrail middleware.
    """
    
    def __init__(
        self,
        banned_input_keywords: list[str] | None = None,
        banned_output_keywords: list[str] | None = None,
        input_refusal_message: str = "I cannot process this request.",
        output_refusal_message: str = "I cannot provide that information.",
    ):
        super().__init__()
        self.banned_input_keywords = [kw.lower() for kw in (banned_input_keywords or [])]
        self.banned_output_keywords = [kw.lower() for kw in (banned_output_keywords or [])]
        self.input_refusal_message = input_refusal_message
        self.output_refusal_message = output_refusal_message
    
    @hook_config(can_jump_to=["end"])
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Check input before agent runs."""
        messages = state.get("messages", [])
        if not messages:
            return None
        
        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None
        
        user_input = str(last_message.content).lower()
        
        # Your detection logic here
        if self._detect_input_attack(user_input):
            return {
                "messages": [AIMessage(content=self.input_refusal_message)],
                "jump_to": "end"
            }
        
        return None
    
    @hook_config(can_jump_to=["end"])
    def after_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        """Check output after agent completes."""
        messages = state.get("messages", [])
        if not messages:
            return None
        
        last_message = messages[-1]
        if not isinstance(last_message, AIMessage):
            return None
        
        agent_output = str(last_message.content).lower()
        
        # Your detection logic here
        if self._detect_harmful_output(agent_output):
            return {
                "messages": [AIMessage(content=self.output_refusal_message)],
                "jump_to": "end"
            }
        
        return None
    
    def _detect_input_attack(self, text: str) -> bool:
        """Replace with your actual detection logic."""
        for keyword in self.banned_input_keywords:
            if keyword in text:
                return True
        return False
    
    def _detect_harmful_output(self, text: str) -> bool:
        """Replace with your actual detection logic."""
        for keyword in self.banned_output_keywords:
            if keyword in text:
                return True
        return False
