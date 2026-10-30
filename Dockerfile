FROM python:3.12-slim

WORKDIR /app

# Ensure non-buffered stdout for real-time logs
ENV PYTHONUNBUFFERED=1
ENV PORT=5000
ENV PYTHONPATH=/app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY backend /app/backend
COPY frontend /app/frontend

# Expose default web server port
EXPOSE 5000

# Run Ejari Students Egypt v3.1 production WSGI server via Gunicorn with dynamic PORT support
CMD ["sh", "-c", "gunicorn --chdir backend app:app --bind 0.0.0.0:${PORT:-5000} --workers 3"]
