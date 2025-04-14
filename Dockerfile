FROM python:3.12.9-alpine

RUN apk add --no-cache \
    git \
    build-base \
    python3-dev \
    musl-dev \
    linux-headers
    
WORKDIR /kexobot

COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --no-deps git+https://github.com/PythonistaGuild/Wavelink.git

COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/kexobot

CMD ["python", "app/main.py"]