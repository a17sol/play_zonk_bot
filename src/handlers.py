import logging

from telegram import LinkPreviewOptions
from telegram.ext import CommandHandler, CallbackQueryHandler

import ui
import invite
import game
from helpers import show_roll, show_game_end, kick


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
	await update.message.reply_text(text=ui.start)


async def ver(update, context):
	await update.message.reply_text("2025-02-22 17:46")


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
		await update.message.reply_text("Игра уже идёт")
		return
	if 'invite' in context.chat_data:
		await update.message.reply_text("В этом чате уже есть приглашение")
		return
	context.chat_data['invite'] = invite.Invite(type, update.effective_user)
	context.chat_data["board"] = await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=ui.make_inviteboard(context),
		reply_markup=ui.make_invite_markup(context),
		disable_notification=False
	)
	logging.info("Invite posted in chat %d \"%s\" by %s", 
		update.message.chat.id, 
		update.message.chat.title or "(personal chat)", 
		update.effective_user.full_name
	)


async def leave(update, context):
	if 'game' in context.chat_data:
		try:
			await kick(update.effective_user, context)
		except ValueError:
			await update.message.reply_text("Ты не в списке участников")
		else:
			await update.message.reply_text("Ты покинул(а) игру")

	elif 'invite' in context.chat_data:
		try:
			context.chat_data['invite'].remove(update.effective_user)
		except invite.InitiatorDeletionError:
			await update.message.reply_text("Организатор не может покинуть игру до её начала. "
				"Чтобы отменить игру, воспользуйся соответствующей кнопкой.")
		except invite.PlayerNotFoundError:
			await update.message.reply_text("Ты не в списке участников")
		else:
			await update.message.reply_text("Ты покинул(а) игру")
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context),
				reply_markup=ui.make_invite_markup(context)
			)

	else:
		await update.message.reply_text("Игра не запущена")


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

	if button_type == "join":
		try:
			context.chat_data['invite'].add(user)
		except ValueError:
			await query.answer("Ты уже в списке участников")
			return
		else:
			await context.chat_data["board"].edit_text(
				ui.make_inviteboard(context),
				reply_markup=ui.make_invite_markup(context)
			)

	elif str(user.id) != owner_id:
		await query.answer("Это не твоя кнопка")
		return

	elif button_type == "begin":
		context.chat_data['game'] = game.Game(
			context.chat_data['invite'].type, 
			context.chat_data['invite'].get_players()
		)
		del context.chat_data['invite']
		await show_roll(context)

	elif button_type == "cancel":
		context.application.drop_chat_data(context._chat_id)
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

