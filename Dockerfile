# Game Assistant S2S AI Agent Dockerfile
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    portaudio19-dev \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY data/ ./data/

# Create directories for logs and outputs
RUN mkdir -p /app/logs /app/outputs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port for potential web interface (future enhancement)
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["python", "src/main.py"]

# Default command (text mode)
CMD ["--mode", "text"]
