## Meowgram

<p align="center">
  <img src="https://raw.githubusercontent.com/Pingdred/Meowgram/main/logo.png"/>
</p>

Welcome to Meowgram, a Telegram client designed to seamlessly integrate with [Cheshire Cat Ai](https://cheshirecat.ai/).

## Prerequisites

- `python >=3.10`
- Access to an instance of the [Cheshire Cat](https://github.com/cheshire-cat-ai/core#quickstart)
- A Telegram bot `TOKEN`, which you can obtain by creating one through [Bot Father](https://core.telegram.org/bots/features#creating-a-new-bot)

## Installation

To get started, follow these simple steps:

Clone the repository:

  ```bash
  git clone https://github.com/Pingdred/Meowgram.git
  ```

Navigate to the project directory:

  ```bash
  cd Meowgram
  ```

Install the necessary dependencies:

```bash
pip install -r requirements.txt
```

Create an `.env` file and set the following parameters:

```toml
BOT_TOKEN="YOUR-BOT-TOKEN"

CHESHIRE_CAT_URL="localhost"
CHESHIRE_CAT_PORT=1865
```

You can use the provided `.env.example` file as a template.

> [!IMPORTANT]
> Ensure your Cheshire Cat instance is up and running by following the [quick start guide](https://github.com/cheshire-cat-ai/core#quickstart).

Run the Meowgram Telegram bot:

```bash
python main.py
```

## Meowgram Connect

Enhance your chatting experience with Meowgram Connect, a plugin designed to offer additional chat settings customization options. Although currently limited, more features are planned for future updates.

You can find Meowgram Connect in the plugin registry and install it directly from the Cheshire Cat admin interface under the Plugins tab.

![Meowgram Connect](/assets/Screenshot%20from%202024-05-13%2015-46-05.png)

## Sending Voice Notes

To send voice notes using Meowgram, you'll need to install the [Whispering Cat](https://github.com/Furrmidable-Crew/Whispering_Cat) plugin in your Cheshire Cat instance. Whispering Cat enables speech-to-text functionality, allowing you to dictate messages seamlessly.

> [!Note]
> While Whispering Cat is currently the sole plugin supporting this feature, expect more options to become available in the future.

You can install Whispering Cat from the Plugins tab in the Cheshire Cat Admin:

![Whispering Cat](https://github.com/Pingdred/Meowgram/assets/67059270/ff652354-0e9e-4505-b307-6af90d56d0cf)

Be sure to configure Whispering Cat by providing your API Key, preferred language, and setting the `Audio Key` to `meowgram_voice`.

## Receiving Voice Notes

Similar to sending voice notes, receiving them in Meowgram requires the installation of a plugin in Cheshire Cat. The [TTS powered by OpenAI](https://github.com/Pingdred/openai-tts) plugin facilitates text-to-speech conversion.

> [!Note]
> While currently the only supported plugin for this functionality, expect additional options to emerge in the future.

You can install TTS powered by OpenAI from the Plugins tab in the Cheshire Cat Admin:

![TTS powered by OpenAI](/assets/Screenshot%20from%202024-05-13%2015-46-35.png)

After installation, ensure the `Response type` in the plugin settings is set to `TTS key`. Enjoy seamless communication with Meowgram!
