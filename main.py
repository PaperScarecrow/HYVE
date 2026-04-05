import os
import sys
import logging
import uvicorn
import time
from typing import Optional, List
from fastapi import FastAPI, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
import requests
import threading

# --- THE DIRECTORY BRIDGE ---
# Update these paths for your local installation
INTERFACE_DIR = "./interface"
ENGINE_DIR = "."

if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)
os.chdir(ENGINE_DIR)

from hyve_nexus import HyveNexus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HyveVivarium")

app = FastAPI()

# THE OBSIDIAN LOCK: Prevents telemetry polls from colliding with active inference
nexus_lock = threading.Lock()

# Config
NYXXIE_BRAIN_URL = "http://127.0.0.1:8001/api/synthesize"
WORKSPACE_DIR = "./nyxxie_workspace"
os.makedirs(WORKSPACE_DIR, exist_ok=True)

logger.info("Igniting HYVE Colonial Organism...")
nexus = HyveNexus()

# --- Data Models ---
class Attachment(BaseModel):
    type: str # 'image/jpeg', 'audio/wav', etc.
    data: str # Base64 encoded string

class ChatMessage(BaseModel):
    message: str
    attachments: Optional[List[Attachment]] = None

# --- Endpoints ---
@app.post("/api/chat")
async def chat_with_nyxxie(data: ChatMessage):
    if not data.message.strip() and not data.attachments:
        return JSONResponse(status_code=400, content={"error": "Empty stimulus."})
        
    try:
        att_dicts = [att.dict() for att in data.attachments] if data.attachments else None
        
        with nexus_lock:
            response_text = nexus.chat(data.message, attachments=att_dicts)
        
        return {
            "choices": [{
                "message": {
                    "content": response_text
                }
            }]
        }

    except Exception as e:
        logger.error(f"HYVE Matrix Error: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/telemetry")
async def get_telemetry():
    """Real-time neural activity monitor for the UI."""
    # Non-blocking: if chat is in progress, return stale data rather than waiting
    if not nexus_lock.acquire(blocking=False):
        return JSONResponse(content={"system_state": "PROCESSING", "emotions": [], "tether": None, "memory": {}})
    
    try:
        active_states = nexus.memory.get_active_inner_states(threshold=0.05)
        conn = nexus.memory.get_inner_connectivity()
        
        state = "DREAMING (REM)" if nexus.dreamer.is_dreaming else "AWAKE"
        tether_state = nexus.tether.get_relational_state() if hasattr(nexus, 'tether') and nexus.tether else None
        
        return {
            "system_state": state,
            "emotions": [{"name": n, "activation": a} for n, a, _ in active_states[:8]],
            "tether": tether_state,
            "memory": {
                "episodic": len(nexus.memory.episodic_memory),
                "novel_dreams": conn['novel_dreams'],
                "diversity": f"{conn['diversity']:.1%}"
            }
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        nexus_lock.release()

# --- Replace the synthesize block at the bottom ---
@app.post("/api/synthesize")
async def synthesize(text: str = Form(...)):
    # voice_node.py only expects 'text' as Form data
    payload = {"text": text}

    def audio_streamer(data_payload):
        with requests.Session() as session:
            try:
                # CRITICAL: Use 'data=' for Form submission, not 'json='
                with session.post(NYXXIE_BRAIN_URL, data=data_payload, stream=True, timeout=30) as r:
                    r.raise_for_status()
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: yield chunk
            except Exception as e:
                logger.error(f"TTS Streaming failed: {e}")

    return StreamingResponse(audio_streamer(payload), media_type="audio/wav")

app.mount("/static", StaticFiles(directory=os.path.join(INTERFACE_DIR, "static")), name="static")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(INTERFACE_DIR, 'static/index.html'))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
