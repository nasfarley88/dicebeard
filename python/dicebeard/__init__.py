from copy import deepcopy
import io

import telepot
import telepot.aio
from telepot import glance
from telepot.namedtuple import InlineKeyboardMarkup, InlineKeyboardButton

from skybeard.beards import BeardChatHandler, ThatsNotMineException
from skybeard.decorators import onerror, getargsorask, getargs

from .skb_roll import roll
from .helper import TrainResult, AnswerTimer
from .utils import image_to_bytesio


class DiceBeard(BeardChatHandler):

    __commands__ = [
        ('roll', 'roll', 'Rolls dice. Parses args and rolls.'),
        ('train', 'train', 'does some training'),
        ('trainmany', 'train_many', 'Trains dice roll <code>n</code> times.'),
        # TODO reinstate coins when imlemented
        # ('flip', 'flip_coin', 'Flips a number of coins and returns the result'),
        ('mode', 'choose_mode', ('Can change the output mode of the bot'
                                 ' between picture, icons and text')),
    ]

    __userhelp__ = ('Can roll dice or flip coins.\n\n'
                    'To roll dice use the /roll command followed by any '
                    'number of arguments of the form 3d6+5 (can be + or -) '
                    'seperated by spaces. Currently, supported dice for '
                    'producing images are d4, d6, d8, d10, d12 and d20. To '
                    'flip coins simply type /flip followed by the number of '
                    'coins you would like to flip (e.g /flip 10 will filp 10 '
                    'coins)').strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(
                    text='Picture', callback_data=self.serialize('image')),
                 InlineKeyboardButton(
                     text='Text', callback_data=self.serialize('text'))],
            ])

        # Can be 'text' or 'image'
        self.mode = 'image'

    _timeout = 90

    @onerror()
    @getargs()
    async def train_many(self, msg, no_of_times, no_of_dice=3):
        total_score = 0
        try:
            no_of_times = int(no_of_times)
        except ValueError:
            await self.sender.sendMessage(
                "I require an integer number of turns.")

        for i in range(int(no_of_times)):
            # Change message to be something more pallatable
            msg_edited = deepcopy(msg)
            msg_edited['text'] = "/train {}".format(no_of_dice)
            result = await self.train(msg_edited)
            if result.correct:
                total_score += result.time
            else:
                total_score += 10.

        assert isinstance(total_score, float)
        await self.sender.sendMessage(
                "Your total score is {:.3} for {} turns".format(
                    total_score, no_of_times))

    async def _create_personal_listener_from_msg(self, msg):
        my_listener = self.bot.create_listener()
        my_listener.capture([{'from': {'id': msg['from']['id']}},
                             {'chat': {'id': msg['chat']['id']}}])

        return my_listener

    @onerror()
    @getargs()
    async def train(self, msg, no_of_dice=3):
        '''Game for training adding up dice.'''
        try:
            no_of_dice = int(no_of_dice)
        except ValueError:
            await self.sender.sendMessage("Sorry, '{}' is not an number.")
            return

        if no_of_dice > 10:
            await self.sender.sendMessage(
                "Sorry, that's too many dice! Try a number under 10.")
            return

        r = roll('{}d6'.format(no_of_dice))
        if self.mode == 'image':
            await self._send_roll(r, with_total=False, scattered=True)
        else:
            await self._send_roll(r, with_total=False)

        my_listener = await self._create_personal_listener_from_msg(msg)

        with AnswerTimer() as timer:
            msg = await my_listener.wait()

        # Check if the answer is a number
        try:
            answer = int(msg['text'])
        except ValueError:
            await self.sender.sendMessage("That answer was not a number.")
            return
        except KeyError:
            await self.sender.sendMessage(
                "Please answer with text based numbers.")
            return

        result = TrainResult(r, answer, timer.total_time)

        # Report back to the user about their answer
        if result.correct:
            await self.sender.sendMessage(
                'Correct: {:.3}s'.format(timer.total_time))

        else:
            await self.sender.sendMessage(
                'Wrong: {:.3}s'.format(timer.total_time))

        return result

    async def _send_roll(self, roll, *args, **kwargs):
        """Sends roll through telegram using preferred method."""

        try:
            if self.mode == "text":
                await self.sender.sendMessage(roll.to_text(*args, **kwargs))
            elif self.mode == "image":
                out_img = roll.to_image(*args, **kwargs)
                bytes_output = image_to_bytesio(out_img)

                await self.sender.sendPhoto(bytes_output)
            else:
                raise NotImplementedError(
                    "That mode is not implemented: {}".format(self.mode))
        except NotImplementedError:
            await self.sender.sendMessage(
                "Mode not supported with this expression.")
            await self.sender.sendMessage(roll.to_text())

    @onerror()
    @getargsorask([('roll_expr', 'What dice do you want to roll?')])
    async def roll(self, msg, roll_expr):
        self.logger.debug(roll_expr)
        r = roll(roll_expr)
        await self._send_roll(r)

    @onerror()
    @getargsorask([('input_args', 'How many coins do you want to flip?')])
    async def flip_coin(self, msg, input_args):
        raise NotImplementedError

    @onerror()
    async def choose_mode(self, msg):
        await self.sender.sendMessage('Please choose:',
                                      reply_markup=self.keyboard)

    async def on_callback_query(self, msg):
        query_id, from_id, query_data = glance(msg, flavor='callback_query')

        try:
            data = self.deserialize(query_data)
        except ThatsNotMineException:
            return

        await self.bot.editMessageText(
            telepot.origin_identifier(msg),
            text="Mode changed to: {}".format(data),
            reply_markup=self.keyboard)

        self.mode = data

