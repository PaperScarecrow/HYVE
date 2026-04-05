# voice/voice_node.py
"""
HYVE Voice Node: Pure TTS Server
==================================
Qwen3-TTS with Sucrose voice cloning.
STT is handled natively by Gemma 4 E4B via the brain server.

No Whisper. No STT model. No CUDA collisions.
"""

import os
import io
import wave
import asyncio
import uvicorn
import torch
import numpy as np
from fastapi import FastAPI, Form
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from qwen_tts import Qwen3TTSModel

app = FastAPI(title="HYVE Voice Node")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QWEN_MODEL_PATH = os.path.join(ROOT_DIR, "models", "nyxxie_sucrose_final", "checkpoint-final")
VOICE_SAMPLE = os.path.join(ROOT_DIR, "references", "nyxxie_sample.wav")

# Reference transcript for voice cloning (Sucrose)
VOICE_REFERENCE_TRANSCRIPT = (
    "Oh, you, uh, noticed. My ears are a hereditary feature, "
    "quite different from everyone else's. So I try to hide them "
    "with my hair as much as possible."
)

# GPU lock prevents overlapping TTS generations from colliding
gpu_lock = asyncio.Lock()

print(f"[*] Booting HYVE Voice Node (TTS Only) on {DEVICE}...")

tts_model = None
try:
    tts_model = Qwen3TTSModel.from_pretrained(
        QWEN_MODEL_PATH,
        device_map=DEVICE,
        dtype=torch.bfloat16
    )
    print("[+] Qwen3 TTS Online. Voice: Sucrose")
except Exception as e:
    print(f"[!] Qwen3 TTS failed to load: {e}")


@app.post("/api/synthesize")
async def synthesize(text: str = Form(...)):
    if tts_model is None:
        return JSONResponse(status_code=500, content={"error": "TTS Engine Offline"})

    print(f"[Voice] Synthesizing: {text[:50]}...")

    try:
        async with gpu_lock:
            wavs, sample_rate = tts_model.generate_voice_clone(
                text=text,
                language="English",
                ref_audio=VOICE_SAMPLE,
                ref_text=VOICE_REFERENCE_TRANSCRIPT,
                x_vector_only_mode=True,
                do_sample=True,
                temperature=0.90,
                top_p=0.85,
                bottom_p=0,
                top_k=20,
                repetition_penalty=0.9
            )
            torch.cuda.empty_cache()

        audio_array = wavs[0]

        # Fade in to prevent click artifacts
        fade_in_len = int(sample_rate * 0.05)
        if len(audio_array) > fade_in_len:
            fade_window = np.linspace(0, 1, fade_in_len)
            audio_array[:fade_in_len] *= fade_window

        if isinstance(audio_array, torch.Tensor):
            audio_array = audio_array.detach().cpu().numpy()

        if audio_array.ndim > 1:
            audio_array = audio_array.flatten()

        # Pad start to prevent clipping on playback
        padding = np.zeros(int(sample_rate * 0.2), dtype=audio_array.dtype)
        audio_array = np.concatenate((padding, audio_array))

        def audio_streamer():
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes((audio_array * 32767).astype('int16').tobytes())
            buffer.seek(0)
            yield buffer.read()

        return StreamingResponse(audio_streamer(), media_type="audio/wav")

    except Exception as e:
        print(f"[Voice Error]: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/health")
async def health():
    return {
        "tts": "online" if tts_model else "offline",
        "device": DEVICE,
        "voice": "Sucrose",
    }


if __name__ == "__main__":
    print(f"[+] Voice Node listening on http://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="warning")
