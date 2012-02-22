from multiprocessing import Pipe
from io import RawIOBase

from .IRCConnection import *

class IRCChannel(RawIOBase):
	def __init__(self, channel, connection, pipe):
		self.connection = connection
		self.channel = channel
		self.users = set()
		connection.write('JOIN %s' % channel)

		self.mypipe = pipe

	def readline(self):
		return self.mypipe.recv() # hack? maybe?

	def read(self, maxlen = None):
		return self.mypipe.recv(maxlen)

	def write(self, msg):
		self.connection.send('PRIVMSG %s :%s' % (self.channel, msg))

	def close(self):
		self.mypipe.close()
		self.connection.send('PART %s' % self.channel)

	def kick(self, who):
		self.connection.send('KICK %s %s' % (self.channel, who))

	# misc. filelike-isms
	def fileno(self): return self.mypipe.fileno()
	def seek(self, n): raise IOError("not a seekable object")
	def tell(self): raise IOError("not a seekable object")
	def truncate(self): raise IOError("not a seekable object")
	def readable(self): return True
	def writable(self): return True
	def seekable(self): return False
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_value, exc_traceback): self.close()

