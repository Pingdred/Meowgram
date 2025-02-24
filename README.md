## Meowgram

<p align="center">
  <img src="https://raw.githubusercontent.com/Pingdred/Meowgram/main/logo.png" alt="Meowgram logo"/>
</p>

Welcome to **Meowgram**, a Telegram client designed to seamlessly integrate with [Cheshire Cat Ai](https://cheshirecat.ai/).

---

## Prerequisites

Before you begin, make sure you have the following:

- Python `>= 3.10`
- A running instance of [Cheshire Cat](https://github.com/cheshire-cat-ai/core#quickstart) (version `>= 1.8.0`)
- Telegram **API Hash**
- A **Telegram bot TOKEN**, which you can get by creating a bot through [BotFather](https://core.telegram.org/bots/features#creating-a-new-bot)

### Obtaining the API Hash

1. Log in to your Telegram account using the developer phone number.
2. Navigate to **API Development Tools**.
3. In the **Create New Application** window, fill in the App title and Short name.
4. Click **Create Application**. Your **API Hash** is secret—**do not share it**.

---

## Installation

Follow these steps to get Meowgram up and running:

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Pingdred/Meowgram.git
   ```

2. **Navigate to the project directory:**

   ```bash
   cd Meowgram
   ```

3. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

4. **Create a `.env` file** and set the following parameters:

   ```toml
   API_ID = "API_ID"
   API_HASH = "API_HASH"
   BOT_TOKEN = "YOUR-BOT-TOKEN"

   CHESHIRE_CAT_URL = "localhost"
   CHESHIRE_CAT_PORT = 1865
   ```

   You can use the provided `.env.example` file as a template.

> **Important:**  
> Ensure that your Cheshire Cat instance is running by following the [quick start guide](https://github.com/cheshire-cat-ai/core#quickstart).

5. **Run Meowgram**:

   ```bash
   python src/main.py
   ```

---

## Meowgram Connect

**Meowgram Connect** is a plugin that enhances your chat experience with additional customization options, such as buttons for forms.

You can find **Meowgram Connect** in the plugin registry and install it directly from the Cheshire Cat Admin interface under the **Plugins** tab.

![Meowgram Connect](assets/Screenshot%20from%202024-05-13%2015-46-05.png)

---

## Media Support

Meowgram supports the media features introduced in Cheshire Cat `1.8.0`.

### Sending Voice Notes

To send voice notes via Meowgram, install the [Whispering Cat](https://github.com/Furrmidable-Crew/Whispering_Cat) plugin for Cheshire Cat. Whispering Cat enables speech-to-text functionality, allowing you to dictate messages seamlessly.

> **Note:**  
> Currently, **Whispering Cat** is the only plugin supporting this feature. Expect more options in the future.

Install **Whispering Cat** from the **Plugins** tab in the Cheshire Cat Admin.

![Whispering Cat](https://github.com/Pingdred/Meowgram/assets/67059270/ff652354-0e9e-4505-b307-6af90d56d0cf)

### Receiving Voice Notes

To receive voice notes in Meowgram, install the [TTS powered by OpenAI](https://github.com/Pingdred/openai-tts) plugin for text-to-speech conversion.

> **Note:**  
> Currently, **TTS powered by OpenAI** is the only supported plugin for this functionality, but additional options are expected soon.

Install **TTS powered by OpenAI** from the **Plugins** tab in the Cheshire Cat Admin.

![TTS powered by OpenAI](assets/Screenshot%20from%202024-05-13%2015-46-35.png)
