#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Remote cache client that talks the binary Hot Rod protocol.
"""

__author__ = "Galder Zamarreño"
__copyright__ = "(C) 2010-2011 Red Hat Inc."

import socket
import struct
import exceptions

from infinispan import MAGIC, VERSION_10, \
  REQ_FMT, RES_H_LEN, RES_H_FMT, REQ_START_FMT, REQ_END_FMT, \
  PUT, GET, PUT_IF_ABSENT, REPLACE, REPLACE_IF, REMOVE, REMOVE_IF, \
  CONTAINS, GET_WITH_VERSION, CLEAR, STATS, PING, BULK_GET, \
  SEND, RECV

from unsigned import to_varint
from unsigned import from_varint

# TODO Control length of key/value/cache_name...etc
# TODO implement client intelligence = 2 (cluster formation interest)
# TODO implement client intelligence = 3 (hash distribution interest)

class RemoteCache(object):
  def __init__(self, host='127.0.0.1', port=11222, cache_name=''):
    self.s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    self.s.connect_ex((host, port))
    self.cache_name = cache_name

  def stop(self):
    self.s.close()

  def put(self, key, val, lifespan=0, max_idle=0, ret_prev=False):
    """ Associates the specified value with the specified key in the
    remote cache.

    Optionally, this function takes two parameters that control expiration this
    cache entry: lifespan indicates the number of seconds the cache entry
    should live in memory, and max idle time indicates the number of seconds
    since last time the cache entry entry has been touched after which the
    cache entry is considered up for expiration. If you pass 0 as parameter for
    lifespan, it means that the entry has no lifespan and can live forever.
    Same thing happens for max idle parameter.

    Unless returning previous value has been enabled, this operation returns
    True if the operation was successful, otherwise if there's a server
    error, a RemoteCacheError is thrown.

    When return previous has been enabled, this operation returns the previous
    value if exists. If the key was not associated with any previous value,
    it will return None. """
    return self._do_op(PUT[0],
                       key, val, lifespan, max_idle, ret_prev)

  def contains_key(self, key):
    """ Returns True if the key is present in the remote cache,
    otherwise, if the key is not present, it returns False. """
    return self._do_op(CONTAINS[0], key, '', 0, 0, False)

  def get(self, key):
    """ Returns the value associated with the given key in the remote cache.
    If the key is not present, this operation returns None. """
    return self._do_op(GET[0], key, '', 0, 0, False)

  def put_if_absent(self, key, val, lifespan=0, max_idle=0, ret_prev=False):
    """ Associates the specified value with the specified key in the
    remote cache, only of the key was absent.

    Optionally, this function takes two parameters that control expiration this
    cache entry: lifespan indicates the number of seconds the cache entry
    should live in memory, and max idle time indicates the number of seconds
    since last time the cache entry entry has been touched after which the
    cache entry is considered up for expiration. If you pass 0 as parameter for
    lifespan, it means that the entry has no lifespan and can live forever.
    Same thing happens for max idle parameter.

    Unless returning previous value has been enabled, this operation returns
    True if the operation was successful or False if the key was present
    and hence the operation could not succeed. If there was any server error,
    the function throws a RemoteCacheError indicating the cause for the
    failure.

    When return previous has been enabled and the operation was successful,
    the function returns a tuple with True as first element, and None as
    second element indicating that the previous value did not exist. If return
    previous has been enabled but the operation did not succed due to key
    being already present in the remote cache, this function returns a tuple
    with False as first element, and the current value associated with the key
    in the remote cache as second element. """
    return self._do_op(PUT_IF_ABSENT[0],
                       key, val, lifespan, max_idle, ret_prev)

  def replace(self, key, val, lifespan=0, max_idle=0, ret_prev=False):
    """ Replaces the value associated with a key only if the key is present
    in the remote cache.

    Optionally, this function takes two parameters that control expiration this
    cache entry: lifespan indicates the number of seconds the cache entry
    should live in memory, and max idle time indicates the number of seconds
    since last time the cache entry entry has been touched after which the
    cache entry is considered up for expiration. If you pass 0 as parameter for
    lifespan, it means that the entry has no lifespan and can live forever.
    Same thing happens for max idle parameter.

    Unless returning previous value has been enabled, this operation returns
    True if the operation was successful or False if the key not was present
    and hence the operation could not succeed. If there was any server error,
    the function throws a RemoteCacheError indicating the cause for the
    failure.

    When return previous has been enabled and the operation was successful,
    the function returns a tuple with True as first element, and the previous
    value associated with the key in the remote cache as second element.
    If return previous has been enabled but the operation did not succed due
    to key being missing in the remote cache, this function returns a tuple
    with False as first element, and None as second element."""
    return self._do_op(REPLACE[0], key, val, lifespan, max_idle, ret_prev)

  def get_versioned(self, key):
    """ Returns the version associated with this key in the remote cache and
    the value associated with the given key. The return is actually a tuple
    where the version is the first element and value is the second. If the
    key is not found, this method returns (0, None). """
    return self._do_op(GET_WITH_VERSION[0], key, '', 0, 0, False)

  def replace_with_version(self, key, val, version, lifespan=0, max_idle=0,
                           ret_prev=False):
    """ Replaces the value associated with a key with the value passed as
    parameter if, and only if, the version of the cache entry matches the
    version passed. This type of operation is generally used to guarantee that
    when the cache entry is to be replaced, nobody has changed the contents
    of the cache entry since last time it was read. Normally, the version that
    is passed comes from the output of calling get_versioned() operation.

    As with other similar operations, optional lifespan, max_idle parameters
    can be provided to control the lifetime of the cache entry.

    If return previous is disabled, this operations returns 1 (True) if the
    operation succeeded. Otherwise, if the operation failed due to key not
    being present, it returns 0 (False). Finally, if the operation failed due
    to the version numbers not matching meaning that the value associated with
    the key was modified in between retrieving the version and calling
    replica_with_version, then this function returns -1.

    If return previous is enabled, the function returns a tuple with the
    possible return values mentioned in previous paragraph as first element,
    and the previous value as second element. Clearly, if no previous value
    was present, the second element will contain None. """
    return self._do_op(REPLACE_IF[0],
                       key, val, lifespan, max_idle, ret_prev, version)

  def remove(self, key, ret_prev=False):
    """ Remove the key and the value associated to it from the remote cache.
    Unless returning previous value has been enabled, this operation returns
    True if the cache entry was removed in the remote cache, otherwise if the
    key is not present it returns False.

    When return previous has been enabled, this operation returns a tuple with
    the result of the operation as first element, and the previous value as
    second element if the key was present. If the key was not associated with
    any previous value, it will return None in the second parameter of the
    tuple. """
    return self._do_op(REMOVE[0], key, '', 0, 0, ret_prev)

  def remove_with_version(self, key, version, ret_prev=False):
    """ Removes the key and its associated value for the key passed as
    parameter if, and only if, the version of the cache entry matches the
    version passed. This type of operation is generally used to guarantee that
    when the cache entry is to be removed, nobody has changed the contents
    of the cache entry since last time it was read. Normally, the version that
    is passed comes from the output of calling get_versioned() operation.

    If return previous is disabled, this operations returns 1 (True) if the
    operation succeeded. Otherwise, if the operation failed due to key not
    being present, it returns 0 (False). Finally, if the operation failed due
    to the version numbers not matching meaning that the value associated with
    the key was modified in between retrieving the version and calling
    replica_with_version, then this function returns -1.

    If return previous is enabled, the function returns a tuple with the
    possible return values mentioned in previous paragraph as first element,
    and the previous value as second element. Clearly, if no previous value
    was present, the second element will contain None. """
    return self._do_op(REMOVE_IF[0], key, '', 0, 0, ret_prev, version)

  def clear(self):
    """ Clears the contents of the remote cache and has not return."""
    return self._do_op(CLEAR[0], '', '', 0, 0, False)

  def stats(self):
    """ Returns a dictionary containing statistics about the remote cache.
    The key of each cache entry represents the statistic name and the value
    represents the value of that stastic at the time the stats command was
    sent. Both keys and values are always represented as Strings. """
    return self._do_op(STATS[0], '', '', 0, 0, False)

  def ping(self):
    """ Pings the backend remote cache. If the remote cache is present and it's
    responding correctly, it returns True. Otherwise, if throws an error."""
    return self._do_op(PING[0], '', '', 0, 0, False)

  def bulk_get(self, count=0):
    """ Returns a a dictionay containing a quantity of cache entries stored
    in the remote cache. The count parameter controls the number of cache
    entries to return. If the count is 0, this operation returns all cache
    entries stored in the remote cache.

    Each cache entry maps directly to an entry in the dictionary. So, the key
    in the dictionary represents the key of the cache entry, and the value
    in the dictionary represents the value of the cache entry."""
    return self._do_op(BULK_GET[0], '', '', 0, 0, False, -1, count)

  def _do_op(self, op, key, val, lifespan, max_idle, ret_prev, version=-1, count=0):
    self._send_op(op, key, val, lifespan, max_idle, ret_prev, version, count)
    return self._get_resp(ret_prev)

  def _send_op(self, op, key, val, lifespan, max_idle, ret_prev, version, count):
    if ret_prev:
      flag = 0x01
    else:
      flag = 0

      # TODO: Make message id counter variable and atomic(?)
    if self.cache_name == '':
      msg = struct.pack(REQ_FMT, MAGIC[0], 0x01, VERSION_10, op,
                        0, flag, 0x01, 0, 0)
    else:
      start = struct.pack(REQ_START_FMT, MAGIC[0], 0x01, VERSION_10, op)
      end = struct.pack(REQ_END_FMT, flag, 0x01, 0, 0)
      msg = start + to_varint(len(self.cache_name)) + self.cache_name + end

    SEND[op](self.s, msg, key, val, lifespan, max_idle, version, count)

  def _get_resp(self, ret_prev):
    header = self._read_bytes(RES_H_LEN)
    magic, msg_id, op, st, topo_mark = struct.unpack(RES_H_FMT, header)
    assert (magic == MAGIC[1]), "Got magic: %d" % magic
    return RECV[op](self, st, ret_prev)

  def _read_ranged_bytes(self):
    return self._read_bytes(from_varint(self.s))

  def _read_bytes(self, expected_len):
    bytes = ""
    bytes_len = expected_len
    while len(bytes) < bytes_len:
      tmp = self.s.recv(bytes_len - len(bytes))
      if tmp == '':
        raise exceptions.EOFError("Got empty data (remote died?).")
      bytes += tmp
    assert len(bytes) == bytes_len
    if bytes == '':
      return None
    else:
      return bytes

  def _read_bounded_map(self):
    map = {}
    for i in range(0, from_varint(self.s)):
      key = self._read_ranged_bytes()
      map[key] = self._read_ranged_bytes()
    return map

  def _read_map(self):
    map = {}
    more = "" + self.s.recv(1)
    while (more == u'\1'):
      key = self._read_ranged_bytes()
      map[key] = self._read_ranged_bytes()
      more = self.s.recv(1)
    return map

  def _raise_error(self, status):
    error = self._read_ranged_bytes()
    raise RemoteCacheError(status, error)

class RemoteCacheError(Exception):
  """Error raised when a command fails."""

  def __init__(self, status, msg):
    super_msg = 'Hot Rod protocol error #' + `status`
    if msg: super_msg += ":  " + msg
    exceptions.Exception.__init__(self, super_msg)

    self.status = status
    self.msg = msg

  def __repr__(self):
    return "<Hot Rod protocol error #%d ``%s''>" % (self.status, self.msg)