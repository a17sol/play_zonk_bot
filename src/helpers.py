from telegram.error import BadRequest, Forbidden

import ui
from poll import create_poll, unstore_poll, store_poll
from game import ExtraordinaryRoll, GameEnd


async def kick(user, context):
	"""
	Kick the user out from the game defined by context.
	Raises ValueError if user not in game, all other cases handled.
	"""
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
	"""
	Replace existing scoreboard and poll with new ones in proper order.
	"""
	tmp_board = await context.bot.send_message(
		chat_id=context._chat_id,
		text=ui.make_scoreboard(context)
	)
	new_poll = await create_poll(context)
	old_poll = unstore_poll(context)
	store_poll(context, new_poll)
	await safe_await(context.chat_data["board"].delete)
	context.chat_data["board"] = tmp_board
	try:
		await old_poll.delete()
	except AttributeError:
		pass # Suppress error on first move when unstore_poll returns None


async def show_game_end(context):
	"""
	Show leaderboard and safely clear all the game data 
	"""
	await safe_await(
		context.bot.send_message,
		chat_id=context._chat_id,
		text=ui.make_leaderboard(context)
	)
	await safe_await(context.chat_data["board"].delete)
	await safe_await(unstore_poll(context).delete)
	context.application.drop_chat_data(context._chat_id)


async def safe_await(function, *args, **kwargs):
	"""
	Try to run given function (send message, delete message etc.) 
	on given arguments and suppress exceptions if user blocked 
	the bot or deleted the chat or the message.
	"""
	try:
		await function(*args, **kwargs)
	except (BadRequest, Forbidden):
		pass
