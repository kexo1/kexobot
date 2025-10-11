# ---- Builder Stage ----
# This stage installs dependencies, including from git
FROM python:3.12.11-alpine AS builder

# Install build-time dependencies
RUN apk add --no-cache \
    git \
    build-base \
    python3-dev \
    musl-dev \
    linux-headers \
    libffi-dev

WORKDIR /kexobot

# Create a virtual environment to keep dependencies isolated
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps git+https://github.com/PythonistaGuild/Wavelink.git

# ---- Final Stage ----
# This is the small, final image that will run the application
FROM python:3.12.11-alpine

# Create a non-root user for security
RUN addgroup -g 1001 -S botuser && \
    adduser -S -D -H -u 1001 -s /sbin/nologin -G botuser botuser

WORKDIR /kexobot

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application code
COPY . .

# Set ownership and switch to non-root user
RUN chown -R botuser:botuser /kexobot
USER botuser

# Create a writable directory for Matplotlib config
RUN mkdir -p /tmp/matplotlib && chown -R botuser:botuser /tmp/matplotlib

# Set environment variables for runtime
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/kexobot \
    PYTHONOPTIMIZE=1

# Command to run the application
CMD ["python", "app/main.py"]
