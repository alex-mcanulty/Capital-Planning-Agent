# LangChain Structured Output Guide for Agents

A comprehensive guide to structuring the final output of LangChain agents using `create_agent()` with `response_format`.

---

## Table of Contents

1. [Overview](#overview)
2. [Schema Types](#schema-types)
3. [Output Strategies](#output-strategies)
4. [Basic Examples](#basic-examples)
5. [Error Handling](#error-handling)
6. [Advanced Patterns](#advanced-patterns)
7. [Best Practices](#best-practices)
8. [Provider Support](#provider-support)

---

## Overview

LangChain allows you to constrain an agent's final response to follow a defined schema using the `response_format` parameter. This ensures the output can be easily parsed and used in downstream processing.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **`response_format`** | Parameter on `create_agent()` that defines the output schema |
| **`structured_response`** | Key in the result dict containing the parsed output |
| **`ToolStrategy`** | Uses tool calling to enforce structure (works with all models) |
| **`ProviderStrategy`** | Uses native provider structured output (more reliable, limited models) |

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent Execution                         │
│                                                             │
│  1. Agent receives user message                             │
│  2. Agent calls tools as needed (loop)                      │
│  3. When done with tools, agent generates final response    │
│  4. Response is coerced into the specified schema           │
│  5. Parsed output returned in result["structured_response"] │
└─────────────────────────────────────────────────────────────┘
```

---

## Schema Types

LangChain supports multiple schema types for defining structured output.

### Pydantic Models (Recommended)

Pydantic provides the richest feature set with field validation, descriptions, and nested structures.

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class ContactInfo(BaseModel):
    """Extracted contact information."""
    
    name: str = Field(..., description="Full name of the person")
    email: str = Field(..., description="Email address")
    phone: Optional[str] = Field(None, description="Phone number if available")
    tags: List[str] = Field(default_factory=list, description="Relevant tags")
```

### Dataclasses

Python dataclasses work for simpler schemas.

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class WeatherResponse:
    """Weather information response."""
    temperature: float
    condition: str
    humidity: Optional[float] = None
```

### TypedDict

For when you don't need runtime validation.

```python
from typing import TypedDict, Optional

class AnalysisResult(TypedDict):
    summary: str
    sentiment: str
    confidence: float
```

---

## Output Strategies

LangChain v1+ requires you to explicitly choose a strategy for structured output.

### ToolStrategy

Uses tool calling to enforce structure. Works with **all models that support tool calling**.

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel

class OutputSchema(BaseModel):
    answer: str
    reasoning: str

agent = create_agent(
    model="gpt-4o-mini",
    tools=[...],
    response_format=ToolStrategy(OutputSchema)
)
```

**How it works:**
1. The schema is converted to a tool definition
2. The agent calls this "tool" to produce structured output
3. The tool call arguments are parsed into your schema

**Pros:**
- Works with any model supporting tool calling
- Reliable across providers

**Cons:**
- Slightly higher latency (tool call overhead)
- May occasionally produce parsing errors

### ProviderStrategy

Uses the model provider's **native structured output** feature. More reliable but limited to supported providers.

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from pydantic import BaseModel

class OutputSchema(BaseModel):
    answer: str
    reasoning: str

agent = create_agent(
    model="gpt-4o",  # Must support native structured output
    tools=[...],
    response_format=ProviderStrategy(OutputSchema)
)
```

**Supported Providers:**
- OpenAI (gpt-4o, gpt-4o-mini, etc.)
- Anthropic (Claude models)
- Google (Gemini models)
- xAI (Grok models)

**Pros:**
- Higher reliability (provider enforces schema)
- Often faster than ToolStrategy

**Cons:**
- Limited to supported providers
- May not work with all model variants

### Automatic Strategy Selection

In LangChain 1.1+, passing a schema directly auto-selects the best strategy:

```python
# LangChain auto-selects ProviderStrategy if supported, else ToolStrategy
agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=OutputSchema  # Direct schema (auto-select)
)
```

> **Note:** As of LangChain 1.0, you should explicitly use `ToolStrategy` or `ProviderStrategy` for clarity.

---

## Basic Examples

### Example 1: Simple Extraction

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field

class ContactInfo(BaseModel):
    """Extracted contact information."""
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    phone: str = Field(..., description="Phone number")

agent = create_agent(
    model="gpt-4o-mini",
    tools=[],
    response_format=ToolStrategy(ContactInfo)
)

result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Extract: John Doe, [email protected], (555) 123-4567"
    }]
})

contact = result["structured_response"]
print(contact)
# ContactInfo(name='John Doe', email='[email protected]', phone='(555) 123-4567')

# Access fields directly
print(contact.name)   # 'John Doe'
print(contact.email)  # '[email protected]'
```

### Example 2: Agent with Tools + Structured Output

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field

# Define a tool
@tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"It's sunny and 72°F in {city}."

# Define output schema
class WeatherReport(BaseModel):
    """Structured weather report."""
    temperature: float = Field(..., description="Temperature in Fahrenheit")
    condition: str = Field(..., description="Weather condition")
    location: str = Field(..., description="Location queried")

# Create agent
agent = create_agent(
    model="gpt-4o-mini",
    tools=[get_weather],
    response_format=ToolStrategy(WeatherReport)
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "What's the weather in NYC?"}]
})

report = result["structured_response"]
# WeatherReport(temperature=72.0, condition='sunny', location='NYC')
```

### Example 3: Using ProviderStrategy with Anthropic

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ProviderStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field

@tool
def search_database(query: str) -> str:
    """Search the product database."""
    return "Found: Widget Pro - $49.99, 4.5 stars, 120 reviews"

class ProductAnalysis(BaseModel):
    """Analysis of a product search."""
    product_name: str
    price: float
    rating: float
    recommendation: str = Field(..., description="Buy/wait/skip recommendation")

agent = create_agent(
    model="anthropic:claude-sonnet-4-5",
    tools=[search_database],
    response_format=ProviderStrategy(ProductAnalysis)
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Should I buy the Widget Pro?"}]
})

analysis = result["structured_response"]
# ProductAnalysis(product_name='Widget Pro', price=49.99, rating=4.5, recommendation='buy')
```

### Example 4: Optional Fields and Defaults

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class ResearchSummary(BaseModel):
    """Summary of research findings."""
    
    topic: str = Field(..., description="Main topic researched")
    summary: str = Field(..., description="Brief summary of findings")
    
    # Optional fields
    sources: Optional[List[str]] = Field(
        None, 
        description="List of sources if available"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Confidence score 0-1"
    )
    
    # Field with choices
    category: str = Field(
        ...,
        description="Category: 'science', 'technology', 'business', or 'other'"
    )

agent = create_agent(
    model="gpt-4o",
    tools=[search_tool],
    response_format=ToolStrategy(ResearchSummary)
)
```

### Example 5: Using Dataclasses

```python
from dataclasses import dataclass
from typing import Optional
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

@dataclass
class TaskResult:
    """Result of a completed task."""
    status: str
    message: str
    duration_seconds: Optional[float] = None

agent = create_agent(
    model="gpt-4o-mini",
    tools=[...],
    response_format=ToolStrategy(TaskResult)
)

result = agent.invoke({
    "messages": [{"role": "user", "content": "Complete the task"}]
})

task_result = result["structured_response"]
# TaskResult(status='completed', message='Task finished successfully', duration_seconds=2.5)
```

---

## Error Handling

### ToolStrategy Error Handling

Control how errors are handled with the `handle_errors` parameter:

```python
from langchain.agents.structured_output import ToolStrategy

# Default: Retry on errors with a prompt
agent = create_agent(
    model="gpt-4o-mini",
    tools=[...],
    response_format=ToolStrategy(
        OutputSchema,
        handle_errors=True  # Default: retry with error message
    )
)

# Custom error handling
def custom_error_handler(error: Exception) -> str:
    """Return a message to send back to the model for retry."""
    return f"Error parsing output: {error}. Please fix the format."

agent = create_agent(
    model="gpt-4o-mini",
    tools=[...],
    response_format=ToolStrategy(
        OutputSchema,
        handle_errors=custom_error_handler
    )
)
```

### Error Types

| Error | Description | Default Behavior |
|-------|-------------|------------------|
| **Parsing Error** | Model output doesn't match schema | Retry with error message |
| **Multiple Tool Calls** | Model makes 2+ structured output calls | Retry asking to pick one |
| **Validation Error** | Pydantic validation fails | Retry with validation error |

### Custom Tool Message Content

Customize the message shown in conversation history when structured output is generated:

```python
agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=ToolStrategy(
        MeetingNotes,
        tool_message_content="Meeting notes captured successfully!"
    )
)
```

---

## Advanced Patterns

### Dynamic Response Format with Middleware

Select different response formats based on context:

```python
from langchain.agents import create_agent
from langchain.agents.middleware import wrap_model_call, ModelRequest, ModelResponse
from langchain.agents.structured_output import ToolStrategy
from dataclasses import dataclass
from typing import Callable

@dataclass
class Context:
    output_format: str  # "simple" or "detailed"

class SimpleOutput(BaseModel):
    answer: str

class DetailedOutput(BaseModel):
    answer: str
    reasoning: str
    confidence: float
    sources: list[str]

@wrap_model_call
def dynamic_response_format(
    request: ModelRequest,
    handler: Callable[[ModelRequest], ModelResponse]
) -> ModelResponse:
    output_format = request.runtime.context.output_format
    
    if output_format == "detailed":
        schema = DetailedOutput
    else:
        schema = SimpleOutput
    
    # Note: This pattern requires manual handling in practice
    # The response_format is typically set at agent creation time
    return handler(request)

# In practice, create separate agents for different formats:
simple_agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=ToolStrategy(SimpleOutput)
)

detailed_agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=ToolStrategy(DetailedOutput)
)
```

### Nested Schemas

Use nested Pydantic models for complex structures:

```python
from pydantic import BaseModel, Field
from typing import List

class Address(BaseModel):
    street: str
    city: str
    country: str
    postal_code: str

class Person(BaseModel):
    name: str
    email: str
    address: Address  # Nested model

class CompanyInfo(BaseModel):
    company_name: str
    employees: List[Person]  # List of nested models
    headquarters: Address

agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=ToolStrategy(CompanyInfo)
)
```

### Enums and Constrained Types

Use enums and validators for constrained output:

```python
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from typing import Literal

class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TicketAnalysis(BaseModel):
    title: str
    priority: Priority  # Enum constraint
    category: Literal["bug", "feature", "question"]  # Literal constraint
    estimated_hours: float = Field(..., ge=0, le=100)  # Range constraint
    
    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Title cannot be empty")
        return v.strip()
```

### Combining with Memory

Structured output works with agent memory:

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel

class ConversationSummary(BaseModel):
    topic: str
    key_points: list[str]
    next_steps: list[str]

agent = create_agent(
    model="gpt-4o",
    tools=[...],
    response_format=ToolStrategy(ConversationSummary),
    checkpointer=InMemorySaver()  # Enable memory
)

# First turn
result1 = agent.invoke(
    {"messages": [{"role": "user", "content": "Let's discuss project planning"}]},
    config={"configurable": {"thread_id": "session-1"}}
)

# Second turn (remembers context)
result2 = agent.invoke(
    {"messages": [{"role": "user", "content": "What did we discuss?"}]},
    config={"configurable": {"thread_id": "session-1"}}
)
```

---

## Best Practices

### 1. Write Descriptive Field Descriptions

Field descriptions guide the model on what to extract:

```python
# ❌ Bad: No descriptions
class Output(BaseModel):
    text: str
    score: float

# ✅ Good: Clear descriptions
class Output(BaseModel):
    text: str = Field(
        ..., 
        description="The main response text, 2-3 sentences"
    )
    score: float = Field(
        ..., 
        ge=0, 
        le=1, 
        description="Confidence score from 0 (uncertain) to 1 (certain)"
    )
```

### 2. Use Appropriate Types

Choose types that match your needs:

```python
from typing import Optional, List, Literal
from pydantic import BaseModel, Field

class WellTypedOutput(BaseModel):
    # Required string
    title: str
    
    # Optional with default
    subtitle: Optional[str] = None
    
    # List of items
    tags: List[str] = Field(default_factory=list)
    
    # Constrained choices
    status: Literal["draft", "published", "archived"]
    
    # Numeric with bounds
    rating: float = Field(..., ge=1, le=5)
```

### 3. Keep Schemas Focused

Don't try to extract everything in one schema:

```python
# ❌ Bad: Too many fields, unfocused
class KitchenSinkOutput(BaseModel):
    summary: str
    entities: list
    sentiment: str
    keywords: list
    categories: list
    language: str
    word_count: int
    # ... 20 more fields

# ✅ Good: Focused on specific task
class SentimentAnalysis(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    confidence: float = Field(..., ge=0, le=1)
    key_phrases: List[str] = Field(..., max_length=5)
```

### 4. Handle Optional Data Gracefully

Use Optional for fields that may not always be present:

```python
class FlexibleOutput(BaseModel):
    # Always required
    main_answer: str
    
    # Optional - model fills if available
    supporting_evidence: Optional[str] = None
    sources: Optional[List[str]] = None
    
    # Default value if not specified
    confidence: float = Field(default=0.5, ge=0, le=1)
```

### 5. Test Schema Before Deployment

Validate your schema works correctly:

```python
def test_schema():
    # Test that schema can be instantiated
    output = OutputSchema(
        field1="test",
        field2=123
    )
    
    # Test validation
    try:
        invalid = OutputSchema(field1="", field2=-1)
        assert False, "Should have raised validation error"
    except ValueError:
        pass  # Expected
```

---

## Provider Support

### Native Structured Output Support

| Provider | Native Support | Strategy |
|----------|---------------|----------|
| **OpenAI** | ✅ gpt-4o, gpt-4o-mini | ProviderStrategy |
| **Anthropic** | ✅ Claude 3+, Claude 4+ | ProviderStrategy |
| **Google** | ✅ Gemini models | ProviderStrategy |
| **xAI** | ✅ Grok models | ProviderStrategy |
| **Others** | Via tool calling | ToolStrategy |

### Checking Model Support

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("gpt-4o")

# Check if model supports structured output
profile = model.profile
if profile.get("structured_output"):
    print("Model supports native structured output")
    # Use ProviderStrategy
else:
    print("Model uses tool calling for structured output")
    # Use ToolStrategy
```

### Custom Model Profiles

Override profile data if needed:

```python
from langchain.chat_models import init_chat_model

custom_profile = {
    "structured_output": True,
    "tool_calling": True,
    # ... other capabilities
}

model = init_chat_model("my-model", profile=custom_profile)
```

---

## Quick Reference

### Imports

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy, ProviderStrategy
from langchain.tools import tool
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from dataclasses import dataclass
```

### Basic Pattern

```python
from pydantic import BaseModel, Field
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy

class MyOutput(BaseModel):
    """Description of output."""
    field1: str = Field(..., description="What this field contains")
    field2: int = Field(..., description="What this field contains")

agent = create_agent(
    model="gpt-4o-mini",
    tools=[...],
    response_format=ToolStrategy(MyOutput)
)

result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
output = result["structured_response"]  # MyOutput instance
```

### Result Structure

```python
result = agent.invoke({"messages": [...]})

# Access structured output
structured = result["structured_response"]  # Your schema instance

# Access raw messages
messages = result["messages"]  # List of all messages

# Access last message content
last_message = result["messages"][-1].content
```

---

*Based on LangChain v1 documentation. For the latest details, see the [official structured output documentation](https://docs.langchain.com/oss/python/langchain/structured-output).*