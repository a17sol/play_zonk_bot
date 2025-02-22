from time import time

from telegram.ext import CallbackContext

from handlers import kick, safe_delete


def set_up_moderation(app):
	app.job_queue.run_repeating(check_inactivity, interval=60)


async def check_inactivity(context):
	current_time = time()

	for chat_id, chat_data in context.application.chat_data.items():

		if (game := chat_data.get('game')) and game.move_start_time + 900 < current_time:
			user = chat_data['game'].current_user()
			await context.bot.send_message(
				chat_id=chat_id, 
				text=user.mention_html() + " кикнут(а), так как не закончил(а) ход за 15 минут.", 
				parse_mode='html'
			)
			chat_context = CallbackContext(context.application, chat_id=chat_id)
			await kick(user, chat_context)

		elif (inv := chat_data.get('invite')) and inv.creation_time + 900 < current_time:
			await context.bot.send_message(
				chat_id=chat_id, 
				text="Приглашение удалено, так как игра не началась за 15 минут.", 
				parse_mode='html'
			)
			del chat_data['invite']
			await safe_delete(chat_data['board'])

