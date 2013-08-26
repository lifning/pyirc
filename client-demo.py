# File: asynchat-example-1.py

from pyirc import IRCConnection
from select import select
import sys

with IRCConnection('pyirc-demo', 'irc.example.com').join('#mychannel') as ch:
	while True:
		ready = select([ch, sys.stdin], [], [])[0]
		if ch in ready:
			print ch.readline().rstrip('\r\n')
		if sys.stdin in ready:
			ch.write(raw_input())

