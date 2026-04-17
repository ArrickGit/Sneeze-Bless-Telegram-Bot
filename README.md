# Bless You Sneeze Bot

A fun Telegram bot for group chats that tracks who said "bless you" first.

## What it does

- `/bless @first @second [points]` awards points to the first two valid blessers.
- `/bless self [points]` resolves `self` to your own Telegram username.
- `/blessme` gives you 2 points for blessing yourself after sneezing.
- `/faaaah` sends the bundled `Faaah.m4a` audio clip.
- `/bless` starts a short guided reply flow if you do not want to type the bless entry in one command.
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
3. Find your Telegram numeric user ID if you want to enable the owner-only hard reset command.
4. Copy `.env.example` to `.env` and fill in the values.
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

By default, polling mode drops old queued updates on startup so a local debug session does not replay stale `/bless` spam. Webhook mode keeps pending updates so a sleeping host like Render can still receive commands that arrived while it was waking up.

## Commands

- `/help` shows usage.
- `/bless @alice @bob`
- `/bless @alice`
- `/bless @alice 100000`
- `/bless @alice @bob 100000`
- `/bless self`
- `/bless self 100000`
- `/blessme`
- `/faaaah`
- `/bless` and then reply with `@alice @bob` or `@alice`
- `/unbless @alice`
- `/unbless @alice -2 early blessing during a sneeze streak`
- `/unbless @alice 2 early blessing during a sneeze streak`
- `/scoreboard`
- `/rules`
- `/addrule Wait for the full sneeze combo before blessing.`
- `/removerule 3`
- `/cancel` exits a guided input flow.

There is also a hidden owner-only reset command for emergencies:
- private chat only
- requires `OWNER_USER_ID` in `.env`
- use `/hardreset confirm` to wipe all MongoDB scores, events, and custom rules across every chat while keeping known users intact

## Notes about usernames

The bot tracks blessers by Telegram handle because `/bless` is based on `@handles`. If someone changes their Telegram username later, they may look like a new person in the scoreboard. That is a good enough tradeoff for a first version and keeps the bot simple.

`/bless self` is just a shortcut that resolves to your current Telegram username, so it still requires you to have a username set.

The bot now also validates bless and unbless handles against Telegram users it has seen before. If it cannot verify a handle, it will reject the command instead of creating a fake scoreboard entry. In practice, that means someone may need to message the bot once before they can be scored by handle.

## Render deployment

1. Push this project to GitHub.
2. Create a new Render Web Service from the repo.
3. Render will detect `render.yaml`.
4. Set these environment variables in Render:
   - `BOT_TOKEN`
   - `MONGODB_URI`
5. Keep `BOT_MODE=webhook`.
6. Deploy.

On Render, the bot can use Render's own `RENDER_EXTERNAL_URL` automatically, so you usually do not need to set `WEBHOOK_BASE_URL` manually unless you want to use a custom domain.

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
