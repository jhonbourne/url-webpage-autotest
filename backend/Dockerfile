# Playwright's Python image ships Chromium + system deps, so page rendering works
# out of the box.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
