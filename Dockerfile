# Base image for Python
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# libsndfile1 is required for soundfile
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
# Note: For RPi specifically, we might want to target https://download.pytorch.org/whl/cpu
# But for now we rely on standard pip which usually finds the right wheels.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create volume for models
VOLUME /models

# Environment variable for model path
ENV MODEL_PATH=/models/Qwen/Qwen3-TTS-12Hz-0.6B-Base

# Expose port
EXPOSE 8000

# Start command
# Start command
CMD ["python", "app.py"]
