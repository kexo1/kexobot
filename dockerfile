FROM python:3.12.9-alpine

# Install necessary packages
RUN apk add --no-cache \
    git \
    ttf-dejavu \
    fontconfig \
    build-base \
    python3-dev \
    musl-dev \
    linux-headers

WORKDIR /kexobot
RUN mkdir -p /kexobot/video

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps git+https://github.com/PythonistaGuild/Wavelink.git

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "app/main.py"]