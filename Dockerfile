# Use stable and lightweight Python image
FROM python:3.14-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:////data/enyalien.db

# Create directory for persistent database storage
RUN mkdir -p /data

# Set working directory
WORKDIR /app

# Install dependencies explicitly to ensure successful build
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "fastapi>=0.110.0" \
    "uvicorn>=0.28.0" \
    "sqlmodel>=0.0.16" \
    "jinja2>=3.1.3" \
    "python-multipart>=0.0.9" \
    "markdown>=3.6"

# Copy project files
COPY ./app /app/app
COPY ./main.py /app/main.py

# Expose port
EXPOSE 8000

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
