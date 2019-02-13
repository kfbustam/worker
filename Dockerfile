FROM python:3.6-alpine

RUN apk add --no-cache --virtual .build-deps gcc musl-dev git
RUN mkdir -p /app
VOLUME ["/app"]
WORKDIR /app
COPY ./requirements.txt   ./app/requirements.txt
RUN pip install -r ./app/requirements.txt
COPY . /app

ENTRYPOINT sh worker.sh
