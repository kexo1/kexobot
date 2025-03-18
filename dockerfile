FROM python:3.11.4-slim-buster

RUN apt-get update && apt-get install -y git

WORKDIR /kexobot

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --no-deps wavelink

COPY . .

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
#EXPOSE 2333

CMD ["python", "main.py"]
