FROM python:3.12-slim

# System deps for moviepy/ffmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fonts-liberation \
    wget curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-create directories needed at runtime
RUN mkdir -p products/audio products/browser_demos products/videos

# Use Liberation Sans as the font (Linux equivalent of Arial Bold)
ENV FONT_PATH=/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf

EXPOSE 8000

CMD ["/bin/sh", "-c", "uvicorn api_server:app --host 0.0.0.0 --port ${PORT:-8000}"]
