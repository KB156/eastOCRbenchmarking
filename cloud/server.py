"""Deploy on Cloud Run only. Cloud Run IAM authenticates incoming requests."""
import base64
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
lock = threading.Lock()
model = None


class Request(BaseModel):
    image: str
    mime_type: str


@app.get('/health')
def health():
    return {'status': 'ok', 'backend': os.getenv('BACKEND', 'ocr')}


@app.post('/predict')
def predict(request: Request):
    global model
    if request.mime_type not in ('image/jpeg', 'image/png'):
        raise HTTPException(400, 'Only JPEG/PNG supported')
    try:
        data = base64.b64decode(request.image, validate=True)
    except ValueError:
        raise HTTPException(400, 'Invalid base64')
    if len(data) > 20_000_000:
        raise HTTPException(413, 'Image exceeds 20 MB')
    backend = os.getenv('BACKEND', 'ocr')
    with lock, tempfile.TemporaryDirectory() as directory:
        started = time.perf_counter()
        if model is None:
            if backend == 'vl':
                from paddleocr import PaddleOCRVL
                model = PaddleOCRVL()
            else:
                from paddleocr import PaddleOCR
                model = PaddleOCR(lang='japan', use_doc_orientation_classify=True, use_doc_unwarping=False)
        path = Path(directory) / ('input.png' if request.mime_type == 'image/png' else 'input.jpg')
        path.write_bytes(data)
        texts, scores = [], []
        for result in model.predict(str(path)):
            raw = result.json
            if isinstance(raw, str):
                raw = json.loads(raw)
            raw = raw.get('res', raw)
            if backend == 'vl':
                texts.extend(block.get('block_content', '') for block in raw.get('parsing_res_list', []))
            else:
                texts.extend(raw.get('rec_texts', []))
                scores.extend(float(s) for s in raw.get('rec_scores', []))
        return {'text': '\n'.join(texts), 'recognition_scores': scores,
                'model': type(model).__name__, 'usage': {'images': 1, 'inference_seconds': time.perf_counter() - started}}
