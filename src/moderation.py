from time import time
import logging
import asyncio

from telegram.ext import CallbackContext, BaseRateLimiter
from telegram.error import RetryAfter, BadRequest

from helpers import kick, safe_await
import ui


def set_up_moderation(app):
	app.job_queue.run_repeating(check_inactivity, interval=60)


async def check_inactivity(context):
	current_time = time()
	ito = tto = 900

	for chat_id, chat_data in dict(context.application.chat_data).items():

		if (game := chat_data.get('game')) and game.move_start_time + tto < current_time:
			user = chat_data['game'].current_user()
			chat_context = CallbackContext(context.application, chat_id=chat_id)
			await safe_await(
				context.bot.send_message,
				chat_id=chat_id,
				text=ui.turn_timeout(user, tto),
				disable_notification=False
			)
			await kick(user, chat_context)

		elif (inv := chat_data.get('invite')) and inv.creation_time + ito < current_time:
			await safe_await(chat_data['board'].delete)
			await safe_await(
				context.bot.send_message,
				chat_id=chat_id,
				text=ui.invite_timeout(ito)
			)
			context.application.drop_chat_data(chat_id)


class LazyLimiter(BaseRateLimiter):
	chat_id_2_query = {}
	query_id_2_chat_id = {}
	chat_id_2_retry_time = {}

	@classmethod
	def add_query(cls, query):
		cls.chat_id_2_query[query.message.chat.id] = query
		cls.query_id_2_chat_id[query.id] = query.message.chat.id

	@classmethod
	def chat_is_waiting(cls, chat_id):
		return chat_id in cls.chat_id_2_retry_time

	@classmethod
	def remaining_time(cls, chat_id):
		return cls.chat_id_2_retry_time[chat_id] - time()

	def __init__(self):
		pass
	async def initialize(self):
		pass
	async def shutdown(self):
		pass

	async def process_request(self, callback, args, kwargs, endpoint, data, rate_limit_args):
		if endpoint == "answerCallbackQuery":
			if chat_id := self.query_id_2_chat_id.pop(data["callback_query_id"], None):
				del self.chat_id_2_query[chat_id]
				return await callback(*args, **kwargs)
			return

		for i in range(5):
			try:
				return await callback(*args, **kwargs)
			except RetryAfter as exc:
				chat_id = data["chat_id"]
				sleep = exc.retry_after + 1
				self.chat_id_2_retry_time[chat_id] = time() + sleep
				logging.info("Flood control exceeded. Retry after %d sec.", sleep)
				query = self.chat_id_2_query[chat_id]
				await query.answer(ui.retry_after(sleep), show_alert=True)
				await asyncio.sleep(sleep)
				del self.chat_id_2_retry_time[chat_id]
