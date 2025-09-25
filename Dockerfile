FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y \
    curl wget gnupg ca-certificates \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Start both bot & proxy
CMD ["sh", "-c", "python proxy.py & python bot.py"]
