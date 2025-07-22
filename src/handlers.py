import logging

from telegram import LinkPreviewOptions
from telegram.ext import CommandHandler, CallbackQueryHandler

import ui
import invite
import game
from helpers import show_roll, show_game_end, kick
from rate_limiter import LazyLimiter


def register_handlers(app):
	app.add_handlers([
		CommandHandler("start", start),
		CommandHandler("zonk", zonk),
		CommandHandler("zonk_b", zonk_b),
		CommandHandler("leave", leave),
		CommandHandler("rules", rules),
		CommandHandler("help", send_help),
		CommandHandler("stat", stat),
		CallbackQueryHandler(button_callback),
	])


async def start(update, context):
	await update.message.reply_text(text=ui.start)


async def rules(update, context):
	await update.message.reply_text(text=ui.rules)


async def send_help(update, context):
	await update.message.reply_text(
		text=ui.send_help,
		link_preview_options=LinkPreviewOptions(is_disabled=True),
	)


async def zonk(update, context):
	await post_invite('classic', update, context)

async def zonk_b(update, context):
	await post_invite('butovo', update, context)

async def post_invite(type, update, context):
	if 'game' in context.chat_data:
		await update.message.reply_text(ui.game_exists)
		return
	if 'invite' in context.chat_data:
		await update.message.reply_text(ui.invite_exists)
		return
	context.chat_data['invite'] = invite.Invite(type, update.effective_user)
	context.chat_data["board"] = await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=ui.make_inviteboard(context),
		reply_markup=ui.make_invite_markup(context),
		disable_notification=False
	)
	logging.info("Invite posted in chat %d \"%s\" by @%s, type: \"%s\"", 
		update.message.chat.id, 
		update.message.chat.title or "(personal chat)", 
		update.effective_user.username,
		type
	)


async def leave(update, context):
	if 'game' in context.chat_data:
		try:
			await kick(update.effective_user, context)
		except ValueError:
			await update.message.reply_text(ui.you_dont_play)
		else:
			await update.message.reply_text(ui.you_leave)

	elif 'invite' in context.chat_data:
		try:
			context.chat_data['invite'].remove(update.effective_user)
		except invite.InitiatorDeletionError:
			await update.message.reply_text(ui.initiator_cant_leave)
		except invite.PlayerNotFoundError:
			await update.message.reply_text(ui.you_dont_play)
		else:
			await update.message.reply_text(ui.you_leave)
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context),
				reply_markup=ui.make_invite_markup(context)
			)

	else:
		await update.message.reply_text(ui.game_doesnt_exist)


async def stat(update, context):
	games = []
	invites = []
	for chat_id, chat_data in context.application.chat_data.items():
		if 'game' in chat_data:
			games.append(chat_id)
		if 'invite' in chat_data:
			invites.append(chat_id)
	await update.message.reply_text("Games: " + str(games) + "\nInvites: " + str(invites))


# Button callback

async def button_callback(update, context):
	query = update.callback_query
	user = query.from_user
	button_type, owner_id = query.data.split(":")

	LazyLimiter.add_query(query)
	if LazyLimiter.chat_is_waiting(context._chat_id):
		sec = int(LazyLimiter.remaining_time(context._chat_id))
		await query.answer(ui.retry_after(sec), show_alert=True)
		return

	if button_type == "join":
		try:
			context.chat_data['invite'].add(user)
		except ValueError:
			await query.answer(ui.you_already_play)
			return
		else:
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context),
				reply_markup=ui.make_invite_markup(context)
			)

	elif str(user.id) != owner_id:
		await query.answer(ui.not_your_button)
		return

	elif button_type == "begin":
		logging.info(
			"Game started in chat %d. Players: %s", 
			context._chat_id, 
			[p.username for p in context.chat_data['invite'].get_players()]
		)
		context.chat_data['game'] = game.Game(
			context.chat_data['invite'].type, 
			context.chat_data['invite'].get_players()
		)
		del context.chat_data['invite']
		await show_roll(context)

	elif button_type == "cancel":
		context.application.drop_chat_data(context._chat_id)
		await query.edit_message_text(ui.game_cancelled)

	elif button_type == "take&continue" or button_type == "notake":
		context.chat_data['game'].take_and_continue()
		await show_roll(context)

	elif button_type == "take&finish":
		try:
			context.chat_data['game'].take_and_finish()
		except game.GameEnd:
			await show_game_end(context)
		else:
			await show_roll(context)

	await query.answer()

