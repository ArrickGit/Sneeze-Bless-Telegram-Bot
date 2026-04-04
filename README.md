# Bless You Sneeze Bot

A fun Telegram bot for group chats that tracks who said "bless you" first.

## What it does

- `/bless @first @second` awards 1 point to the first two valid blessers.
- `/bless` starts a short guided reply flow if you do not want to type both handles in one command.
- `/unbless @user [points] [reason]` removes points for rule breaks.
- `/scoreboard` shows the current rankings for the chat.
- `/rules` shows the chat rules.
- `/addrule ...` and `/removerule <number>` let chat admins evolve the rules over time.

Scores are stored in MongoDB so the bot can restart safely without losing data.

## Current rules

1. Wait until the final sneeze in a consecutive sneeze streak before blessing. Early blesses can be punished with `/unbless`.
2. Only the first two blessers score. If there is only one valid blesser, only that person gets the point.

## Tech stack

- Python
- `python-telegram-bot`
- MongoDB Atlas
- FastAPI + Uvicorn for webhook hosting

## Local setup

1. Create a bot with BotFather and copy the token.
2. Create a MongoDB Atlas cluster and grab the connection string.
3. Copy `.env.example` to `.env` and fill in the values.
4. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

5. Start the bot in polling mode:

```bash
python main.py
```

## Commands

- `/help` shows usage.
- `/bless @alice @bob`
- `/bless @alice`
- `/bless` and then reply with `@alice @bob` or `@alice`
- `/unbless @alice`
- `/unbless @alice 2 early blessing during a sneeze streak`
- `/scoreboard`
- `/rules`
- `/addrule Wait for the full sneeze combo before blessing.`
- `/removerule 3`
- `/cancel` exits a guided input flow.

## Notes about usernames

The bot tracks blessers by Telegram handle because `/bless` is based on `@handles`. If someone changes their Telegram username later, they may look like a new person in the scoreboard. That is a good enough tradeoff for a first version and keeps the bot simple.

## Render deployment

1. Push this project to GitHub.
2. Create a new Render Web Service from the repo.
3. Render will detect `render.yaml`.
4. Set these environment variables in Render:
   - `BOT_TOKEN`
   - `MONGODB_URI`
   - `WEBHOOK_BASE_URL`
5. Keep `BOT_MODE=webhook`.
6. Deploy.

The bot exposes:

- `GET /healthz`
- `POST /telegram/webhook`

Render free services can sleep after inactivity, so the first command after a quiet period may be a little slow. Telegram will retry webhook deliveries.

## MongoDB Atlas

Atlas free clusters are enough for this bot. The app writes:

- `scores`: current point totals per chat and handle
- `events`: bless and unbless history
- `rules`: rules per chat

## Future ideas

- `/history` to show recent blesses and punishments
- `/undo` for the last scoring event
- admin-only penalties
- a streak or monthly leaderboard
- smarter sneeze-session tracking
