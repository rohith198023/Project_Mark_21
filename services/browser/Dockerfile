FROM python:3.11-slim AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY services/browser/requirements.txt ./services/browser/
RUN pip install --no-cache-dir -r services/browser/requirements.txt

# Install Playwright Chromium binary and its system dependencies
# Must run after pip install playwright so the CLI is available
RUN playwright install chromium --with-deps

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
# Copy Playwright browser binaries from builder stage
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="/app"
# Directory where screenshots will be persisted
ENV SCREENSHOTS_DIR="/app/screenshots"

# Install Chromium runtime system libs (needed in the slim final image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libexpat1 \
    libgbm1 \
    libnspr4 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxkbcommon0 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /app/screenshots

# Copy shared code and service code
COPY shared/ ./shared/
COPY services/browser/ ./services/browser/

EXPOSE 8003
WORKDIR /app/services/browser
CMD ["python", "main.py"]
