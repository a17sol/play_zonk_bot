from random import shuffle
from time import time


class PlayerNotFoundError(Exception):
    pass


class InitiatorDeletionError(Exception):
    pass


class Invite:
	def __init__(self, type, initiator):
		if type not in ('classic', 'butovo'):
			raise ValueError("Invalid argument in Game(type, players). "
				"type must be one of 'classic', 'butovo'.")
		self.type = type
		self.players = []
		self.initiator = initiator
		self.creation_time = time()

	def add(self, user):
		if user in self.players or user == self.initiator:
			raise ValueError("User already in list")
		self.players.append(user)

	def remove(self, user):
		if user == self.initiator:
			raise InitiatorDeletionError("Initiator cannot be removed")
		if user not in self.players:
			raise PlayerNotFoundError("User not in list")
		self.players.remove(user)

	def get_players(self):
		all_players = self.players + [self.initiator]
		shuffle(all_players)
		return all_players

