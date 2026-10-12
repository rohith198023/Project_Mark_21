FROM python:3.11-slim as builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/voice/requirements.txt ./services/voice/
RUN pip install --no-cache-dir -r services/voice/requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# Copy shared code and service code
COPY shared/ ./shared/
COPY services/voice/ ./services/voice/

EXPOSE 8004
WORKDIR /app/services/voice
CMD ["python", "main.py"]
