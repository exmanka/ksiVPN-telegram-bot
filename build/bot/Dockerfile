FROM python:3.10-slim

WORKDIR /usr/src/tgbot

COPY ./build/bot/requirements.txt ./
RUN pip install --upgrade pip; pip install --no-cache-dir -r requirements.txt

COPY . .

CMD [ "python", "./main.py"]
