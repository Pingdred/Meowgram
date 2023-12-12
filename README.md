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
## Set-up speech to text
First thing to do is install the plugin Whispering cat from the page Plugin in the Cheshire Cat Admin:

![Screenshot from 2023-12-12 12-08-02](https://github.com/Pingdred/Meowgram/assets/67059270/dc6b0c9f-209b-425f-b039-619fa68f0dce)

![Screenshot from 2023-12-12 12-07-16](https://github.com/Pingdred/Meowgram/assets/67059270/ff652354-0e9e-4505-b307-6af90d56d0cf)

Then click on the settings wheel set your Api Key, the language and in the field `Audio Key` write `meowgram voice`.
