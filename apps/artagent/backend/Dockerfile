# Note: build this image from the root of the project directory

# Use an official Python runtime as a parent image
FROM python:3.11-slim-bookworm

# Update packages to mitigate vulnerabilities
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user and group
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory in the container
WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential portaudio19-dev && \
    rm -rf /var/lib/apt/lists/*

# Set up virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip

# Copy the source code and project files
COPY pyproject.toml .
COPY ./apps /app/apps
COPY ./src /app/src
COPY ./utils /app/utils

# Install the package (reads dependencies from pyproject.toml)
RUN pip install --no-cache-dir .

# Set PYTHONPATH to include the app directory
ENV PYTHONPATH="/app:$PYTHONPATH"

# Change ownership of the /app directory to the non-root user
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application
# The main.py file should be at /app/apps/artagent/backend/main.py
CMD ["uvicorn", "apps.artagent.backend.main:app", "--host", "0.0.0.0", "--port", "8000"]