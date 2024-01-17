# ksiVPN Telegram Bot
Multifunctional telegram bot for ksiVPN project based on aiogram framework and using modules: asyncpg2, apscheduler, aiomoney, gpt4free. Deployment is possible using Docker with docker-compose.

## Features
- __aiogram2 support__
- __PostgreSQL usage__
- __P2P payments via YooMoney__
- __ChatGPT integration__
- __subscription mechanics: renewal, expiration notifications__
- __promocodes mechanics__
- __referral sysetm mechanics__
- __personal account mechanics__
- __localizations support__
- panels for unauthorized users, authorized users and admin
- rapid deployment via Docker
- database backups via bot
- asynchronous code
- logging

## Use Case diagram
Here will be the Use Case diagram.

## PostgreSQL database diagram
![drawSQL-tgbot-postgres-export-2024-01-17](https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/a3d96dab-207b-4553-b7d1-b969822ceab7)


## Installation
1. Install Docker with Docker Compose according to the [official instructions](https://docs.docker.com/engine/install/).
2. Install git according to the [official instructions](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git).
3. Register new telegram bot using [BotFather](https://t.me/BotFather) and get bot's token.
4. `git clone https://github.com/exmanka/ksiVPN-telegram-bot.git` — download the repository to your computer.
5. `cd ksiVPN-telegram-bot` — move to project directory.
6. Change text file `.env` according to your needs.  
   __Important:__ all environment variables marked with `# !` sign MUST be entered!
7. `docker compose up` — build images and run containers.

## Usage
Now you can write to your bot and enjoy all its pre-installed features. You are free to play with functionality and database filling. Learn something new for yourself! 🎉  
### You should mention me in your releases if you use my project for your own purposes.
