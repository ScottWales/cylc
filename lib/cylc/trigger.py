#!/usr/bin/env python

#C: THIS FILE IS PART OF THE CYLC SUITE ENGINE.
#C: Copyright (C) 2008-2014 Hilary Oliver, NIWA
#C:
#C: This program is free software: you can redistribute it and/or modify
#C: it under the terms of the GNU General Public License as published by
#C: the Free Software Foundation, either version 3 of the License, or
#C: (at your option) any later version.
#C:
#C: This program is distributed in the hope that it will be useful,
#C: but WITHOUT ANY WARRANTY; without even the implied warranty of
#C: MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#C: GNU General Public License for more details.
#C:
#C: You should have received a copy of the GNU General Public License
#C: along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re

import cylc.TaskID
from cylc.cycling.loader import (
    get_interval, get_interval_cls, get_point_relative)
from cylc.task_state import task_state
from cylc.task_state import TaskStateError


BACK_COMPAT_MSG_RE = re.compile('^(.*)\[\s*T\s*(([+-])\s*(\d+))?\s*\](.*)$')
MSG_RE = re.compile('^(.*)\[\s*(([+-])?\s*(.*))?\s*\](.*)$')


class TriggerError( Exception ):
    def __init__( self, msg ):
        self.msg = msg
    def __str__( self ):
        return repr( self.msg )

class trigger(object):
    """
Task triggers, used to generate prerequisite messages.

#(a) graph offsets:
  # trigger bar if foo at -P1D succeeded:
    graph = foo[-P1D] => bar
  # trigger bar if foo at -P1D reported message output:
    graph = foo[-P1D]:x => bar

#(b) output message offsets:
[runtime]
   [[foo]]
      [[[outputs]]]
         x = "file X uploaded for [P1D]"
         y = "file Y uploaded for []"
    """

    def __init__(
            self, task_name, qualifier=None, graph_offset_string=None,
            cycle_point=None, suicide=False, outputs={}, base_interval=None):

        self.task_name = task_name
        self.suicide = suicide
        self.graph_offset_string = graph_offset_string
        self.cycle_point = cycle_point

        self.message = None
        self.message_offset = None
        self.builtin = None
        qualifier = qualifier or "succeeded"

        # Built-in trigger?
        try:
            self.builtin = task_state.get_legal_trigger_state(qualifier)
        except TaskStateError:
            pass
        else:
            return

        # Message trigger?
        try:
            msg = outputs[qualifier]
        except KeyError:
            raise TriggerError, (
                    "ERROR: undefined trigger qualifier: %s:%s" % (
                        task_name, qualifier)
            )
        else:
            # Back compat for [T+n] in message string.
            m = re.match(BACK_COMPAT_MSG_RE, msg)
            msg_offset = None
            if m:
                prefix, signed_offset, sign, offset, suffix = m.groups()
                if offset:
                    msg_offset = base_interval.get_inferred_child(signed_offset)
                else:
                    msg_offset = get_interval_cls().get_null()
            else:
                n = re.match(MSG_RE, msg)
                if n:
                    prefix, signed_offset, sign, offset, suffix = n.groups()
                    if offset:
                        msg_offset = get_interval(signed_offset)
                    else:
                        msg_offset = get_interval_cls().get_null()
                else:
                    raise TriggerError, (
                            "ERROR: undefined trigger qualifier: %s:%s" % (
                                task_name, qualifier)
                    )
            self.message = msg
            self.message_offset = msg_offset

    def is_standard(self):
        return self.builtin is not None

    def get(self, point):
        """Return a prerequisite string and the relevant point."""
        if self.message:
            # Message trigger
            preq = self.message
            if self.cycle_point:
                point = self.cycle_point
            else:
                if self.message_offset:
                    point += self.message_offset
                if self.graph_offset_string:
                    point = get_point_relative(
                            self.graph_offset_string, point)
            preq = re.sub( '\[.*\]', str(point), preq )
        else:
            # Built-in trigger
            if self.cycle_point:
                point = self.cycle_point
            elif self.graph_offset_string:
                point = get_point_relative(
                    self.graph_offset_string, point)
            preq = cylc.TaskID.get(self.task_name, str(point)) + ' ' + self.builtin
        return preq, point
