from time import time

from telegram.ext import CallbackContext

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

