from random import choice

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


start = (
	"Привет! Я зонк-бот для групповых чатов. "
	"Добавляй меня в группы и пиши /zonk, чтобы начать игру с друзьями!\n"
	"Дополнительная информация здесь: /help"
)

rules = (
	"<b>Правила игры</b>\n"
	"Игроки по очереди бросают 6 кубиков и ищут комбинации в своём броске. "
	"Комбинации можно забрать в руку и получить очки, затем можно либо перебросить "
	"незабранные кубики и т.д., либо закончить ход. Если в броске нет ни одной "
	"комбинации, набранные за ход очки сгорают, и ход переходит к следующему. "
	"Если игроку удалось забрать все 6 костей, ему даётся ещё 6 и ход продолжается. "
	"Игра ведётся до 5000 очков, игроки занимают места в порядке достижения цели.\n"
	"\n<b>Комбинации</b>\n"
	"1\uFE0F\u20E3 - 100\n"
	"5\uFE0F\u20E3 - 50\n"
	"Три одинаковых \U000023FA\U000023FA\U000023FA - их номинал × 100\n"
	"Три единицы 1\uFE0F\u20E31\uFE0F\u20E31\uFE0F\u20E3 - 1000\n"
	"Каждая следующая такая же кость удваивает очки\n"
	"1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E3"
	"4\uFE0F\u20E35\uFE0F\u20E36\uFE0F\u20E3 - 1500\n"
	"<b>Только в классическом зонке:</b>\n"
	"Три пары \U000023FA\U000023FA\U0001F53C\U0001F53C\U000023F9\U000023F9 - 750\n"
	"<b>Только в бутовском зонке:</b>\n"
	"1\uFE0F\u20E32\uFE0F\u20E33\uFE0F\u20E34\uFE0F\u20E35\uFE0F\u20E3 - 500\n"
	"2\uFE0F\u20E33\uFE0F\u20E34\uFE0F\u20E35\uFE0F\u20E36\uFE0F\u20E3 - 750"
)

send_help = (
	"""Все команды:
	/start - Приветствие
	/help - Помощь
	/rules - Правила игры
	/zonk - Начать игру в зонк
	/zonk_b - Начать игру в бутовский зонк
	/leave - Покинуть игру
	Автор: https://t.me/Misha_Solovyev
	Исходный код: https://github.com/a17sol/play_zonk_bot"""
)


def make_take_markup(user_id):
	keyboard = []
	keyboard.append([InlineKeyboardButton("Забрать и продолжить", callback_data=f"take&continue:{user_id}")])
	keyboard.append([InlineKeyboardButton("Забрать и закончить", callback_data=f"take&finish:{user_id}")])
	return InlineKeyboardMarkup(keyboard)


def make_notake_markup(user_id):
	keyboard = [[InlineKeyboardButton("Не забирать", callback_data=f"notake:{user_id}")]]
	return InlineKeyboardMarkup(keyboard)


def make_invite_markup(context):
	user = context.chat_data["invite"].initiator
	keyboard = [
		[InlineKeyboardButton("Я хочу!", callback_data=f"join:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы начать", callback_data=f"begin:{user.id}")],
		[InlineKeyboardButton(f"{user.first_name}, нажми, чтобы отменить", callback_data=f"cancel:{user.id}")],
	]
	return InlineKeyboardMarkup(keyboard)


def make_inviteboard(context):
	invite = context.chat_data['invite']
	string = invite.initiator.mention_html() + " хочет сыграть в "
	string += "бутовский зонк" if invite.type == 'butovo' else "классический зонк"
	string += ". Кто в деле?\n"
	if invite.players:
		players_names = [u.mention_html() for u in invite.players]
		string += "Отозвались:\n" + "\n".join(players_names)
	return string


def make_scoreboard(context):
	game = context.chat_data['game']
	string = "Бутовский" if game.type == 'butovo' else "Классический"
	string += " зонк\nКруг " + str(game.turn) + "\n"
	string += "Текущий счёт:\n"
	for u, p in game.players.items():
		string += f"{u.full_name} - {p}"
		if u == list(game.players)[game.current_player]:
			string += "+" + str(game.subtotal)
		string += "\n"
	for u in game.winners:
		string += f"{u.full_name} закончил(а)\n"
	string += "Ходит " + list(game.players)[game.current_player].mention_html()
	return string


def make_leaderboard(context):
	string = "Игра окончена!\n"
	for i, u in enumerate(context.chat_data["game"].winners):
		string += f"{i + 1} место - {u.mention_html()}" + "\n"
	return string


def make_poll_opts(context):
	opts = context.chat_data["game"].current_roll
	emo = "\uFE0F\u20E3"
	jokes = [
		"Рисковая игра!", 
		"Йо-хо-хо!", 
		"Кто не рискует - тот не пьёт!", 
		"Риск - моё второе имя!", 
		"Шансы 2 к 6!",
		"Шанс!"
	]
	additional_opt = [choice(jokes)] if len(opts) == 1 else []
	return [str(i) + emo for i in opts] + additional_opt
