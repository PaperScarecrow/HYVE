import torch
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import time
import base64
import io
from PIL import Image
from transformers import AutoModelForMultimodalLM, AutoProcessor
import requests # Make sure this is imported at the top

# --- CONFIGURATION ---
MODEL_PATH = "./models/gemma-4-E4B"  # Update to your local model path
PORT = 1234
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[*] Waking the Native HYVE Brain Server on {DEVICE}...")

processor = AutoProcessor.from_pretrained(MODEL_PATH)
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

app = FastAPI(title="HYVE Brain API")

@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    payload = await request.json()
    messages = payload.get("messages", [])
    max_tokens = payload.get("max_tokens", 1024)
    temperature = payload.get("temperature", 0.75)
    
    # 1. INTERCEPT AND DECODE MULTIMEDIA
    pil_images = []
    
    for msg in messages:
        if isinstance(msg.get("content"), list):
            valid_content = []
            for item in msg["content"]:
                if item.get("type") == "image":
                    url_data = item.get("url", "")
                    img = None
                    
                    try:
                        if url_data.startswith("data:image"):
                            b64_str = url_data.split("base64,")[1]
                            image_bytes = base64.b64decode(b64_str)
                            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                            
                        elif url_data.startswith("http"):
                            # Actively fetch the internet link
                            print(f"[*] Fetching external visual data: {url_data[:50]}...")
                            headers = {'User-Agent': 'HyveNexus/1.0'}
                            res = requests.get(url_data, headers=headers, timeout=5)
                            res.raise_for_status()
                            img = Image.open(io.BytesIO(res.content)).convert("RGB")
                            
                    except Exception as e:
                        print(f"[-] Vision Intake Error: {e}")
                        img = None
                    
                    # CRITICAL: Only keep the item if we successfully built the tensor
                    if img is not None:
                        pil_images.append(img)
                        valid_content.append(item) 
                    else:
                        print("[-] Dropping invalid visual stimulus to prevent ATen segfault.")
                else:
                    # Keep text and other modalities
                    valid_content.append(item)
            
            # Overwrite the message content with only the safe, validated items
            msg["content"] = valid_content

    # 2. FORMAT THE TEXT (Injects the <|image|> tokens safely)
    text = processor.apply_chat_template(
        messages, 
        tokenize=False, 
        add_generation_prompt=True,
        enable_thinking=False 
    )
    
    # 3. BIND THE SENSES
    # We pass the text prompt AND the physical image pixels to the processor simultaneously
    processor_kwargs = {
        "text": text,
        "return_tensors": "pt"
    }
    if pil_images:
        processor_kwargs["images"] = pil_images
        
    inputs = processor(**processor_kwargs).to(model.device)
    input_len = inputs["input_ids"].shape[-1]
    
    # 4. GENERATE
    with torch.no_grad():
        outputs = model.generate(
            **inputs, 
            max_new_tokens=max_tokens,
            temperature=temperature,
            do_sample=True if temperature > 0 else False,
            top_p=0.95
        )
        
    # Decode only the newly generated tokens
    response_text = processor.decode(outputs[0][input_len:], skip_special_tokens=True)
    
    # Package into OpenAI compatible response
    response_json = {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "hyve-gemma4-e4b-native",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text.strip()
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": input_len,
            "completion_tokens": len(outputs[0]) - input_len,
            "total_tokens": len(outputs[0])
        }
    }
    
    return JSONResponse(content=response_json)

if __name__ == "__main__":
    print(f"[+] Brain Server Online. Listening on http://127.0.0.1:{PORT}/v1/chat/completions")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
