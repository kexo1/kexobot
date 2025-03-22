FROM python:3.12.9-alpine

RUN apk add --no-cache git

WORKDIR /kexobot
RUN mkdir -p /kexobot/video

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-deps git+https://github.com/PythonistaGuild/Wavelink.git


COPY . .

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
