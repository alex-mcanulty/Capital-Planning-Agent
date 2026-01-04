"""
Guardrail Detection Server

A FastAPI server that loads detection models once at startup and serves
inference requests via REST API endpoints.

Models:
- Input (prompt injection): protectai/deberta-v3-base-prompt-injection-v2
- Output (toxicity/HAP): ibm-granite/granite-guardian-hap-38m

Usage:
    python guardrail_server.py
    # Or with uvicorn directly:
    uvicorn guardrail_server:app --host 0.0.0.0 --port 8004

Endpoints:
    POST /detect/injection  - Check text for prompt injection
    POST /detect/toxicity   - Check text for toxicity (HAP)
    GET  /health            - Health check
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    pipeline,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

class ServerConfig:
    """Server configuration."""
    HOST: str = "0.0.0.0"
    PORT: int = 8004
    
    # Model IDs
    INJECTION_MODEL_ID: str = "protectai/deberta-v3-base-prompt-injection-v2"
    HAP_MODEL_ID: str = "ibm-granite/granite-guardian-hap-38m"
    
    # Inference settings
    MAX_LENGTH: int = 512
    DEVICE: str = "cuda" if torch.cuda.is_available() else "cpu"


config = ServerConfig()


# =============================================================================
# Request/Response Models
# =============================================================================

class DetectionRequest(BaseModel):
    """Request model for detection endpoints."""
    text: str = Field(..., description="Text to analyze", min_length=1)
    threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for detection (0.0-1.0)"
    )


class DetectionResponse(BaseModel):
    """Response model for detection endpoints."""
    detected: bool = Field(..., description="Whether the content was detected as problematic")
    score: float = Field(..., description="Model confidence score (0.0-1.0)")
    label: str = Field(..., description="Classification label")
    threshold: float = Field(..., description="Threshold used for detection")
    inference_time_ms: float = Field(..., description="Inference time in milliseconds")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""
    status: str
    models_loaded: dict[str, bool]
    device: str
    uptime_seconds: float


class BatchDetectionRequest(BaseModel):
    """Request model for batch detection."""
    texts: list[str] = Field(..., description="List of texts to analyze", min_length=1)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class BatchDetectionResponse(BaseModel):
    """Response model for batch detection."""
    results: list[DetectionResponse]
    total_inference_time_ms: float


# =============================================================================
# Model Manager
# =============================================================================

class ModelManager:
    """Manages loading and inference for detection models."""
    
    def __init__(self):
        self.injection_classifier = None
        self.hap_model = None
        self.hap_tokenizer = None
        self.device = config.DEVICE
        self.start_time = None
        
    def load_models(self):
        """Load all models into memory."""
        self.start_time = time.time()
        
        logger.info(f"Loading models on device: {self.device}")
        
        # Load prompt injection model
        logger.info(f"Loading injection model: {config.INJECTION_MODEL_ID}")
        injection_tokenizer = AutoTokenizer.from_pretrained(config.INJECTION_MODEL_ID)
        injection_model = AutoModelForSequenceClassification.from_pretrained(
            config.INJECTION_MODEL_ID
        )
        self.injection_classifier = pipeline(
            "text-classification",
            model=injection_model,
            tokenizer=injection_tokenizer,
            truncation=True,
            max_length=config.MAX_LENGTH,
            device=torch.device(self.device),
        )
        logger.info("Injection model loaded successfully")
        
        # Load HAP model
        logger.info(f"Loading HAP model: {config.HAP_MODEL_ID}")
        self.hap_tokenizer = AutoTokenizer.from_pretrained(config.HAP_MODEL_ID)
        self.hap_model = AutoModelForSequenceClassification.from_pretrained(
            config.HAP_MODEL_ID
        )
        if self.device == "cuda":
            self.hap_model = self.hap_model.to(self.device)
        self.hap_model.eval()
        logger.info("HAP model loaded successfully")
        
        logger.info("All models loaded and ready!")
    
    def detect_injection(self, text: str, threshold: float = 0.5) -> dict[str, Any]:
        """Detect prompt injection in text."""
        start = time.time()
        
        result = self.injection_classifier(text)[0]
        label = result["label"]
        score = result["score"]
        
        # Model outputs INJECTION or SAFE
        if label == "INJECTION":
            detected = score >= threshold
        else:
            detected = False
            
        elapsed_ms = (time.time() - start) * 1000
        
        return {
            "detected": detected,
            "score": score,
            "label": label,
            "threshold": threshold,
            "inference_time_ms": round(elapsed_ms, 2),
        }
    
    def detect_toxicity(self, text: str, threshold: float = 0.5) -> dict[str, Any]:
        """Detect toxicity (HAP) in text."""
        start = time.time()
        
        inputs = self.hap_tokenizer(
            text,
            padding=True,
            truncation=True,
            max_length=config.MAX_LENGTH,
            return_tensors="pt",
        )
        
        if self.device == "cuda":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            logits = self.hap_model(**inputs).logits
            probabilities = torch.softmax(logits, dim=1)
            toxicity_prob = probabilities[0, 1].item()
        
        detected = toxicity_prob >= threshold
        label = "TOXIC" if detected else "SAFE"
        
        elapsed_ms = (time.time() - start) * 1000
        
        return {
            "detected": detected,
            "score": toxicity_prob,
            "label": label,
            "threshold": threshold,
            "inference_time_ms": round(elapsed_ms, 2),
        }
    
    def detect_toxicity_batch(
        self, texts: list[str], threshold: float = 0.5
    ) -> list[dict[str, Any]]:
        """Detect toxicity in a batch of texts."""
        start = time.time()
        
        inputs = self.hap_tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=config.MAX_LENGTH,
            return_tensors="pt",
        )
        
        if self.device == "cuda":
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            logits = self.hap_model(**inputs).logits
            probabilities = torch.softmax(logits, dim=1)
            toxicity_probs = probabilities[:, 1].cpu().numpy().tolist()
        
        total_elapsed_ms = (time.time() - start) * 1000
        per_item_ms = total_elapsed_ms / len(texts)
        
        results = []
        for prob in toxicity_probs:
            detected = prob >= threshold
            results.append({
                "detected": detected,
                "score": prob,
                "label": "TOXIC" if detected else "SAFE",
                "threshold": threshold,
                "inference_time_ms": round(per_item_ms, 2),
            })
        
        return results
    
    @property
    def models_loaded(self) -> dict[str, bool]:
        """Check which models are loaded."""
        return {
            "injection": self.injection_classifier is not None,
            "toxicity": self.hap_model is not None,
        }
    
    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        if self.start_time is None:
            return 0.0
        return time.time() - self.start_time


# Global model manager instance
model_manager = ModelManager()


# =============================================================================
# FastAPI Application
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load models on startup, cleanup on shutdown."""
    # Startup
    logger.info("Starting Guardrail Detection Server...")
    model_manager.load_models()
    yield
    # Shutdown
    logger.info("Shutting down Guardrail Detection Server...")


app = FastAPI(
    title="Guardrail Detection Server",
    description="API for prompt injection and toxicity detection",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check server health and model status."""
    return HealthResponse(
        status="healthy" if all(model_manager.models_loaded.values()) else "degraded",
        models_loaded=model_manager.models_loaded,
        device=model_manager.device,
        uptime_seconds=round(model_manager.uptime_seconds, 2),
    )


@app.post("/detect/injection", response_model=DetectionResponse)
async def detect_injection(request: DetectionRequest):
    """
    Detect prompt injection attacks in the provided text.
    
    Uses the ProtectAI DeBERTa model for detection.
    """
    if not model_manager.injection_classifier:
        raise HTTPException(status_code=503, detail="Injection model not loaded")
    
    try:
        result = model_manager.detect_injection(request.text, request.threshold)
        return DetectionResponse(**result)
    except Exception as e:
        logger.error(f"Error during injection detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/detect/toxicity", response_model=DetectionResponse)
async def detect_toxicity(request: DetectionRequest):
    """
    Detect toxicity (hate, abuse, profanity) in the provided text.
    
    Uses the IBM Granite Guardian HAP model for detection.
    """
    if not model_manager.hap_model:
        raise HTTPException(status_code=503, detail="HAP model not loaded")
    
    try:
        result = model_manager.detect_toxicity(request.text, request.threshold)
        return DetectionResponse(**result)
    except Exception as e:
        logger.error(f"Error during toxicity detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/detect/toxicity/batch", response_model=BatchDetectionResponse)
async def detect_toxicity_batch(request: BatchDetectionRequest):
    """
    Detect toxicity in a batch of texts for better throughput.
    """
    if not model_manager.hap_model:
        raise HTTPException(status_code=503, detail="HAP model not loaded")
    
    try:
        start = time.time()
        results = model_manager.detect_toxicity_batch(request.texts, request.threshold)
        total_time = (time.time() - start) * 1000
        
        return BatchDetectionResponse(
            results=[DetectionResponse(**r) for r in results],
            total_inference_time_ms=round(total_time, 2),
        )
    except Exception as e:
        logger.error(f"Error during batch toxicity detection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting server on {config.HOST}:{config.PORT}")
    uvicorn.run(
        "guardrail_server:app",
        host=config.HOST,
        port=config.PORT,
        reload=False,
        log_level="info",
    )
