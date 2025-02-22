from telegram import LinkPreviewOptions
from telegram.ext import CommandHandler, CallbackQueryHandler
from telegram.error import BadRequest

import ui
import invite
import game
from poll import create_poll, unstore_poll

def register_handlers(app):
	app.add_handlers([
		CommandHandler("start", start),
		CommandHandler("zonk", zonk),
		CommandHandler("zonk_b", zonk_b),
		CommandHandler("leave", leave),
		CommandHandler("rules", rules),
		CommandHandler("help", send_help),
		CommandHandler("ver", ver),
		CommandHandler("stat", stat),
		CallbackQueryHandler(button_callback),
	])


async def start(update, context):
	await update.message.reply_text(text=ui.start, disable_notification=True)


async def ver(update, context):
	await update.message.reply_text("2025-02-22 17:46")


async def rules(update, context):
	await update.message.reply_html(text=ui.rules, disable_notification=True)


async def send_help(update, context):
	await update.message.reply_text(
		text=ui.send_help, 
		link_preview_options=LinkPreviewOptions(is_disabled=True), 
		disable_notification=True
	)


async def zonk(update, context):
	await post_invite('classic', update, context)

async def zonk_b(update, context):
	await post_invite('butovo', update, context)

async def post_invite(type, update, context):
	if 'game' in context.chat_data:
		await update.message.reply_text("Игра уже идёт", disable_notification=True)
		return
	if 'invite' in context.chat_data:
		await update.message.reply_text("В этом чате уже есть приглашение", disable_notification=True)
		return
	context.chat_data['invite'] = invite.Invite(type, update.effective_user)
	context.chat_data["board"] = await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=ui.make_inviteboard(context),
		parse_mode="html", 
		reply_markup=ui.make_invite_markup(context)
	)


async def leave(update, context):
	if 'game' in context.chat_data:
		try:
			await kick(update.effective_user, context)
		except ValueError:
			await update.message.reply_text("Ты не в списке участников", disable_notification=True)
		else:
			await update.message.reply_text("Ты покинул(а) игру", disable_notification=True)


	elif 'invite' in context.chat_data:
		try:
			context.chat_data['invite'].remove(update.effective_user)
		except invite.InitiatorDeletionError:
			await update.message.reply_text("Организатор не может покинуть игру до её начала. "
				"Чтобы отменить игру, воспользуйся соответствующей кнопкой.", disable_notification=True)
		except invite.PlayerNotFoundError:
			await update.message.reply_text("Ты не в списке участников", disable_notification=True)
		else:
			await update.message.reply_text("Ты покинул(а) игру", disable_notification=True)
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context), 
				reply_markup=ui.make_invite_markup(context), 
				parse_mode="html"
			)

	else:
		await update.message.reply_text("Игра не запущена", disable_notification=True)


async def stat(update, context):
	games = []
	invites = []
	for chat_id, chat_data in context.application.chat_data.items():
		if chat_data["game"]:
				games.append(chat_id)
		if chat_data["invite"]:
			invites.append(chat_id)
	await update.message.reply_text("Games: " + str(active_games) + "\nInvites: " + str(invites_waiting))


# Button callback

async def button_callback(update, context):
	query = update.callback_query
	user = query.from_user
	button_type, owner_id = query.data.split(":")

	if button_type == "join":
		try:
			context.chat_data['invite'].add(user)
		except ValueError:
			await query.answer("Ты уже в списке участников")
			return
		else:
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context), 
				reply_markup=ui.make_invite_markup(context), 
				parse_mode="html"
			)

	elif str(user.id) != owner_id:
		await query.answer("Это не твоя кнопка")
		return

	elif button_type == "begin":
		context.chat_data['game'] = game.Game(context.chat_data['invite'].type, context.chat_data['invite'].get_players())
		del context.chat_data['invite']
		await show_roll(context)

	elif button_type == "cancel":
		del context.chat_data['invite']
		await query.edit_message_text("Игра отменена")

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


# Aux

async def kick(user, context):
	# Raises ValueError if user not in game
	try:
		context.chat_data['game'].kick(user)
	except game.ExtraordinaryRoll:
		await show_roll(context)
	except game.GameEnd:
		await show_game_end(context)
	else:
		await context.chat_data["board"].edit_text(
			ui.make_scoreboard(context), 
			parse_mode="html"
		)


async def show_roll(context):
	tmp_board = await context.bot.send_message(
		chat_id=context._chat_id,
		text=ui.make_scoreboard(context),
		parse_mode="html",
		disable_notification=True
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
		text=ui.make_leaderboard(context),
		parse_mode="html",
		disable_notification=True
	)
	await safe_delete(context.chat_data["board"])
	await safe_delete(unstore_poll(context))
	del context.chat_data['game']


async def safe_delete(msg):
	try:
		await msg.delete()
	except BadRequest:
		pass # Continue if message was already deleted by user in personal chat

