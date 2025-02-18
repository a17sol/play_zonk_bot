# TODO: poll:msg & msg:poll (or chat instead of msg?). 
#       poll:msg & chat:poll? save_poll(poll_id, msg), delete_poll(chat_id), chat_by_poll(poll_id)?
#       or even create_poll(context), delete_poll(chat_id/context?), msg_by_poll(poll_id)
# TODO: factor out game end


from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
	Application,
	CommandHandler,
	CallbackQueryHandler,
	ContextTypes,
	PollAnswerHandler,
	PicklePersistence
)
from telegram.error import TelegramError, NetworkError
from random import randrange, shuffle, choice
from collections import Counter
from os import getenv
from asyncio import sleep
import logging


logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s',
	handlers=[
		logging.FileHandler("zonk.log"),
		logging.StreamHandler()
	]
)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

token = getenv("ZONK_TOKEN")
if not token:
	logging.error("Token not set. Aborting.")
	exit()

target = 5000


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
	await update.message.reply_text("Привет! Я зонк-бот для групповых чатов. Добавляй меня в группы и пиши /zonk, чтобы начать игру с друзьями!", disable_notification=True)


async def zonk_b(update, context):
	context.chat_data["game_type"] = "butovo"
	await play(update, context)


async def zonk(update, context):
	context.chat_data["game_type"] = "classic"
	await play(update, context)


async def play(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:

	logging.info("Game started in chat %d \"%s\"", update.message.chat.id, update.message.chat.title)

	if context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра уже идёт", disable_notification=True)
		return

	user = update.effective_user
	context.chat_data["game_in_process"] = randrange(1, 1000000)
	context.chat_data["turn"] = 0
	context.chat_data["players"] = {}
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

	if button_type == "join":
		if str(user.id) == owner_id or user in context.chat_data["players"]:
			await query.answer("Ты уже в списке участников")
			return
		context.chat_data["players"][user] = 0
		await query.edit_message_text(
			make_inviteboard(context),
			parse_mode="html",
			reply_markup=make_invite_markup(context)
		)

	elif str(user.id) != owner_id:
		await query.answer("Это не твоя кнопка")
		return

	elif button_type == "begin":
		context.chat_data["players"][user] = 0
		players = list(context.chat_data["players"])
		shuffle(players)
		context.chat_data["players"] = {pl : 0 for pl in players}
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		context.chat_data["current_player"] = None
		context.chat_data["leaderboard"] = []
		context.chat_data["current_roll"] = []
		context.chat_data["selected_dices"] = set()
		context.chat_data["subtotal"] = 0
		context.chat_data["turn"] = 1
		await next_move(context)

	elif button_type == "cancel":
		context.chat_data["game_in_process"] = 0
		await query.edit_message_text("Игра отменена")

	elif button_type == "notake":
		await next_move(context)
		# await query.message.delete()
		await delete_poll(context)

	elif button_type == "take&continue":
		scoring_func = scoring if context.chat_data["game_type"] == 'clessic' else scoring_b
		subsubtotal, dices_used = scoring_func(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
			await next_move(context)
		else:
			context.chat_data["subtotal"] += subsubtotal
			dices_to_roll = len(context.chat_data["current_roll"]) - dices_used
			if dices_to_roll == 0:
				dices_to_roll = 6
			await roll(dices_to_roll, context)
		# await query.message.delete()
		await delete_poll(context)

	elif button_type == "take&finish":
		scoring_func = scoring if context.chat_data["game_type"] == 'clessic' else scoring_b
		subsubtotal, _ = scoring_func(context)
		if subsubtotal == 0:
			context.chat_data["subtotal"] = 0
		else:
			context.chat_data["subtotal"] += subsubtotal
		context.chat_data["players"][context.chat_data["current_player"]] += context.chat_data["subtotal"]
		player_points = context.chat_data["players"][context.chat_data["current_player"]]
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
				context.chat_data["game_in_process"] = 0
				await query.message.delete()
				return
		await next_move(context)
		# await query.message.delete()
		await delete_poll(context)

	await query.answer()


async def next_move(context):
	try:
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])
	except StopIteration:
		context.chat_data["turn"] += 1
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		pl = context.chat_data["current_player"] = next(context.chat_data["player_iterator"])

	context.chat_data["subtotal"] = 0
	await roll(6, context)
	context.application.create_task(kick_by_time(context))


async def roll(dices_to_roll, context):

	tmp = await context.bot.send_message(
		chat_id=context._chat_id,
		text=make_scoreboard(context),
		parse_mode="html",
		disable_notification=True
	)
	context.chat_data["current_roll"] = [randrange(1, 7) for _ in range(dices_to_roll)]
	context.chat_data["selected_dices"] = set()
	await create_poll(context)
	await context.chat_data["board"].delete()
	context.chat_data["board"] = tmp


def make_take_markup(user_id):
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
	string = context.chat_data['initiator'].mention_html() + " хочет сыграть в "
	string += "бутовский зонк" if context.chat_data['game_type'] == 'butovo' else "классический зонк"
	string += ". Кто в деле?\n"
	if context.chat_data['players']:
		players_names = [u.mention_html() for u in context.chat_data["players"]]
		string += "Отозвались:\n" + "\n".join(players_names)
	return string


def make_scoreboard(context):
	string = "Бутовский" if context.chat_data['game_type'] == 'butovo' else "Классический"
	string += " зонк\nКруг " + str(context.chat_data["turn"]) + "\n"
	string += "Текущий счёт:\n"
	for u, p in context.chat_data["players"].items():
		string += f"{u.full_name} - {p}"
		if u == context.chat_data["current_player"]:
			string += "+" + str(context.chat_data["subtotal"])
		string += "\n"
	for u in context.chat_data["leaderboard"]:
		string += f"{u.full_name} закончил(а)\n"
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


def scoring_b(context):
	values = [0, 100, 20, 30, 40, 50, 60]
	mult = [0, 0, 0, 10, 20, 40, 80]
	combos = {"123456": 1500, "23456": 750, "12345": 500}
	count = 0
	dices_used = 0
	di = context.chat_data["current_roll"]
	sel = context.chat_data["selected_dices"]
	take = [di[n] for n in sel if n < len(di)]
	take_table = Counter(take)
	for combo in combos:
		if all(int(item) in take for item in combo):
			count += combos[combo]
			dices_used += len(combo)
			for i in combo:
				take_table[int(i)] -= 1
			break
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
	poll_message = poll_msg(poll_answer.poll_id, context)
	chat_data = context.application.chat_data[poll_message.chat.id]
	answered_user = poll_answer.user.id
	intended_user = chat_data["current_player"].id
	if answered_user == intended_user:
		await poll_message.edit_reply_markup(make_take_markup(answered_user))
		chat_data["selected_dices"] = set(poll_answer.option_ids)


async def leave(update, context):
	user = update.effective_user

	if not context.chat_data.get("game_in_process", False):
		await update.message.reply_text("Игра не запущена")
	
	elif user == context.chat_data['initiator'] and context.chat_data["turn"] == 0:
		await update.message.reply_text("Организатор не может покинуть игру до её начала. Чтобы отменить игру, воспользуйся соответствующей кнопкой.")

	elif user not in context.chat_data["players"]:
		await update.message.reply_text("Ты не в списке участников")	

	else:
		await kick(user, context)
		await update.message.reply_text("Ты покинул(а) игру")


async def kick_by_time(context):
	player_before = context.chat_data["current_player"]
	turn_before = context.chat_data["turn"]
	game_before = context.chat_data["game_in_process"]
	await sleep(1800)
	player_after = context.chat_data["current_player"]
	turn_after = context.chat_data["turn"]
	game_after = context.chat_data["game_in_process"]
	if player_before.id == player_after.id and turn_before == turn_after and game_before == game_after:
		await kick(player_after, context)
		await context.bot.send_message(chat_id=context._chat_id, text=player_after.mention_html() + " кикнут(а), так как не закончил(а) ход за 30 минут.", parse_mode='html')


async def kick(user, context):
	del context.chat_data["players"][user]

	if context.chat_data["turn"] == 0:
		await context.chat_data["board"].edit_text(make_inviteboard(context), reply_markup=make_invite_markup(context), parse_mode="html")

	elif len(context.chat_data["players"]) <= 1:
		await context.chat_data["board"].delete()
		await delete_poll(context)
		context.chat_data["game_in_process"] = 0
		if len(context.chat_data["players"]) == 1:
			context.chat_data["leaderboard"] += list(context.chat_data["players"])
			context.chat_data["board"] = await context.bot.send_message(
				chat_id=context._chat_id,
				text=make_leaderboard(context),
				parse_mode="html",
				disable_notification=True
			)

	elif context.chat_data["current_player"].id == user.id:
		await delete_poll(context)
		await next_move(context)

	else:
		await context.chat_data["board"].edit_text(make_scoreboard(context), parse_mode="html")
		context.chat_data["player_iterator"] = iter(dict(context.chat_data["players"]))
		while next(context.chat_data["player_iterator"]) != context.chat_data["current_player"]:
			pass


async def ver(update, context):
	await update.message.reply_text("2025-02-19 01:01")


async def err_handler(update, context):
	try:
		raise context.error
	except (TelegramError, NetworkError, TimeoutError, ConnectionError) as e:
		logging.error(f"{type(e).__name__}: {e}")
	except Exception as e:
		logging.error(str(type(e).__name__), exc_info=True)


async def init_poll_index(application):
	if not application.bot_data.get("poll_id:poll_msg", False):
		application.bot_data["poll_id:poll_msg"] = {}
	if not application.bot_data.get("chat_id:poll_msg", False):
		application.bot_data["chat_id:poll_msg"] = {}


async def create_poll(context):
	emo = "\uFE0F\u20E3"
	jokes = ["Рисковая игра!", "Йо-хо-хо!", "Кто не рискует - тот не пьёт!", "Риск - моё второе имя!", "Шансы 2 к 6!"]
	additional_opt = [choice(jokes)] if len(context.chat_data["current_roll"]) == 1 else []
	options = [str(i) + emo for i in context.chat_data["current_roll"]] + additional_opt
	keyboard = [[InlineKeyboardButton("Не забирать", callback_data=f"notake:{context.chat_data['current_player'].id}")]]
	poll_msg = await context.bot.send_poll(
		chat_id=context._chat_id,
		question=context.chat_data["current_player"].first_name + ", выбери кости",
		options=options,
		is_anonymous=False,
		allows_multiple_answers=True,
		reply_markup=InlineKeyboardMarkup(keyboard),
		disable_notification=True
	)
	context.bot_data["poll_id:poll_msg"][poll_msg.poll.id] = poll_msg
	context.bot_data["chat_id:poll_msg"][context._chat_id] = poll_msg


async def delete_poll(context):
	poll_msg = context.bot_data["chat_id:poll_msg"][context._chat_id]
	await poll_msg.delete()
	del context.bot_data["poll_id:poll_msg"][poll_msg.poll.id]
	del context.bot_data["chat_id:poll_msg"][context._chat_id]


def poll_msg(poll_id, context):
	return context.bot_data["poll_id:poll_msg"][poll_id]


persistence = PicklePersistence(filepath='bot_memory.pikle')

application = Application.builder().token(token).persistence(persistence).post_init(init_poll_index).build()

application.add_handlers([
	CommandHandler("start", start),
	CommandHandler("zonk", zonk),
	CommandHandler("zonk_b", zonk_b),
	CommandHandler("leave", leave),
	CommandHandler("ver", ver),
	CallbackQueryHandler(button_callback),
	PollAnswerHandler(poll_answer)
])

application.add_error_handler(err_handler)

application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)



