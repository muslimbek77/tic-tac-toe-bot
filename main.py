import logging
from typing import Optional

from telegram import InlineQueryResultArticle, InputTextMessageContent, \
    InlineKeyboardMarkup, InlineKeyboardButton, User, TelegramError
from telegram.ext import Updater, Dispatcher, InlineQueryHandler, \
    CallbackContext, CallbackQueryHandler, DictPersistence
from telegram.update import Update

import settings

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO)

persistence = DictPersistence()
updater = Updater(
    token=settings.TELEGRAM_TOKEN,
    persistence=persistence
)

dispatcher: Dispatcher = updater.dispatcher

NONE = '⬜'
CROSS = '❌'
CIRCLE = '⭕'
HAND = '👈'
WINNER = '🤩'
LOSER = '😭'
DRAW = '😡'


class Grid:
    def __init__(self, grid: list):
        if len(grid) != 9:
            grid = [0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.items = grid.copy()

    def has_ended(self):
        return len(list(filter(lambda x: x == 0, self.items))) == 0

    def get_winner(self):
        winner = None
        for i in range(3):
            temp = self._check_row_x(i) or self._check_row_y(i)
            if temp is not None:
                winner = temp
        temp = self._check_diagonal_1()
        if temp is not None:
            winner = temp
        temp = self._check_diagonal_2()
        if temp is not None:
            winner = temp
        return winner

    def _check_finished(self, items):
        finished = True
        temp = None

        for i in items:
            if i == 0:
                finished = False
                break
            else:
                if temp is None:
                    temp = i

                if temp != i:
                    finished = False
        if finished:
            return temp
        else:
            return None

    def _check_row_x(self, index):
        items = [self.items[index * 3], self.items[index * 3 + 1],
                 self.items[index * 3 + 2]]
        return self._check_finished(items)

    def _check_row_y(self, index):
        items = [self.items[0 + index], self.items[3 + index],
                 self.items[6 + index]]
        return self._check_finished(items)

    def _check_diagonal_1(self):
        items = [self.items[0], self.items[4], self.items[8]]
        return self._check_finished(items)

    def _check_diagonal_2(self):
        items = [self.items[2], self.items[4], self.items[6]]
        return self._check_finished(items)


class Game:
    def __init__(self, context: CallbackContext):
        self._context = context
        self._bot_data = context.bot_data
        if self._bot_data.get('games_increment', None) is None:
            self._bot_data.update({
                'games_increment': 1,
            })
        self.game_name = None
        self.game = None

    def _get_next_game_id(self):
        _id = self._bot_data['games_increment']
        self._bot_data.update({
            'games_increment': _id + 1
        })
        return _id

    def store_data(self):
        temp = self.game.copy()
        temp['grid'] = self.game['grid'].items
        self._bot_data.update({
            self.game_name: temp
        })

    def new_game(self, is_player1_first: bool):
        self.game_name = 'game' + str(self._get_next_game_id())
        self.game = {
            'player1': {
                'id': None,
                'name': '?'
            },
            'player2': {
                'id': None,
                'name': '?'
            },
            'grid': Grid([]),
            # True <- player2
            # False <- player1
            'turn': False,
            # True  <- player1 = x, player2 = o
            # False <- player1 = o, player2 = x
            'is_player1_first': is_player1_first,
            'locked': False,
        }
        self.store_data()

    def get_game(self, name):
        self.game_name = name
        self.game = self._bot_data.get(name, None)
        if self.game is not None:
            temp = self.game.get('grid', Grid([]))
            grid = temp
            if isinstance(temp, list):
                grid = Grid(temp)
            self.game.update({
                'grid': grid
            })

    def set_player1(self, user: User):
        self.game['player1'] = {
            'id': user.id,
            'name': user.first_name,
        }
        self.store_data()

    def set_player2(self, user: User):
        self.game['player2'] = {
            'id': user.id,
            'name': user.first_name,
        }
        self.store_data()

    def get_turn_message(self):
        game = self.game
        player1 = game['player1']
        player2 = game['player2']
        turn = game['turn']
        is_player_first = game['is_player1_first']

        return f"{CROSS if is_player_first else CIRCLE}" \
               f" {player1['name']} " \
               f"{'' if turn else HAND}" \
               f"\n" \
               f"{CIRCLE if is_player_first else CROSS}" \
               f" {player2['name']} " \
               f"{HAND if turn else ''}"

    def get_end_message(self):
        game = self.game
        player1 = game['player1']
        player2 = game['player2']
        is_player_first = game['is_player1_first']
        grid: Grid = self.game['grid']
        winner = grid.get_winner()
        player1_emoji = DRAW
        player2_emoji = DRAW

        if winner:
            if is_player_first:
                player1_emoji = WINNER if winner == 1 else LOSER
                player2_emoji = WINNER if winner == 2 else LOSER
            else:
                player1_emoji = LOSER if winner == 1 else WINNER
                player2_emoji = LOSER if winner == 2 else WINNER

        return f"{CROSS if is_player_first else CIRCLE}" \
               f" {player1['name']} " \
               f"{player1_emoji}" \
               f"\n" \
               f"{CIRCLE if is_player_first else CROSS}" \
               f" {player2['name']} " \
               f"{player2_emoji}"

    def switch_turn(self):
        turn = self.game['turn']
        self.game['turn'] = not turn
        self.store_data()

    def make_move(self, user: User, index: int):
        changed = False
        game = self.game
        player1 = game['player1']
        player2 = game['player2']
        is_player1_first = self.game['is_player1_first']

        if player2['id'] is None:
            if user.id != player1['id']:
                self.set_player2(user)
                player2 = game['player2']
                changed = True
            else:
                return changed

        if not (player1['id'] == user.id or
                player2['id'] == user.id):
            return changed

        turn = game['turn']

        if index is None:
            return changed

        current_player = player2 if turn else player1

        if current_player['id'] != user.id:
            return changed

        can_turn = game['grid'].items[index] == 0

        if not can_turn:
            return changed

        if turn:
            game['grid'].items[index] = 2 if is_player1_first else 1
        else:
            game['grid'].items[index] = 1 if is_player1_first else 2

        self.store_data()

        self.switch_turn()
        return True


def generate_keyboard(game: Optional[Game], is_player1_first: bool):
    keyboard = []

    for i in range(3):
        temp_keyboard = []
        for j in range(3):
            index = i * 3 + j
            if game is None:
                item = 0
                callback_data = \
                    f"new_game|{'True' if is_player1_first else 'False'}"
            else:
                grid: Grid = game.game['grid']
                item = grid.items[index]
                callback_data = f'{game.game_name}|{index}'
            text = NONE if item == 0 else CROSS if item == 1 else CIRCLE
            temp_keyboard.append(
                InlineKeyboardButton(
                    text=text,
                    callback_data=callback_data
                )
            )
        keyboard.append(temp_keyboard)

    return keyboard


def inline_query(update: Update, context: CallbackContext) -> None:
    update.inline_query.answer([
        InlineQueryResultArticle(
            id="x", title='X',
            input_message_content=
            InputTextMessageContent('Press any button, please'),
            reply_markup=InlineKeyboardMarkup(generate_keyboard(None, True)),
        ),
        InlineQueryResultArticle(
            id="o", title='O',
            input_message_content=
            InputTextMessageContent('Press any button, please'),
            reply_markup=InlineKeyboardMarkup(generate_keyboard(None, False)),
        ),
    ])


def callback_query(update: Update, context: CallbackContext):
    query = update.callback_query

    query.answer(text='🤚')

    game = Game(context)
    is_player1_first = True
    index = None
    changed = False

    if 'new_game' in query.data:
        is_player1_first = \
            True if query.data.split('|')[1] == 'True' else False
        game.new_game(is_player1_first=is_player1_first)
        game.set_player1(update.effective_user)
        changed = True
    else:
        game_name, index = query.data.split('|')
        index = int(index)
        game.get_game(game_name)
        if game.game is None:
            game.new_game(is_player1_first=is_player1_first)
            game.set_player1(update.effective_user)
            changed = True

    changed = changed or game.make_move(update.effective_user, index)

    grid: Grid = game.game['grid']
    winner = grid.get_winner()
    if winner or grid.has_ended():
        query.edit_message_text(
            text=game.get_end_message(),
        )
    elif changed:
        try:
            query.edit_message_text(
                text=game.get_turn_message(),
                reply_markup=InlineKeyboardMarkup(
                    generate_keyboard(game, is_player1_first)
                )
            )
        except:
            try:
                query.edit_message_reply_markup(
                    reply_markup=InlineKeyboardMarkup(
                        generate_keyboard(game, is_player1_first)
                    )
                )
            except TelegramError as e:
                print(e)
                pass


dispatcher.add_handler(InlineQueryHandler(inline_query))
dispatcher.add_handler(CallbackQueryHandler(callback_query))

updater.start_polling()
updater.idle()