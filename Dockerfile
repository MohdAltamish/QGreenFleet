FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies for WeasyPrint and rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .

# Ensure /app is in PYTHONPATH
ENV PYTHONPATH="/app:${PYTHONPATH}"

# Expose port
EXPOSE 7860

# Run app with dynamic port fallback
CMD ["sh", "-c", "streamlit run ui/app.py --server.port=${PORT:-7860} --server.address=0.0.0.0 --server.headless=true"]
