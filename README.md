<div align="center">
   <img src="https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/38b4bf5b-bfa8-4904-b8e8-4c492c4eb872"/>
</div>

<div align="center">

[![license](https://img.shields.io/github/license/exmanka/ksiVPN-telegram-bot?style=flat-square&color=green)](https://github.com/exmanka/ksiVPN-telegram-bot/blob/main/LICENSE)
[![python-version](https://img.shields.io/badge/python-3.10-royalblue?style=flat-square)](https://github.com/exmanka/ksiVPN-telegram-bot/releases)
[![aiogram-version](https://img.shields.io/badge/aiogram-2.25.1-royalblue?style=flat-square)](https://github.com/exmanka/ksiVPN-telegram-bot/releases)
[![asyncpg-version](https://img.shields.io/badge/asyncpg-0.29.0-blue?style=flat-square)](https://github.com/MagicStack/asyncpg)
[![apscheduler-version](https://img.shields.io/badge/apscheduler-3.10.4-blue?style=flat-square)](https://github.com/agronholm/apscheduler)
[![gpt4free-version](https://img.shields.io/badge/gpt4free-0.1.9.3-blue?style=flat-square)](https://github.com/hiddify/hiddify-next/)
[![aiomoney-version](https://img.shields.io/badge/aiomoney-forked-blue?style=flat-square)](https://github.com/fofmow/aiomoney)
[![docker-compose-version](https://img.shields.io/badge/Docker_Compose-2.21.0-blue?style=flat-square)](https://docs.docker.com/compose/release-notes/)
[![telegram-channel](https://img.shields.io/endpoint?label=Channel&style=flat-square&url=https%3A%2F%2Ftg.sumanjay.workers.dev%2F%2Bxkh2-7JJQ183YzJi&color=%2326A5E4)](https://t.me/+VocvIz4dZaAyNjE6)
[![telegram-bot](https://img.shields.io/badge/Enjoy-ksiVPN_bot-limegreen?style=flat-square&logo=telegram)](https://t.me/ksiVPN_bot)

</div>

# ksiVPN Telegram Bot
<div align="center">

![showcase-en](https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/dada862c-4ac0-497a-a12c-9da410d064d6)
![showcase-ru](https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/8db6ac46-61af-41fa-99bf-5bc32b0bc1e8)

</div>

Multifunctional telegram bot for ksiVPN project based on aiogram framework and using modules: asyncpg2, apscheduler, aiomoney, gpt4free. Deployment is possible using Docker with docker-compose.

## Features
- __aiogram2 support__
- __PostgreSQL usage__
- __P2P payments via YooMoney__
- __ChatGPT integration__
- __subscription mechanics: renewal, expiration notifications__
- __promocodes mechanics__
- __referral system mechanics__
- __personal account mechanics__
- __localizations support__
- panels for unauthorized users, authorized users and admin
- rapid deployment via Docker
- database backups via bot
- asynchronous code
- logging

## Use Case diagram
Use Case diagram can be found [here](https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/36163ea2-810c-4a70-b97a-cb54df6b8a60).

## PostgreSQL database diagram
[![db-diagram](https://github.com/exmanka/ksiVPN-telegram-bot/assets/74555362/4eaae2bc-8742-41ba-9c3a-b6afed4479bd)](https://drawsql.app/teams/trycatch-1/diagrams/tgbot-postgres)

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

## About ksiVPN project
🔥 __ksiVPN__ — an open source student project that has become something more not only for its creator, but also for most customers .Thanks to hard work, the use of basic modern protocols and competent server rental, the project is able to provide the highest quality VPN connection for the minimum cost.  
### ksiVPN uses the following open-source solutions:
- [pivpn](https://github.com/pivpn/pivpn)
- [3x-ui](https://github.com/MHSanaei/3x-ui)
- [nekoray](https://github.com/MatsuriDayo/nekoray)
- [v2rayNG](https://github.com/2dust/v2rayNG)

`PROMO_GITHUB_2049`
