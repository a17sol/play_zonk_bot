from time import time
from random import randrange
from collections import Counter


class GameEnd(Exception):
	pass


class ExtraordinaryRoll(Exception):
	pass


class Game:
	"""
	Representation of a zonk game storing its state.
	All the attributes should be used as read-only.
	To change the game state, use public methods.
	"""
	def __init__(self, type, players):
		if type not in ('classic', 'butovo'):
			raise ValueError("Invalid argument in Game(type, players). "
				"type must be one of 'classic', 'butovo'.")
		if len(players) == 0:
			raise TypeError("Invalid argument in Game(type, players). "
				"players must be an iterable of hashable objects.")
		self.type = type
		self.players = {u:0 for u in players}
		self.current_player = 0
		self.current_roll = []
		self.selected_dices = set()
		self.winners = []
		self.turn = 1
		self.subtotal = 0
		self.over = False
		self.move_start_time = time()
		self.target = 5000
		self._scoring = self._scoring_c if type == 'classic' else self._scoring_b
		self._roll(6)

	def _lock_when_over(func):
		def wrapper(self, *args, **kwargs):
			if self.over:
				raise GameEnd("Game is over, can't continue")
			return func(self, *args, **kwargs)
		return wrapper

	@_lock_when_over
	def select(self, idxs):
		self.selected_dices = set(idxs)

	@_lock_when_over
	def take_and_continue(self):
		score, dices_used = self._scoring()
		self.subtotal += score
		if score == 0:
			self._next_move()
			self._roll(6)
		else:
			self._roll(len(self.current_roll) - dices_used or 6)

	@_lock_when_over
	def take_and_finish(self):
		score, dices_used = self._scoring()
		current_usr = self.current_user()
		if score != 0:
			self.subtotal += score
			self.players[current_usr] += self.subtotal
		if self.players[current_usr] >= self.target:
			self.winners.append(current_usr)
			del self.players[current_usr]
			self.current_player -= 1
			if len(self.players) <= 1:
				self._game_end()
				return
		self._next_move()
		self._roll(6)

	@_lock_when_over
	def kick(self, user):
		target_player_idx = list(self.players).index(user)
		del self.players[user]
		if len(self.players) <= 1:
			self._game_end()
			return
		if target_player_idx > self.current_player:
			return
		self.current_player -= 1
		if target_player_idx == self.current_player + 1:
			self._next_move()
			self._roll(6)
			raise ExtraordinaryRoll("New roll, stay tuned")

	@_lock_when_over
	def current_user(self):
		return list(self.players)[self.current_player]

	def _roll(self, amount):
		self.current_roll = [randrange(1, 7) for _ in range(amount)]
		self.selected_dices = set()

	def _next_move(self):
		if self.current_player == len(self.players) - 1:
			self.turn += 1
		self.current_player = (self.current_player + 1) % len(self.players)
		self.subtotal = 0
		self.move_start_time = time()

	def _game_end(self):
		self.winners.extend(list(self.players))
		self.players = {}
		self.over = True
		raise GameEnd("The game is over")

	def _scoring_c(self):
		values = [0, 100, 20, 30, 40, 50, 60]
		mult = [0, 0, 0, 10, 20, 40, 80]
		count = 0
		dices_used = 0
		di = self.current_roll
		sel = self.selected_dices
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

	def _scoring_b(self):
		values = [0, 100, 20, 30, 40, 50, 60]
		mult = [0, 0, 0, 10, 20, 40, 80]
		combos = {"123456": 1500, "23456": 750, "12345": 500}
		count = 0
		dices_used = 0
		di = self.current_roll
		sel = self.selected_dices
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

