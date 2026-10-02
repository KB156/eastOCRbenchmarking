# GPU image is used only in Cloud Run, never by the local benchmark runner.
FROM paddlepaddle/paddle:3.2.0-gpu-cuda12.6-cudnn9.5-trt10.5
WORKDIR /service
RUN python -m pip install --no-cache-dir "paddleocr[doc-parser]==3.3.2" "fastapi>=0.115,<1" "uvicorn>=0.30,<1"
COPY server.py /service/server.py
ENV BACKEND=ocr PORT=8080
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
