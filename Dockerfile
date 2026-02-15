FROM python:3.12-slim

# Playwright / Chromium system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-liberation \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libcups2 \
    libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium
RUN playwright install chromium

# Copy PhoneInfoga binary
COPY bin/ bin/
RUN chmod +x bin/phoneinfoga 2>/dev/null || true

# Copy application code
COPY src/ src/
COPY templates/ templates/
COPY brokers/ brokers/

# Default config/data/profiles will be mounted as volumes
RUN mkdir -p config/profiles data/logs data/scans data/screenshots

EXPOSE 8080

CMD ["python", "-m", "src"]
