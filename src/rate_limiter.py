import asyncio
import logging
from time import time

from telegram.ext import CallbackContext, BaseRateLimiter
from telegram.error import RetryAfter


import ui

class LazyLimiter(BaseRateLimiter):
	query_id_2_chat_id = {}
	chat_id_2_retry_time = {}

	@classmethod
	def add_query(cls, query):
		cls.query_id_2_chat_id[query.id] = query.message.chat.id

	@classmethod
	def get_query_id_by_chat_id(cls, chat_id):
		# Slow method to use only is exception handling
		for query_id_rec, chat_id_rec in cls.query_id_2_chat_id.items():
			if chat_id == chat_id_rec:
				return query_id_rec
		return None

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
			if self.query_id_2_chat_id.pop(data["callback_query_id"], None):
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

				if query_id := self.get_query_id_by_chat_id(chat_id):
					bot = callback.__self__
					await bot.answer_callback_query(
						callback_query_id=query_id, 
						text=ui.retry_after(sleep), 
						show_alert=True
					)

				await asyncio.sleep(sleep)
				del self.chat_id_2_retry_time[chat_id]
