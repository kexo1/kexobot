FROM python:3.12.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-utils \
    fonts-dejavu \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /kexobot
RUN mkdir -p /kexobot/video

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-deps git+https://github.com/PythonistaGuild/Wavelink.git

# Copy the remaining source code
COPY . .

# Prevent Python from writing pyc files and force unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "app/main.py"]