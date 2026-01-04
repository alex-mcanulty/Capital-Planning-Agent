# LangChain Guardrail Middleware

A server-client architecture for adding input and output guardrails to LangChain agents.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Your LangChain Agent                       │
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐  │
│  │  User Input     │──▶│  Guardrail      │───▶│  Agent      │  │
│  │                 │    │  Middleware     │    │  Execution  │  │
│  └─────────────────┘    └────────┬────────┘    └──────┬──────┘  │
│                                  │                     │        │
│                                  ▼                     ▼        │
│                         ┌────────────────┐    ┌─────────────┐  │
│                         │  HTTP Client   │    │  Output     │  │
│                         │                │    │  Check      │  │
│                         └────────┬───────┘    └──────┬──────┘  │
└──────────────────────────────────┼───────────────────┼─────────┘
                                   │                   │
                                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Guardrail Detection Server                   │
│                       (localhost:8004)                          │
│                                                                 │
│  ┌─────────────────────────┐  ┌─────────────────────────┐      │
│  │  Injection Detector     │  │  Toxicity Detector      │      │
│  │  (DeBERTa, 184M params) │  │  (RoBERTa, 38M params)  │      │
│  └─────────────────────────┘  └─────────────────────────┘      │
│                                                                 │
│  Models loaded once at startup, kept in memory for fast        │
│  inference on all requests.                                     │
└─────────────────────────────────────────────────────────────────┘
```

## Project Structure

```
├── guardrail_server.py      # FastAPI server with loaded models
├── guardrail_middleware.py  # LangChain middleware (API client)
├── example_usage.py         # Example LangChain agent integration
├── test_detector.py         # Test script for the API
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start the Server

```bash
python guardrail_server.py
```

The server will:
- Load both detection models into memory
- Start listening on `http://localhost:8004`
- Be ready to handle detection requests

### 3. Test the Server

In a new terminal:

```bash
# Run benchmark tests
python test_detector.py

# Test only injection detection
python test_detector.py --detector injection

# Test only toxicity detection
python test_detector.py --detector hap

# Interactive testing
python test_detector.py --interactive

# Custom threshold
python test_detector.py --threshold 0.7
```

### 4. Use with LangChain Agent

```python
from guardrail_middleware import GuardrailMiddleware
from langchain.agents import create_agent

# Create middleware (connects to server)
guardrails = GuardrailMiddleware(
    server_url="http://localhost:8004",
    injection_threshold=0.5,
    toxicity_threshold=0.5,
)

# Create agent with guardrails
agent = create_agent(
    model="gpt-4o",
    tools=[...],
    middleware=[guardrails],
)

# Use the agent - guardrails are automatic!
result = agent.invoke({"messages": [...]})
```

## API Endpoints

### Health Check
```
GET /health
```
Returns server status, loaded models, and uptime.

### Detect Prompt Injection
```
POST /detect/injection
Content-Type: application/json

{
    "text": "Your text to analyze",
    "threshold": 0.5
}
```

### Detect Toxicity
```
POST /detect/toxicity
Content-Type: application/json

{
    "text": "Your text to analyze",
    "threshold": 0.5
}
```

### Batch Toxicity Detection
```
POST /detect/toxicity/batch
Content-Type: application/json

{
    "texts": ["text1", "text2", "text3"],
    "threshold": 0.5
}
```

## Models Used

| Guardrail | Model | Size | Purpose |
|-----------|-------|------|---------|
| Input | `protectai/deberta-v3-base-prompt-injection-v2` | 184M | Prompt injection detection |
| Output | `ibm-granite/granite-guardian-hap-38m` | 38M | Hate/Abuse/Profanity detection |

## Configuration

### Server Configuration

Edit `guardrail_server.py`:

```python
class ServerConfig:
    HOST: str = "0.0.0.0"
    PORT: int = 8004
    MAX_LENGTH: int = 512
    DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"
```

### Middleware Configuration

```python
GuardrailMiddleware(
    # Server
    server_url="http://localhost:8004",
    timeout=10.0,
    
    # Input guardrail
    enable_input_guardrail=True,
    injection_threshold=0.5,
    input_refusal_message="Custom refusal message",
    
    # Output guardrail
    enable_output_guardrail=True,
    toxicity_threshold=0.5,
    output_refusal_message="Custom refusal message",
    
    # Callbacks
    on_injection_detected=my_callback,
    on_toxicity_detected=my_callback,
)
```

## Threshold Tuning

- **Lower threshold (0.3)**: More sensitive, catches more attacks but may have false positives
- **Default threshold (0.5)**: Balanced sensitivity
- **Higher threshold (0.7)**: Less sensitive, fewer false positives but may miss some attacks

Use the test script to evaluate different thresholds:

```bash
python test_detector.py --threshold 0.3  # More strict
python test_detector.py --threshold 0.7  # More permissive
```

## Production Deployment

For production, consider:

1. **Run server with Gunicorn/multiple workers**:
   ```bash
   gunicorn guardrail_server:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8004
   ```

2. **Use GPU if available** - models will auto-detect CUDA

3. **Add authentication** to the server endpoints

4. **Monitor with the callbacks** for security alerting

5. **Load balance** multiple server instances for high availability
