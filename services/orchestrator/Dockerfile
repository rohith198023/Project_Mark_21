FROM python:3.11-slim as builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/orchestrator/requirements.txt ./services/orchestrator/
RUN pip install --no-cache-dir -r services/orchestrator/requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# Copy shared code and service code
COPY shared/ ./shared/
COPY services/orchestrator/ ./services/orchestrator/

EXPOSE 8001
WORKDIR /app/services/orchestrator
CMD ["python", "main.py"]
