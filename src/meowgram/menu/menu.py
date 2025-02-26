
import logging

from typing import List, Dict, Callable, Optional

from pydantic import BaseModel, model_validator
from telethon.events import NewMessage
from telethon.tl.custom import Button

class MenuButton(BaseModel):
    text: str
    callback: Optional[Callable] = None
    submenu: Optional[str] = None

    @model_validator(mode='after')
    def validate_callback_or_submenu(self):
        if self.callback is None and self.submenu is None:
            raise ValueError("Either callback or submenu must be provided")
        return self

    async def execute(self, event):
        if self.callback:
            await self.callback(event)


class Menu(BaseModel):
    name: str
    parent: str
    buttons: List[List[MenuButton]]

    def get_keyboard(self) -> List[List[Button]]:
        keyboard = []
        current_row = []
        for row in self.buttons:
            for button in row:
                current_row.append(Button.text(button.text, resize=True))
            keyboard.append(current_row)
            current_row = []

        return keyboard

    def get_button(self, button_text: str) -> Optional[MenuButton]:
        for row in self.buttons:
            for button in row:
                if button.text == button_text:
                    return button
        return None

    async def handle_button(self, button_text: str, event: NewMessage.Event) -> Optional[str]:
        """
        Handle the button that was clicked, execute the callback if it exists.

        Return the name of the menu to show next if the button is handled, None otherwise.
        """

        button = self.get_button(button_text)

        # Button not found in the menu
        if button is None:
            return None
        
        # Execute the button callback
        await button.execute(event)

        # Return the submenu if it exists
        if button.submenu is not None:
            return button.submenu
        
        # Otherwise, return to itself
        return self.name
    

class MenuManager:

    def __init__(self):
        # Memorize the menus structure
        self.menus: Dict[str, Menu] = {}
        # Memorize the parent menu for each menu
        self.parent_menus: Dict[str, str] = {}
        # Store current menu for each user
        self.user_states: Dict[int, str] = {}

        self.main_menu = "main"

        # Default texts
        self.new_menu_message = "Select an option"
        self.home_button_text = "🏠 Home"
        self.back_button_text = "⬅️ Back"

    def add_menu(self, menu: Menu):
        if menu.name in self.menus:
            raise ValueError(f"Menu {menu.name} already exists")
        
        last_row = []
        # Add the back button to the menu
        if menu.parent != menu.name:
            last_row.append(MenuButton(text=self.back_button_text, submenu=menu.parent))

        # Add the home button to the menu
        # if it is not the main menu and the parent is not the main menu
        if (menu.name != self.main_menu) and (menu.parent != self.main_menu):
           last_row.append(MenuButton(text=self.home_button_text, submenu=self.main_menu))

        menu.buttons.append(last_row)
        self.menus[menu.name] = menu

    def create_menu(self, menu_id: str, items: List[List[MenuButton]], parent: str):
        self.add_menu(Menu(
            name=menu_id,
            buttons=items,
            parent=parent,
        ))

    def get_keyboard(self, menu_id: str) -> List[List[Button]]:
        return self.menus[menu_id].get_keyboard()

    async def handle_menu(self, event: NewMessage.Event) -> bool:        
        current_menu_id = self.get_current_menu(event.sender_id)

        if current_menu_id is not None:
            # Handle the button in the current menu
            if await self._handle_in_menu(event, current_menu_id):
                return True
            
        logging.warning(f"The current menu is unknown for user {event.sender_id}")
        
        # Search for the button in all menus
        matching_menus = self._search_button(event.raw_text, limit=2)
        menu_len = len(matching_menus)

        # Button not found in any menu
        if menu_len == 0:
            return False

        # Button found in one menu, handle it
        # and switch to the new menu
        if menu_len == 1:
            menu_id = matching_menus[0]
            await self._handle_in_menu(event, menu_id)
            return True
        
        logging.warning(f"Button `{event.raw_text}` found in multiple menus: {matching_menus}. Switching to the `{self.main_menu}` menu")
        
        # Button found in multiple menus, switch to the main menu
        # not handling the button to avoid ambiguity
        self.set_current_menu(event.sender_id, self.main_menu)
        await event.reply(
            self.new_menu_message,
            buttons=self.get_keyboard(self.main_menu)
        )
        return True

    def _search_button(self, button_text: str, limit: int) -> Optional[str]:
        found = 0
        menu_ids = []
        # Check if the button is in any menu
        for _, menu in self.menus.items():
            # Check if the button is in the menu
            if menu.get_button(button_text) is not None:
                menu_ids.append(menu.name)
                found += 1

            # Exit if the button is found in more than one menu
            if found > limit:
                break

        return menu_ids

    async def _handle_in_menu(self, event: NewMessage.Event, menu_id: str) -> bool:
        button_text = event.raw_text
        new_menu_id = await self.menus[menu_id].handle_button(button_text, event)

        # Button not in the menu
        if new_menu_id is None:
            return False
        
        if new_menu_id == self.get_current_menu(event.sender_id):
            return True

        self.set_current_menu(event.sender_id, new_menu_id)
        await event.reply(
            self.new_menu_message,
            buttons=self.get_keyboard(new_menu_id)
        )
        return True

    def get_current_menu(self, user_id: int) -> str:
        if user_id not in self.user_states:
            self.user_states[user_id] = None
        return self.user_states[user_id]
   
    def set_current_menu(self, user_id: int, menu_id: str) -> None:
        if menu_id not in self.menus:
            raise ValueError(f"Menu `{menu_id}` does not exist, first add the menu with `add_menu`")
        
        if user_id not in self.user_states:
            self.user_states[user_id] = menu_id
        else:
            self.user_states[user_id] = menu_id