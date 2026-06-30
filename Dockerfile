FROM python:3.12-slim

# System deps for moviepy/ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    wget curl ca-certificates \
    # Playwright Chromium dependencies
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libxshmfence1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

COPY . .

# Pre-create directories needed at runtime
RUN mkdir -p products/audio products/browser_demos products/videos

# Use Liberation Sans as the font (Linux equivalent of Arial Bold)
ENV FONT_PATH=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf

EXPOSE 8000

CMD ["/bin/sh", "-c", "uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
