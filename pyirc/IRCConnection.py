from multiprocessing import Pipe
from threading import Thread

import asyncore, asynchat
import os, socket, ssl
import threading
import logging

try:
	from IRCChannel import IRCChannel
except:
	from .IRCChannel import IRCChannel

CRLF = b'\r\n'

class IRCConnection(asynchat.async_chat):
	MAX_LINE_LENGTH = 512 # according to section 2.3 of RFC1459

	def __init__(self, nickname, server, port=6667, usessl=False, privkey=None):
		asynchat.async_chat.__init__(self)
		self.set_terminator(CRLF)
		self.encoding = 'utf8'
		self.channels = dict()
		self.users = set()
		self.inbuffer = b''

		self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
		self.set_reuse_addr()
		if usessl:
			self.del_channel()
			self.set_socket(ssl_wrap_socket(self.socket, keyfile=privkey))
		self.connect((server, port))
		self.serveraddress = server
		self.nick(nickname)
		self.write('USER %s 8 * :%s IRC Bot' % (nickname, nickname))
		self._starteventloop()

	def collect_incoming_data(self, data):
		self.inbuffer += data

	def found_terminator(self):
		self._process(self.inbuffer)
		logging.debug('line: ' + self.inbuffer)
		self.inbuffer = b''

	def _starteventloop(self):
		t = threading.Thread(target=asyncore.loop)
		t.daemon = True
		t.start()

	def _process(self, line):
		if line[0] != ':': return self._process_svr(line)
		return self._process_chan(line)

	def _process_chan(self, line):
		(header, x, data) = line[1:].partition(':')
		tmp = header.split(' ')
		(source, action, dest) = (tmp + [None, None])[:3]
		args = tmp[3:]
		(nick, x, host) = source.partition('!')

		logline = None
		if action == "PRIVMSG": logline = '<%s> %s\n' % (nick, data)
		elif action == "PART":  logline = '> %s left %s\n' % (nick, dest)
		elif action == "QUIT":  logline = '> %s quit\n' % (nick)
		elif action == "TOPIC": logline = '> %s set topic: %s\n' % (nick, data)
		elif action == "MODE" and len(args) >= 2:
			logline = '> %s set %s\n' % (nick, args[0])
			if args[1]: logline = logline[:-1] + (' to %s\n' % ' '.join(args[1:]))
		elif action == "JOIN":
			dest = data
			logline = '> %s joined %s\n' % (nick, dest)
		else: logline = '|%s\n' % line

		if logline and dest in self.channels:
			os.write(self.channels[dest][1], logline.encode(self.encoding,'replace'))

	def _process_svr(self, line):
		split = line.split(' ')
		if split[0] == "PING": self.pong(split[1])
		elif split[0] == "ERROR": logging.error("disconnected.")

	def _parse_modes(self, args):
		pass

	def readline(self):
		return NotImplemented # until we determine a good compromise
		msg = self.myfile.readline()
		if not msg: raise EOFError("reached EOF in readline")
		if msg[-1:] in CRLF: msg = msg[:-1]
		if msg[-1:] in CRLF: msg = msg[:-1]
		if type(msg) is bytes: msg = msg.decode(self.encoding,'replace')
		return msg

	def read(self, maxlen = None):
		return NotImplemented # until we determine a good compromise
		if maxlen is None or maxlen < 0:
			logging.warning("warning: read with no max length not implemented")
			maxlen = IRCConnection.MAX_LINE_LENGTH
		msg = self.mysock.recv(maxlen)
		if not msg: raise IOError("socket connection broken on recv")
		if type(msg) is bytes: msg = msg.decode(self.encoding,'replace')
		return msg

	def write(self, msg):
		msg = msg.rstrip(CRLF)
		if type(msg) is str: msg = msg.encode(self.encoding,'replace')
		msg += CRLF
		msglen = len(msg)
		maxlen = IRCConnection.MAX_LINE_LENGTH
		if msglen > maxlen:
			logging.warning("tried to write a line longer than %d.  truncating." % maxlen)
			msg = msg[:maxlen-len(CRLF)]+CRLF
			msglen = maxlen
		sent = 0
		self.push(msg)
		logging.debug('push: '+msg)
		return msglen

	def close(self):
		for c in self.channels:
			os.close(self.channels[c][1])
		return asynchat.async_chat.close(self)

	# misc. filelike-isms
	def fileno(self): return self._fileno
	def seek(self, n): raise IOError("not a seekable object")
	def tell(self): raise IOError("not a seekable object")
	def truncate(self): raise IOError("not a truncatable object")
	def seekable(self): return False
	# context
	def __enter__(self): return self
	def __exit__(self, exc_type, exc_value, exc_traceback): self.quit()

	# actual irc-related stuff
	def nick(self, nickname): # TODO: check if it didn't work and return error
		self.write('NICK %s' % nickname)
		self.mynick = nickname

	def join(self, channel):
		if channel not in self.channels:
			# open a pipe to send relevant lines to the channel object
			readpipe, writepipe = os.pipe()
			chanobj = IRCChannel(channel, self, readpipe)
			self.channels[channel] = (chanobj, writepipe)
		return self.channels[channel][0]

	def pong(self, target):
		self.write('PONG %s' % target)

	def quit(self):
		self.write('QUIT')
		self.close_when_done()

