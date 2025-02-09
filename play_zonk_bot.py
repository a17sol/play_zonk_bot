from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, PollAnswerHandler
from random import randrange, shuffle, choice
from collections import Counter

token = "REDACTED"

target = 5000

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text("Привет! Я зонк-бот для групповых чатов. Добавляй меня в группы и пиши /zonk, чтобы начать игру с друзьями!", disable_notification=True)

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

	print("play()")

	if context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра уже идёт", disable_notification=True)
		return

	user = update.effective_user
	context.chat_data["game_in_process"] = True
	context.chat_data["players"] = []
	context.chat_data["initiator"] = user

	context.chat_data["board"] = await context.bot.send_message(
		chat_id=update.effective_chat.id,
		text=make_inviteboard(context),
		parse_mode="html", 
		reply_markup=make_invite_markup(context)
	)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

	query = update.callback_query
	user = query.from_user
	button_type, owner_id = query.data.split(":")

	if button_type == "join" and str(user.id) != owner_id and user not in context.chat_data["players"]:
		context.chat_data["players"].append(user)
		await query.edit_message_text(
			make_inviteboard(context),
			parse_mode="html",
			reply_markup=make_invite_markup(context)
		)
	
	elif button_type == "begin" and str(user.id) == owner_id:
		context.chat_data["players"].append(user)
		shuffle(context.chat_data["players"])
		context.chat_data["players"] = {pl : 0 for pl in context.chat_data["players"]}
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		context.chat_data["current_player"] = None
		context.chat_data["leaderboard"] = []
		context.chat_data["current_roll"] = []
		context.chat_data["selected_dices"] = set()
		context.chat_data["subtotal"] = 0
		context.chat_data["turn"] = 1
		await next_move(update, context)

	elif button_type == "cancel" and str(user.id) == owner_id:
		context.chat_data["game_in_process"] = False
		await query.edit_message_text("Игра отменена")

	elif button_type == "notake" and str(user.id) == owner_id:
		await query.message.delete()
		await next_move(update, context)

	elif button_type == "take&continue" and str(user.id) == owner_id:
		subsubtotal, dices_used = scoring(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
			await next_move(update, context)
		else:
			context.chat_data["subtotal"] += subsubtotal
			dices_to_roll = len(context.chat_data["current_roll"]) - dices_used
			if dices_to_roll == 0:
				dices_to_roll = 6
			await roll(dices_to_roll, context)
		await query.message.delete()

	elif button_type == "take&finish" and str(user.id) == owner_id:
		subsubtotal, _ = scoring(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
		else:
			context.chat_data["subtotal"] += subsubtotal
		context.chat_data["players"][context.chat_data["current_player"]] += context.chat_data["subtotal"]
		player_points = context.chat_data["players"][context.chat_data["current_player"]]
		await query.message.delete()
		if player_points >= target:
			context.chat_data["leaderboard"].append(context.chat_data["current_player"])
			del context.chat_data["players"][context.chat_data["current_player"]]
			if len(context.chat_data["players"]) <= 1:
				context.chat_data["leaderboard"] += list(context.chat_data["players"])
				await context.chat_data["board"].delete()
				context.chat_data["board"] = await context.bot.send_message(
					chat_id=context._chat_id,
					text=make_leaderboard(context),
					parse_mode="html",
					disable_notification=True
				)
				context.chat_data["game_in_process"] = False
				return
		await next_move(update, context)

	await query.answer()


async def next_move(update, context):
	try:
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])
	except StopIteration:
		context.chat_data["turn"] += 1
		tu = context.chat_data["turn"]
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])

	context.chat_data["subtotal"] = 0
	await roll(6, context)


async def roll(dices_to_roll, context):

	emo = "\uFE0F\u20E3"

	#await context.chat_data["board"].edit_text(make_scoreboard(context), parse_mode="html")
	await context.chat_data["board"].delete()
	context.chat_data["board"] = await context.bot.send_message(
		chat_id=context._chat_id,
		text=make_scoreboard(context),
		parse_mode="html",
		disable_notification=True
	)

	context.chat_data["current_roll"] = [randrange(1, 7) for _ in range(dices_to_roll)]
	context.chat_data["selected_dices"] = set()
	additional_opt = [choice(["Рисковая игра!", "Йо-хо-хо!", "Кто не рискует - тот не пьёт!", "Риск - моё второе имя!", "Шансы 2 к 6!"])] if len(context.chat_data["current_roll"]) == 1 else []
	options = [str(i)+emo for i in context.chat_data["current_roll"]] + additional_opt

	poll_msg = await context.bot.send_poll(
		chat_id=context._chat_id,
		question="Выбери кости",
		options=options,
		is_anonymous=False,
		allows_multiple_answers=True,
		# reply_markup=make_take_markup(context.chat_data["current_player"].id, context)
		reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Не забирать", callback_data=f"notake:{context.chat_data['current_player'].id}")]]),
		disable_notification=True
	)

	context.bot_data["poll:user"][poll_msg.poll.id] = context.chat_data["current_player"].id
	context.bot_data["poll:chat"][poll_msg.poll.id] = context._chat_id
	context.bot_data["poll:msg"][poll_msg.poll.id] = poll_msg
	context.bot_data["poll:context"][poll_msg.poll.id] = context
	# TODO: remove redundant data storage (msg contains all necessary info, I believe;
	# or use poll:chat to get correct chat context)


def make_take_markup(user_id, context):
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	keyboard = []
	keyboard.append([InlineKeyboardButton("Забрать и продолжить", callback_data=f"take&continue:{user_id}")])
	keyboard.append([InlineKeyboardButton("Забрать и закончить", callback_data=f"take&finish:{user_id}")])
	return InlineKeyboardMarkup(keyboard)

def make_invite_markup(context):
	user = context.chat_data["initiator"]
	keyboard = [
		[InlineKeyboardButton("Я хочу!", callback_data=f"join:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы начать", callback_data=f"begin:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы отменить", callback_data=f"cancel:{user.id}")],
	]
	return InlineKeyboardMarkup(keyboard)

def make_inviteboard(context):
	string = context.chat_data['initiator'].mention_html() + " хочет сыграть. Кто в деле?\n"
	if context.chat_data['players']:
		players_names = [u.mention_html() for u in context.chat_data["players"]]
		string += "Отозвались:\n" + "\n".join(players_names)
	return string

def make_scoreboard(context):
	string = "Круг " + str(context.chat_data["turn"]) + "\n"
	string += "Текущий счёт:\n"
	for u, p in context.chat_data["players"].items():
		string += f"{u.full_name} - {p}"
		if u == context.chat_data["current_player"]:
			string += "+" + str(context.chat_data["subtotal"])
		string += "\n"
	for u in context.chat_data["leaderboard"]:
		string += f"{u.full_name} закончил\n"
	#string += "\n".join([f"{u.full_name} - {p}" for u, p in context.chat_data["players"].items()]) + "\n"
	string += "Ходит " + context.chat_data["current_player"].mention_html()
	return string

def make_leaderboard(context):
	string = "Игра окончена!\n"
	for i, u in enumerate(context.chat_data["leaderboard"]):
		string += f"{i + 1} место - {u.mention_html()}" + "\n"
	return string


def scoring(context):
	values = [0, 100, 20, 30, 40, 50, 60]
	mult = [0, 0, 0, 10, 20, 40, 80]
	count = 0
	dices_used = 0
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	take = [di[n] for n in sel if n < len(di)]
	take_table = Counter(take)
	if len(take_table) == 6:
		count += 1500
		dices_used += 6
	elif len(take_table) == 3 and all(i[1] == 2 for i in take_table.items()):
		count += 750
		dices_used += 6
	else:
		for points, times in take_table.items():
			if mult[times]:
				count += values[points] * mult[times]
				dices_used += times
			elif points in (1, 5):
				count += values[points] * times
				dices_used += times
	return count, dices_used


async def poll_answer(update, context):
	poll_answer = update.poll_answer
	answered_user = poll_answer.user.id
	intended_user = context.bot_data["poll:user"][poll_answer.poll_id]
	if answered_user == intended_user:
		await context.bot_data["poll:msg"][poll_answer.poll_id].edit_reply_markup(make_take_markup(answered_user, context.bot_data["poll:context"][poll_answer.poll_id]))
		option_indexes = poll_answer.option_ids
		chat_id = context.bot_data["poll:chat"][poll_answer.poll_id]
		context.application.chat_data[chat_id]["selected_dices"] = set(option_indexes)
		del context.bot_data["poll:user"][poll_answer.poll_id]
		del context.bot_data["poll:chat"][poll_answer.poll_id]
		del context.bot_data["poll:msg"][poll_answer.poll_id]
		del context.bot_data["poll:context"][poll_answer.poll_id]


# async def resend(update, context):
# 	msg = context.chat_data['cached_message']
# 	if context.chat_data['game_in_process'] and context.chat_data['turn']:
# 		markup = make_dice_markup(context.chat_data['current_player'].id, context)
# 	else:
# 		markup = make_invite_markup(context.chat_data['current_player'], context)
# 	await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, 
# 		reply_markup=markup,
# 		parse_mode="html"
# 	)



application = Application.builder().token(token).build()

application.bot_data["poll:user"] = {}
application.bot_data["poll:chat"] = {}
application.bot_data["poll:msg"] = {}
application.bot_data["poll:context"] = {}

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("zonk", play))
# application.add_handler(CommandHandler("resend", resend))
application.add_handler(CallbackQueryHandler(button_callback))
application.add_handler(PollAnswerHandler(poll_answer))


application.run_polling(allowed_updates=Update.ALL_TYPES)



