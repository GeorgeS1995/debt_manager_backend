FROM python:3.8.3-slim-buster
RUN mkdir /code
WORKDIR /code
RUN apt-get update -y && \
    apt-get install libpq-dev build-essential mime-support -y && \
    apt-get autoremove -y &&\
    apt-get autoclean -y && \
    rm -rf /var/lib/apt/lists/*
COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt
COPY . /code/
EXPOSE 8000