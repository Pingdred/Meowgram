import asyncio
import logging
import json

from cheshire_cat_api import CatClient, Config


class CCatConnection:

    def __init__(self, user_id, out_queue: asyncio.Queue, ccat_url: str = "localhost", ccat_port: int = 1865) -> None:
        self.user_id = user_id

        # Get event loop
        self._loop = asyncio.get_running_loop()

        # Queue of the messages to send on telegram
        self._out_queue = out_queue
        
        conf = Config(
            base_url=ccat_url,
            port=ccat_port,
            user_id=user_id,
        )

        # Instantiate the Cheshire Cat client
        self.ccat = CatClient(
            config=conf,
            on_open=self._on_open,
            on_close=self._on_close,
            on_message=self._ccat_message_callback
        )

        self.last_interaction = time.time()


    def _ccat_message_callback(self, message: str):
        # Websocket on_mesage callback

        message = json.loads(message)

        # Put the new message from the cat in the out queue
        # the websocket runs in its own thread
        # call_soon_threadsafe: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe
        #                       https://stackoverflow.com/questions/53669218/asyncio-queue-get-delay
        self._loop.call_soon_threadsafe(self._out_queue.put_nowait, (message, self.user_id))
    
    
    def _on_open(self):
        logging.info(f"WS connection with user `{self.user_id}` to CheshireCat opened")


    def _on_close(self, close_status_code: int, msg: str):
        logging.info(f"WS connection `{self.user_id}` to CheshireCat closed")
    

    def send(self, message: str, **kwargs):
        self.last_interaction = time.time()
        self.ccat.send(message=message, **kwargs)
