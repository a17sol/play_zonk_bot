from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from random import randrange
from collections import Counter

token = "REDACTED"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text("Привет! Я зонк-бот для групповых чатов.")


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	if context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра уже идёт")
		return
	context.chat_data["game_in_process"] = True
	context.chat_data["players"] = {}

	user = update.effective_user

	reply_markup = make_invite_markup(user, context)

	context.chat_data["cached_message"] = f"{user.mention_html()} хочет сыграть. Кто в деле?"
	await update.message.reply_text(context.chat_data["cached_message"],
		parse_mode="html", 
		reply_markup=reply_markup
	)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	query = update.callback_query
	user = query.from_user
	button_type, owner_id = query.data.split(":")

	if button_type == "join" and str(user.id) != owner_id and user not in context.chat_data["players"]:
		context.chat_data["players"][user] = 0
		players_names = [u.mention_html() for u in context.chat_data["players"]]
		saved_markup = query.message.reply_markup
		await query.edit_message_text(context.chat_data["cached_message"] + "\nОтозвались:\n" + f"{', '.join(players_names)}", 
			parse_mode="html",
			reply_markup=saved_markup
		)
	
	elif button_type == "begin" and str(user.id) == owner_id:
		players_names = [u.mention_html() for u in context.chat_data["players"]]
		context.chat_data["players"][user] = 0
		context.chat_data["player_iterator"] = iter(context.chat_data["players"])
		context.chat_data["current_player"] = None
		context.chat_data["current_roll"] = []
		context.chat_data["selected_dices"] = set()
		context.chat_data["subtotal"] = 0
		context.chat_data["turn"] = 1
		await query.edit_message_text(context.chat_data["cached_message"] + "\nОтозвались:\n" + f"{', '.join(players_names)}" + "\nИгра начата!", 
			parse_mode="html",
		)
		await context.bot.send_message(chat_id=update.effective_chat.id, text="Круг "+str(context.chat_data["turn"]))
		await next_move(update, context)

	elif button_type == "cancel" and str(user.id) == owner_id:
		context.chat_data["game_in_process"] = False
		await query.edit_message_text("Игра отменена")

	elif button_type.startswith("dice") and str(user.id) == owner_id:
		dice_num = int(button_type[-1])
		if dice_num not in context.chat_data["selected_dices"]:
			context.chat_data["selected_dices"].add(dice_num)
		else:
			context.chat_data["selected_dices"].remove(dice_num)
		markup = make_dice_markup(user.id, context)
		await query.edit_message_text(context.chat_data["cached_message"]+"\nОчки за ход: "+str(context.chat_data["subtotal"]), 
			parse_mode="html",
			reply_markup=markup
		)

	elif button_type == "take&continue" and str(user.id) == owner_id:
		subsubtotal, dices_used = scoring(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
			await query.edit_message_text(context.chat_data["cached_message"]+"\nОчки за ход: 0", 
				parse_mode="html"
			)
			await next_move(update, context)
		else:
			context.chat_data["subtotal"] += subsubtotal
			dice_amount = len(context.chat_data["current_roll"]) - dices_used
			if dice_amount == 0:
				dice_amount = 6
			context.chat_data["current_roll"] = [randrange(1, 7) for _ in range(dice_amount)]
			context.chat_data["selected_dices"] = set()
			markup = make_dice_markup(user.id, context)
			await query.edit_message_text(context.chat_data["cached_message"]+"\nОчки за ход: "+str(context.chat_data["subtotal"]), 
				parse_mode="html",
				reply_markup=markup
			)

	elif button_type == "take&finish" and str(user.id) == owner_id:
		subsubtotal, _ = scoring(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
		else:
			context.chat_data["subtotal"] += subsubtotal

		await query.edit_message_text(context.chat_data["cached_message"]+"\nОчки за ход: "+str(context.chat_data["subtotal"]), 
			parse_mode="html"
		)
		context.chat_data["players"][context.chat_data["current_player"]] += context.chat_data["subtotal"]
		await next_move(update, context)

	await query.answer()


async def next_move(update, context):
	try:
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])
	except StopIteration:
		context.chat_data["turn"] += 1
		tu = context.chat_data["turn"]
		context.chat_data["player_iterator"] = iter(context.chat_data["players"])
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])
		await context.bot.send_message(chat_id=update.effective_chat.id, text="Круг "+str(tu)+"\nТекущий счёт:\n"+"\n".join([f"{u.full_name} - {p}" for u, p in context.chat_data["players"].items()]))

	context.chat_data["current_roll"] = [randrange(1, 7) for _ in range(6)]
	context.chat_data["selected_dices"] = set()
	context.chat_data["subtotal"] = 0

	msg = context.chat_data["cached_message"] = "Ходит "+pl.mention_html()

	markup = make_dice_markup(pl.id, context)
	await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, 
		reply_markup=markup,
		parse_mode="html"
	)


def make_dice_markup(user_id, context):
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	keyboard = [[InlineKeyboardButton(f"[{i}]" if n in sel else f"{i}", callback_data=f"dice-{n}:{user_id}") for n, i in enumerate(di)]]
	keyboard.append([InlineKeyboardButton("Забрать и продолжить", callback_data=f"take&continue:{user_id}")])
	keyboard.append([InlineKeyboardButton("Забрать и закончить", callback_data=f"take&finish:{user_id}")])
	return InlineKeyboardMarkup(keyboard)

def make_invite_markup(user, context):
	keyboard = [
		[InlineKeyboardButton("Я хочу!", callback_data=f"join:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы начать", callback_data=f"begin:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы отменить", callback_data=f"cancel:{user.id}")],
	]
	return InlineKeyboardMarkup(keyboard)

def scoring(context):
	values = [0, 100, 20, 30, 40, 50, 60]
	mult = [0, 0, 0, 10, 20, 40, 80]
	count = 0
	dices_used = 0
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	take = [di[n] for n in sel]
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


async def resend(update, context):
	msg = context.chat_data['cached_message']
	if context.chat_data['game_in_process'] and context.chat_data['turn']:
		markup = make_dice_markup(context.chat_data['current_player'].id, context)
	else:
		markup = make_invite_markup(context.chat_data['current_player'], context)
	await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, 
		reply_markup=markup,
		parse_mode="html"
	)


application = Application.builder().token(token).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("play", play))
application.add_handler(CommandHandler("resend", resend))
application.add_handler(CallbackQueryHandler(button_callback))


application.run_polling(allowed_updates=Update.ALL_TYPES)



