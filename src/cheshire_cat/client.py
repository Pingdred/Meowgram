import json
import asyncio
import logging

from aiohttp import ClientWebSocketResponse, ClientSession
from typing import Optional, Callable

from pydantic import BaseModel

from cheshire_cat_api import CatClient, Config

class CheshireCatClient:

    def __init__(self, base_url: str, port: int, user_id: str, message_callback: Callable):
        self.user_id = user_id

        self.ws_url = f"ws://{base_url}:{port}/ws/{user_id}"
        self.session: Optional[ClientSession] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        # Callback che verrà chiamata quando arriva un messaggio
        self.message_callback: Callable = message_callback

        conf = Config(
            base_url=base_url,
            port=port,
            user_id=user_id,
        )

        # Instantiate the Cheshire Cat client
        self.api = CatClient(
            config=conf
        )

        self.listener_task = None
        
        # Setup logging base
        self.logger = logging.getLogger(__name__)

    async def __listen(self):
        """
        Listen for incoming messages from Cheshire Cat, and call the message callback.
        """
        if not self.ws:
            return
            
        async for msg in self.ws:
            if msg.type == 1:  # TYPE_TEXT
                try:
                    data = json.loads(msg.data)

                    self.logger.debug("Recived Chehsire Cat message:")
                    logging.debug(json.dumps(data, indent=4))

                    if self.message_callback:
                        await self.message_callback(data)
                except json.JSONDecodeError:
                    self.logger.error("Ricevuto messaggio JSON non valido")
                except Exception as e:
                    self.logger.error(f"Errore nella gestione del messaggio: {e}")
                    self.logger.error(f"Message: {msg.data}")

    async def connect(self) -> bool:
        """
        Connect to Cheshire Cat via WebSocket. Create a new session if one does not exist.
        """
        if not self.session:
            self.session = ClientSession()
            
        try:
            self.ws = await self.session.ws_connect(f"{self.ws_url}")
            self.logger.info(f"Connesso a Cheshire Cat per l'utente {self.user_id}")

            self.listener_task = asyncio.create_task(self.__listen())

            return True
        except Exception as e:
            self.logger.error(f"Errore nella connessione: {e}")
            return False

    async def send_message(self, message: dict | BaseModel) -> bool:
        if not self.ws:
            self.logger.error("WebSocket non connesso")
            return False
            
        try:

            if isinstance(message, BaseModel):
                message = message.model_dump(mode="json")

            await self.ws.send_json(message)
            return True
        except Exception as e:
            self.logger.error(f"Errore nell'invio del messaggio: {e}")
            return False

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()