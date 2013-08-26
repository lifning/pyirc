import io

try:
	from .IRCConnection import *
except:
	from IRCConnection import *

class IRCChannel(io.RawIOBase):
	def __init__(self, channel, connection, readpipe):
		self.connection = connection
		self.channel = channel
		self.users = set()
		connection.write('JOIN %s' % channel)
		self.mypipe = os.fdopen(readpipe, 'rb')

	def readline(self):
		return self.mypipe.readline().decode(self.connection.encoding, 'replace')

	def read(self):
		return self.mypipe.read().decode(self.connection.encoding, 'replace')

	def write(self, msg):
		self.connection.write('PRIVMSG %s :%s' % (self.channel, msg))

	def close(self):
		self.mypipe.close()
		self.connection.write('PART %s' % self.channel)

	def kick(self, who):
		self.connection.write('KICK %s %s' % (self.channel, who))

	# misc. filelike-isms
	def fileno(self): return self.mypipe.fileno()
	def seek(self, n): raise IOError("not a seekable object")
	def tell(self): raise IOError("not a seekable object")
	def truncate(self): raise IOError("not a truncatable object")
	def readable(self): return True
	def writable(self): return True
	def seekable(self): return False
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_value, exc_traceback): self.close()

