VERSION 0.6

frontend:
  FROM node:16-bullseye
  WORKDIR /app
  COPY ./frontend/public/ ./public
  COPY ./frontend/src/ ./src
  COPY ./frontend/package.json .
  COPY ./frontend/package-lock.json .
  COPY ./frontend/.eslintrc.json .
  COPY ./frontend/.prettierrc .

  RUN npm install && npm run build
  SAVE ARTIFACT ./build

base-image:
  FROM python:3.11
  LABEL maintainer="cicd-owners@kentik.com"
  RUN mkdir -p /incident-bot/app
  # Copy only the relevant Python files into the container.
  COPY +frontend/build/* /incident-bot/app
  COPY ./backend/bot /incident-bot/bot
  COPY ./backend/requirements.txt /incident-bot
  COPY ./backend/config.py /incident-bot
  COPY ./backend/variables.py /incident-bot
  COPY ./backend/main.py /incident-bot
  COPY ./scripts/wait-for-it.sh /incident-bot/wait-for-it.sh

  # Set the work directory to the app folder.
  WORKDIR /incident-bot

  # Install Python dependencies.
  RUN pip3 install --no-cache-dir -r requirements.txt

  EXPOSE 3000
  CMD ["python3", "main.py"]

image:
  FROM +base-image
  SAVE IMAGE --push gcr.io/kentik-continuous-delivery/ops/incident-bot-fork:master

all:
  BUILD +image
