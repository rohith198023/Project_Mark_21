import os
import logging
from fastapi import FastAPI, HTTPException, UploadFile, File
import uvicorn

from shared.contracts.schemas import VoiceSynthesisRequest, VoiceSynthesisResponse, HealthResponse, ReadinessResponse

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("voice-service")

app = FastAPI(
    title="JARVIS Voice Service",
    description="Speech recognition (STT) and voice synthesis (TTS) agent.",
    version="1.0.0"
)

@app.get("/healthz", response_model=HealthResponse)
def healthz():
    """Liveness probe. Checks if audio hardware drivers/models are loaded."""
    return HealthResponse(status="healthy", service="voice-service", version="1.0.0")

@app.get("/readyz", response_model=ReadinessResponse)
def readyz():
    """Readiness probe checking voice model file availability."""
    checks = {
        "tts_model": "loaded (mocked)",
        "stt_model": "loaded (mocked)"
    }
    # TODO: Validate sound card access and cache availability of ONNX model paths
    return ReadinessResponse(status="ready", service="voice-service", checks=checks)

@app.post("/api/v1/tts", response_model=VoiceSynthesisResponse)
async def text_to_speech(request: VoiceSynthesisRequest):
    """Synthesizes input text into a speakable audio file (mock implementation)."""
    logger.info(f"Synthesizing speech: '{request.text[:40]}...' using voice {request.voice_id or 'default'}")
    
    # TODO:
    # 1. Load Kokoro-ONNX TTS model.
    # 2. Run inference to generate raw PCM data.
    # 3. Write PCM data to a WAV file on disk.
    
    return VoiceSynthesisResponse(
        audio_url="/shared/audio/outputs/speech_latest.wav",
        duration=len(request.text) * 0.08  # Simple mock duration estimation
    )

@app.post("/api/v1/stt")
async def speech_to_text(file: UploadFile = File(...)):
    """Transcribes an uploaded audio file into text (mock implementation)."""
    logger.info(f"Transcribing audio file: {file.filename} (content_type={file.content_type})...")
    
    # TODO:
    # 1. Save uploaded file to temp path.
    # 2. Load Whisper speech-to-text model.
    # 3. Transcribe audio and extract text.
    
    return {
        "success": True,
        "filename": file.filename,
        "text": "Hello, this is a mock transcription of your speech query.",
        "confidence": 0.98
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8004))
    logger.info(f"Starting Voice Service on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
