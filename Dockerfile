FROM python:3.12-slim

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-liberation \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/*

# Install codewiki-mcp from PyPI + Playwright Chromium
RUN pip install --no-cache-dir codewiki-mcp \
    && playwright install --with-deps chromium

# Environment variable defaults
ENV CODEWIKI_HARD_TIMEOUT=60
ENV CODEWIKI_MAX_RETRIES=2
ENV CODEWIKI_RESPONSE_MAX_CHARS=30000
ENV CODEWIKI_VERBOSE=false

# Default: stdio transport
ENTRYPOINT ["codewiki-mcp"]
CMD ["--stdio"]

# For SSE transport, run:
#   docker run -p 3000:3000 codewiki-mcp --sse --port 3000
