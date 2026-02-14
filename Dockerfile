# ---- Build stage ----
FROM python:3.12-slim AS builder

WORKDIR /app
COPY pyproject.toml README.md ./
COPY codewiki_mcp/ codewiki_mcp/
COPY server.py ./

RUN pip install --no-cache-dir .

# ---- Runtime stage ----
FROM python:3.12-slim

# Install Chrome + dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Tell Selenium to use the system chromium
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/codewiki-mcp /usr/local/bin/codewiki-mcp
COPY --from=builder /app /app

# Environment variable defaults
ENV CODEWIKI_HARD_TIMEOUT=60
ENV CODEWIKI_MAX_RETRIES=2
ENV CODEWIKI_RESPONSE_MAX_CHARS=8000
ENV CODEWIKI_VERBOSE=false

# Default: stdio transport
ENTRYPOINT ["codewiki-mcp"]
CMD ["--stdio"]

# For SSE transport, run:
#   docker run -p 3000:3000 codewiki-mcp --sse --port 3000
