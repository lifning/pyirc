from multiprocessing import Pipe
from threading import Thread

from socket import socket, AF_INET, SOCK_STREAM
from select import select
from ssl import wrap_socket as ssl_wrap_socket
from sys import stderr
from io import RawIOBase

import os

try:
	from IRCChannel import IRCChannel
except:
	from .IRCChannel import IRCChannel

CRLF = b'\r\n'

class IRCConnection(RawIOBase):
	MAX_LINE_LENGTH = 512 # according to section 2.3 of RFC1459

	def __init__(self, nickname, server, port=6667, usessl=False, privkey=None):
		self.encoding = 'utf8'
		#self.manager = Manager()
		self.channels = dict()
		self.users = set()

		self.mysock = socket(AF_INET, SOCK_STREAM)
		if usessl: self.mysock = ssl_wrap_socket(self.mysock, keyfile=privkey)
		self.mysock.connect((server, port))
		self.serveraddress = server
		self.myfile = self.mysock.makefile("rb")
		self.nick(nickname)
		self.write('USER %s 8 * :%s IRC Bot' % (nickname, nickname))
		self._starteventloop()


	def _starteventloop(self):
		(pr,pw) = Pipe()
		self.mypipetoeventloop = pw
		proc = Thread(target=self._eventloop, args=(pr,))
		proc.daemon = True
		proc.start()

	def _eventloop(self, readpipe):
		while True:
			ready = select([self.mysock, readpipe], [], [])[0]
			if readpipe in ready:
				chanobj, fname, channel = readpipe.recv()
				self.channels[channel] = (chanobj, fname)
			else:
				self._process(self.readline())

	def _process(self, line):
		if line[0] != ':': return self._process_svr(line)

		(header, x, data) = line[1:].partition(':')
		tmp = header.split(' ')
		(source, action, dest) = (tmp + [None, None])[:3]
		args = tmp[3:]
		(nick, x, host) = source.partition('!')

		logline = None
		if action == "PRIVMSG": logline = '<%s> %s\n' % (nick, data)
		elif action == "JOIN":
			dest = data
			logline = '> %s joined %s\n' % (nick, dest)
		elif action == "PART": logline = '> %s left %s\n' % (nick, dest)
		elif action == "QUIT": logline = '> %s quit\n' % (nick)
		elif action == "TOPIC": logline = '> %s set topic: %s\n' % (nick, data)
		elif action == "MODE" and len(args) >= 2:
			logline = '> %s set %s\n' % (nick, args[0])
			if args[1]: logline = logline[:-1] + (' to %s\n' % ' '.join(args[1:]))
		else: logline = '|%s\n' % line

		if logline and dest in self.channels:
			fdw = os.open(self.channels[dest][1], os.O_WRONLY|os.O_NONBLOCK)
			os.write(fdw, logline.encode(self.encoding))
			os.close(fdw)

	def _process_svr(self, line):
		split = line.split(' ')
		if split[0] == "PING": self.pong(split[1])
		elif split[0] == "ERROR": print("disconnected.", stderr)

	def _parse_modes(self, args):
		pass

	def readline(self):
		msg = self.myfile.readline()
		if not msg: raise EOFError("reached EOF in readline")
		if msg[-1:] in CRLF: msg = msg[:-1]
		if msg[-1:] in CRLF: msg = msg[:-1]
		if type(msg) is bytes: msg = msg.decode(self.encoding, 'replace')
		return msg

	def read(self, maxlen = None):
		if maxlen is None or maxlen < 0:
			print("warning: read with no max length not implemented", stderr)
			maxlen = IRCConnection.MAX_LINE_LENGTH
		msg = self.mysock.recv(maxlen)
		if not msg: raise IOError("socket connection broken on recv")
		if type(msg) is bytes: msg = msg.decode(self.encoding)
		return msg

	def write(self, msg):
		if type(msg) is str: msg = msg.encode(self.encoding,'replace')
		if msg[-2:] != CRLF: msg += CRLF
		msg = msg.replace(b'\n\r', b'\r')
		msglen = len(msg)
		maxlen = IRCConnection.MAX_LINE_LENGTH
		if msglen > maxlen:
			print("warning: tried to write a line longer than %d.  truncating." % maxlen, stderr)
			msg = msg[:maxlen-len(CRLF)]+CRLF
			msglen = maxlen
		sent = 0
		while sent < msglen:
			tmp = self.mysock.send(msg[sent:])
			if tmp == 0: raise IOError("socket connection broken on send")
			sent += tmp
		return sent

	def close(self):
		try: self.write('QUIT')
		except IOError: pass
		try:
			self.myfile.close()
			self.mysock.close()
		except: pass

	# misc. filelike-isms
	def fileno(self): return self.mysock.fileno() # should this be myfile's?
	def seek(self, n): raise IOError("not a seekable object")
	def tell(self): raise IOError("not a seekable object")
	def truncate(self): raise IOError("not a seekable object")
	def readable(self): return True
	def writable(self): return True
	def seekable(self): return False
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_value, exc_traceback): self.close()
	# socketish too
	def send(self, msg): return self.write(msg)
	def recv(self, count): return self.read(count)

	# actual irc-related stuff
	def nick(self, nickname): # TODO: check if it didn't work and return error
		self.send('NICK %s' % nickname)
		self.mynick = nickname

	def join(self, channel):
		# open a pipe to send relevant lines to the channel object
		fname = '/tmp/pyirc-{}-{}-{}'.format(self.serveraddress, channel, self.mynick)
		try:
			os.mkfifo(fname)
		except OSError: pass # it may already have been made
		#open(fname, 'r').read() # prevent it from blocking later

		chanobj = IRCChannel(channel, self, fname)
		self.channels[channel] = (chanobj, fname)
		self.mypipetoeventloop.send((chanobj, fname, channel))
		return chanobj

	def pong(self, target):
		self.write('PONG %s' % target)

