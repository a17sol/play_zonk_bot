from telegram.error import BadRequest

import ui
from poll import create_poll, unstore_poll
from game import ExtraordinaryRoll, GameEnd


async def kick(user, context):
	# Raises ValueError if user not in game
	try:
		context.chat_data['game'].kick(user)
	except ExtraordinaryRoll:
		await show_roll(context)
	except GameEnd:
		await show_game_end(context)
	else:
		await context.chat_data["board"].edit_text(
			ui.make_scoreboard(context)
		)


async def show_roll(context):
	tmp_board = await context.bot.send_message(
		chat_id=context._chat_id,
		text=ui.make_scoreboard(context)
	)
	poll = unstore_poll(context)
	await create_poll(context)
	await safe_delete(context.chat_data["board"])
	context.chat_data["board"] = tmp_board
	try:
		await poll.delete()
	except AttributeError:
		pass # Suppress error on first move when unstore_poll returns None


async def show_game_end(context):
	await context.bot.send_message(
		chat_id=context._chat_id,
		text=ui.make_leaderboard(context)
	)
	await safe_delete(context.chat_data["board"])
	await safe_delete(unstore_poll(context))
	context.application.drop_chat_data(context._chat_id)


async def safe_delete(msg):
	try:
		await msg.delete()
	except BadRequest:
		pass # Continue if message was already deleted by user in personal chat

