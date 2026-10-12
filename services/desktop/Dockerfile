FROM python:3.11-slim as builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/desktop/requirements.txt ./services/desktop/
RUN pip install --no-cache-dir -r services/desktop/requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"

# Copy shared code and service code
COPY shared/ ./shared/
COPY services/desktop/ ./services/desktop/

EXPOSE 8005
WORKDIR /app/services/desktop
CMD ["python", "main.py"]
