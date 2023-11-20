# Meowgram

Telegram client for the [CheshireCat Ai](https://cheshirecat.ai/).

## Prerequisites

- `python >=3.10`
- Access to an instance of the [Cheshire Cat](https://github.com/cheshire-cat-ai/core#quickstart)
- The `TOKEN` of a Telegram bot, you can create one using [Bot Father](https://core.telegram.org/bots/features#creating-a-new-bot)

## Install

Clone the repo:

```bash
git clone https://github.com/Pingdred/Meowgram.git
```

Enter in the created folder:

```bash
cd Meowgram
```

Install the requirements:

```bash
pip install -r requirements.txt
```

Create an `.env` file setting the following parameters:

```toml
BOT_TOKEN="YOUR-BOT-TOKEN"

CHESHIRE_CAT_URL="localhost"
CHESHIRE_CAT_PORT=1865
```

In the repot there is a file `.env.example` you can use.

After that make sure you chashire Cat instance is up and reachable, you can follow this [quick start](https://github.com/cheshire-cat-ai/core#quickstart) to do that.

Run the telegram bot and start chatting:

```bash
python main.py
```
