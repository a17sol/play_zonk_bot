import logging

from telegram.ext import PollAnswerHandler

import ui


def register_poll_handler(app):
	app.add_handler(PollAnswerHandler(poll_answer))


# Poll answer handler

async def poll_answer(update, context):
	poll_answer = update.poll_answer
	poll_message = context.bot_data["poll_id:poll_msg"][poll_answer.poll_id]
	chat_data = context.application.chat_data[poll_message.chat.id]
	answered_user = poll_answer.user.id
	intended_user = chat_data['game'].current_user().id
	if answered_user == intended_user:
		chat_data['game'].select(poll_answer.option_ids)
		if poll_answer.option_ids:
			await poll_message.edit_reply_markup(ui.make_take_markup(answered_user))
		else:
			await poll_message.edit_reply_markup(ui.make_notake_markup(answered_user))


# Poll management

async def poll_storage_init(application):
	if not application.bot_data.get("poll_id:poll_msg", False):
		application.bot_data["poll_id:poll_msg"] = {}
	if not application.bot_data.get("chat_id:poll_msg", False):
		application.bot_data["chat_id:poll_msg"] = {}


async def create_poll(context):
	logging.info("Entered create_poll function")
	current_user = context.chat_data['game'].current_user()
	while True:
		try:
			poll_msg = await context.bot.send_poll(
				chat_id=context._chat_id,
				question=ui.poll_header(current_user.first_name),
				options=ui.make_poll_opts(context),
				is_anonymous=False,
				allows_multiple_answers=True,
				reply_markup=ui.make_notake_markup(current_user.id)
			)
			break
		except Exception as e:
			await context.bot.send_message(
				chat_id=context._chat_id,
				text=ui.poll_send_error
			)
			logging.warning(
				"%s exception while sending poll message. Retrying.",
				type(e).__name__
			)
	context.bot_data["poll_id:poll_msg"][poll_msg.poll.id] = poll_msg
	context.bot_data["chat_id:poll_msg"][context._chat_id] = poll_msg


def unstore_poll(context):
	if poll_msg := context.bot_data["chat_id:poll_msg"].get(context._chat_id, None):
		del context.bot_data["poll_id:poll_msg"][poll_msg.poll.id]
		del context.bot_data["chat_id:poll_msg"][context._chat_id]
	return poll_msg

