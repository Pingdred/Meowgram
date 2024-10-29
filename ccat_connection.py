import json
import asyncio
import logging
import websockets

from cheshire_cat_api import CatClient, Config


class CCatConnection:

    def __init__(self, user_id, out_queue: asyncio.Queue, ccat_url: str = "localhost", ccat_port: int = 1865) -> None:
        self.user_id = user_id

        # Queue of the messages to send on telegram
        self._out_queue = out_queue

        self._is_connected = False
        
        self.ws_url = f"ws://{ccat_url}:{ccat_port}/ws/{user_id}"
        
        self.websocket = None
        self.recive_task = None

        conf = Config(
            base_url=ccat_url,
            port=ccat_port,
            user_id=user_id,
        )

        # Instantiate the Cheshire Cat client
        self.api = CatClient(
            config=conf
        )
       

    async def connect(self):
        # Tentiamo la connessione
        self.websocket = await websockets.connect(self.ws_url)
        self._is_connected = True
        
        logging.info(f"Connected to WebSocket for user {self.user_id}")
        
        self.recive_task = asyncio.create_task(self._receive_messages())        

    async def _receive_messages(self):
        # Routine per gestire i messaggi in arrivo dal WebSocket
        try:
            async for message in self.websocket:
                message_data = json.loads(message)
                # Invia il messaggio ricevuto a out_queue per Telegram
                await self._out_queue.put((message_data, self.user_id))
        except websockets.ConnectionClosed as e:
            logging.warning(f"Connection closed for user {self.user_id}: {e}")
            self._is_connected = False

    async def send(self, **kwargs):
        """Invia un messaggio tramite WebSocket come JSON."""
        if not self._is_connected:
            logging.warning("Cannot send message, WebSocket is not connected.")
            return
        
        try:
            message = {
                **kwargs
            }
            
            message["text"] = message["message"]
            del message["message"]
            
            message = json.dumps(message)
            await self.websocket.send(message)
            logging.info(f"Sent message: {message}")
        except Exception as e:
            logging.error(f"Error sending message: {e}")

    async def disconnect(self):
        if self._is_connected and self.websocket:
            await self.websocket.close()
            
        if self.recive_task:
            self.recive_task.cancel()
        
        self._is_connected = False
        logging.info(f"WebSocket disconnected for user {self.user_id}")

    @property
    def is_connected(self):
        return self._is_connected
        