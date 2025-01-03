from aiohttp import ClientWebSocketResponse, ClientSession
import json
import logging
from typing import Optional, Callable

from cheshire_cat_api import CatClient, Config

class CheshireCatClient:
    """
    Client per la comunicazione con Cheshire Cat.
    Gestisce la connessione WebSocket e l'invio/ricezione dei messaggi.
    """
    def __init__(self, base_url: str, port: int, user_id: str):
        self.ws_url = f"ws://{base_url}:{port}/ws"
        self.session: Optional[ClientSession] = None
        self.ws: Optional[ClientWebSocketResponse] = None
        # Callback che verrà chiamata quando arriva un messaggio
        self.message_callback: Optional[Callable] = None

        conf = Config(
            base_url=base_url,
            port=port,
            user_id=user_id,
        )

        # Instantiate the Cheshire Cat client
        self.api = CatClient(
            config=conf
        )
        
        # Setup logging base
        self.logger = logging.getLogger()


    async def connect(self, user_id: str) -> bool:
        """
        Stabilisce la connessione WebSocket con Cheshire Cat.
        Crea una nuova sessione se non esiste già.
        """
        if not self.session:
            self.session = ClientSession()
            
        try:
            self.ws = await self.session.ws_connect(f"{self.ws_url}/{user_id}")
            self.logger.info(f"Connesso a Cheshire Cat per l'utente {user_id}")
            return True
        except Exception as e:
            self.logger.error(f"Errore nella connessione: {e}")
            return False

    async def listen(self):
        """
        Ascolta i messaggi in arrivo dal WebSocket.
        Quando arriva un messaggio, chiama la callback registrata.
        """
        if not self.ws:
            return
            
        async for msg in self.ws:
            if msg.type == 1:  # TYPE_TEXT
                try:
                    data = json.loads(msg.data)
                    if self.message_callback:
                        await self.message_callback(data)
                except json.JSONDecodeError:
                    self.logger.error("Ricevuto messaggio JSON non valido")

    async def send_message(self, message: dict):
        """
        Invia un messaggio a Cheshire Cat.
        Il messaggio deve essere un dizionario che verrà convertito in JSON.
        """
        if not self.ws:
            self.logger.error("WebSocket non connesso")
            return False
            
        try:
            await self.ws.send_json(message)
            return True
        except Exception as e:
            self.logger.error(f"Errore nell'invio del messaggio: {e}")
            return False

    def set_message_handler(self, callback: Callable):
        """
        Registra una callback che verrà chiamata per ogni messaggio ricevuto.
        """
        self.message_callback = callback

    async def disconnect(self):
        """
        Chiude la connessione WebSocket e la sessione.
        """
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()