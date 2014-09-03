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
"""
Integer cycling by point, interval, and sequence classes.
"""

import re

from cylc.cycling import (
    PointBase, IntervalBase, SequenceBase, PointParsingError)


CYCLER_TYPE_INTEGER = "integer"
CYCLER_TYPE_SORT_KEY_INTEGER = "a"

# TODO - abbreviated integer recurrences?

# INTEGER RECURRENCE REGEXES
#
# Unlike ISO8601 time points we can't tell if an integer point is absolute, or
# relative to some context, so a special character 'c' is used to signify that
# context is required. '?' can be used for the period in one-off (no-repeat)
# expressions, otherwise an arbitrary given value will be ignored.
#
# 1) REPEAT/START/PERIOD: R[n]/[c]i/Pi
# missing n means repeat indefinitely
FULL_RE_1 = re.compile('R(\d+)?/(c)?([+-]?\d+)/P(\d+|\?)')
#
# 2) REPEAT/START/STOP: Rn/[c]i/[c]i
# n required: n times between START and STOP
# (R1 means just START, R2 means START and STOP)
FULL_RE_2 = re.compile('R(\d+)/(c)?([+-]?\d+)/(c)?(\d+)')
#
# 3) REPEAT/PERIOD/STOP: Rn/Pi/[c]i
# (n required to count back from stop)
FULL_RE_3 = re.compile('R(\d+)?/P(\d+|\?)/(c)?([+-]?\d+)')


class IntegerPoint(PointBase):

    """A single point in an integer sequence."""

    TYPE = CYCLER_TYPE_INTEGER
    TYPE_SORT_KEY = CYCLER_TYPE_SORT_KEY_INTEGER

    def __init__(self, value):
        if isinstance(value, int):
            value = str(value)
        super(IntegerPoint, self).__init__(value)

    def add(self, other):
        """Add other.value to self.value as integers."""
        return IntegerPoint(int(self) + int(other))

    def cmp_(self, other):
        """Compare self.value to self.other as integers with 'cmp'."""
        return cmp(int(self), int(other))

    def sub(self, other):
        """Subtract other.value from self.value as integers."""
        if isinstance(other, IntegerPoint):
            return IntegerInterval(int(self) - int(other))
        return IntegerPoint(int(self) - int(other))

    def standardise(self):
        """Format self.value into a standard representation and check it."""
        try:
            self.value = str(int(self))
        except (TypeError, ValueError):
            raise PointParsingError(type(self), self.value)
        return self

    def __int__(self):
        # Provide a nice way to use the string self.value in calculations.
        return int(self.value)


class IntegerInterval(IntervalBase):

    """The interval between points in an integer sequence."""

    TYPE = CYCLER_TYPE_INTEGER
    TYPE_SORT_KEY = CYCLER_TYPE_SORT_KEY_INTEGER

    @classmethod
    def get_null(cls):
        """Return a null interval."""
        return IntegerInterval("P0")

    def get_inferred_child(self, string):
        """For a given string, infer the offset given my instance units."""
        return IntegerInterval(string)

    def __init__(self, value):
        if isinstance(value, basestring) and "P" not in value:
            value = int(value)
        if isinstance(value, int):
            if value < 0:
                value = "-P" + str(abs(value))
            else:
                value = "P" + str(value)
        super(IntegerInterval, self).__init__(value)

    def add(self, other):
        """Add other to self as integers (point or interval)."""
        if isinstance(other, IntegerInterval):
            return IntegerInterval(int(self) + int(other))
        return IntegerPoint(int(self) + int(other))

    def cmp_(self, other):
        """Compare other to self as integers."""
        return cmp(int(self), int(other))

    def sub(self, other):
        """Subtract other from self as integers."""
        return IntegerInterval(int(self) - int(other))

    def __abs__(self):
        # Return an interval with absolute values for all properties.
        return IntegerInterval(abs(int(self)))

    def __int__(self):
        # Provide a nice way to use the string self.value in calculations.
        return int(self.value.replace("P", ""))

    def __mul__(self, factor):
        # Return an interval with all properties multiplied by factor.
        return IntegerInterval(int(self) * factor)

    def __nonzero__(self):
        # Return True if the interval has any non-zero properties.
        return bool(int(self))


class IntegerSequence(SequenceBase):
    """Integer points at a regular interval."""

    TYPE = CYCLER_TYPE_INTEGER
    TYPE_SORT_KEY = CYCLER_TYPE_SORT_KEY_INTEGER

    @classmethod
    def get_async_expr(cls, start_point=0):
        """Express a one-off sequence at the initial cycle point."""
        return 'R1/c' + str(start_point) + '/P1'

    def __init__(self, dep_section, p_context_start, p_context_stop=None):
        """Parse state (start, stop, interval) from a graph section heading.
        The start and stop points are always on-sequence, context points
        might not be. If computed start and stop points are out of bounds,
        they will be set to None. Context is used only initially to define
        the sequence bounds."""

        # start context always exists
        self.p_context_start = IntegerPoint(p_context_start)
        # stop context may exist
        if p_context_stop:
            self.p_context_stop = IntegerPoint(p_context_stop)
        else:
            self.p_context_stop = None

        # state variables: start, stop, and step
        self.p_start = None
        self.p_stop = None
        self.i_step = None

        # offset must be stored to compute the runahead limit
        self.i_offset = IntegerInterval('0')

        # 1) REPEAT/START/PERIOD: R([n])/([c])(i)/P(i)
        results = FULL_RE_1.match(dep_section)
        if results:
            reps, context, start, step = results.groups()
            if context == 'c':
                self.p_start = self.p_context_start + IntegerPoint(start)
            else:
                self.p_start = IntegerPoint(start)
            if step == '?' or reps and int(reps) <= 1:
                # one-off
                self.i_step = None
                self.p_stop = self.p_start
            else:
                self.i_step = IntegerInterval(step)
                if reps:
                    self.p_stop = self.p_start + self.i_step * (int(reps) - 1)
                elif self.p_context_stop:
                    # stop at the point <= self.p_context_stop
                    # use p_start as an on-sequence reference
                    remainder = (int(self.p_context_stop - self.p_start) %
                                 int(self.i_step))
                    self.p_stop = self.p_context_stop - IntegerInterval(
                        remainder)
        else:
            # 2) REPEAT/START/STOP: R(n)/([c])(i)/([c])(i)
            results = FULL_RE_2.match(dep_section)
            # results fails if n in R(n) is not given
            if results:
                reps, context1, start, context2, stop = results.groups()
                if context1 == 'c':
                    self.p_start = (
                        self.p_context_start + IntegerPoint(start))
                else:
                    self.p_start = IntegerPoint(start)
                if int(reps) == 1:
                    # one-off: ignore stop point
                    self.i_step = None
                    self.p_stop = self.p_start
                else:
                    if context2 == 'c':
                        if self.p_context_stop:
                            self.p_stop = (
                                self.p_context_stop + IntegerPoint(stop))
                        else:
                            raise Exception(
                                "ERROR: stop or stop context required with " +
                                "regex 2"
                            )
                    else:
                        self.p_stop = IntegerPoint(stop)
                    self.i_step = IntegerInterval(
                        int(self.p_stop - self.p_start) / (int(reps) - 1)
                    )
            else:
                # 3) REPEAT/PERIOD/STOP: R(n)/P(i)/([c])i
                results = FULL_RE_3.match(dep_section)
                # results fails if n in R(n) is not given
                if results:
                    reps, step, context, stop = results.groups()
                    if context == 'c':
                        if self.p_context_stop:
                            self.p_stop = (
                                self.p_context_stop + IntegerPoint(stop))
                        else:
                            raise Exception(
                                "ERROR: stop or stop context required with " +
                                "regex 2"
                            )
                    else:
                        self.p_stop = IntegerPoint(stop)
                    if int(reps) <= 1:
                        # one-off
                        self.p_start = self.p_stop
                        self.i_step = None
                    else:
                        self.i_step = IntegerInterval(step)
                        self.p_start = (
                            self.p_stop - self.i_step * (int(reps) - 1))

                else:
                    raise Exception(
                        "ERROR, bad integer cycling format: %s" % dep_section)

        if self.i_step and self.i_step < IntegerInterval.get_null():
            # (TODO - this should be easy to handle but needs testing)
            raise Exception(
                "ERROR, negative intervals not supported yet: %s" %
                self.i_step
            )

        if self.i_step and self.p_start < self.p_context_start:
            # start from first point >= context start
            remainder = (
                int(self.p_context_start - self.p_start) % int(self.i_step))
            self.p_start = self.p_context_start + IntegerInterval(remainder)
            # if i_step is None here, points will just be None (out of bounds)

        if (self.i_step and self.p_stop and self.p_context_stop and
                self.p_stop > self.p_context_stop):
            # stop at first point <= context stop
            remainder = (
                int(self.p_context_stop - self.p_start) % int(self.i_step))
            self.p_stop = (
                self.p_context_stop - self.i_step +
                IntegerInterval(remainder)
            )
            # if i_step is None here, points will just be None (out of bounds)

    def get_interval(self):
        """Return the cycling interval of this sequence."""
        # interval may be None (a one-off sequence)
        return self.i_step

    def get_offset(self):
        """Deprecated: return the offset used for this sequence."""
        return self.i_offset

    def set_offset(self, i_offset):
        """Deprecated: alter state to offset the entire sequence."""
        if not i_offset.value:
            # no offset
            return
        if not self.i_step:
            # this is a one-off sequence
            self.p_start += i_offset
            self.p_stop += i_offset
            if self.p_start < self.p_context_start:
                self.p_start = self.p_stop = None
            return
        if not int(i_offset) % int(self.i_step):
            # offset is a multiple of step
            return
        # shift to 0 < offset < interval
        i_offset = IntegerInterval(int(i_offset) % int(self.i_step))
        self.i_offset = i_offset
        self.p_start += i_offset  # can be negative
        if self.p_start < self.p_context_start:
            self.p_start += self.i_step
        self.p_stop += i_offset
        if self.p_stop > self.p_context_stop:
            self.p_stop -= self.i_step

    def is_on_sequence(self, point):
        """Is point on-sequence, disregarding bounds?"""
        if self.i_step:
            return int(point - self.p_start) % int(self.i_step) == 0
        else:
            return point == self.p_start

    def _get_point_in_bounds(self, point):
        """Return point, or None if out of bounds."""
        if point >= self.p_start and (
                self.p_stop is None or point <= self.p_stop):
            return point
        else:
            return None

    def is_valid(self, point):
        """Is point on-sequence and in-bounds?"""
        return self.is_on_sequence(point) and \
            point >= self.p_start and point <= self.p_stop

    def get_prev_point(self, point):
        """Return the previous point < point, or None if out of bounds."""
        # Only used in computing special sequential task prerequisites.
        if not self.i_step:
            # implies a one-off task was declared sequential
            # TODO - check this results in sensible behaviour
            return None
        i = int(point - self.p_start) % int(self.i_step)
        if i:
            prev_point = point - IntegerInterval(str(i))
        else:
            prev_point = point - self.i_step
        return self._get_point_in_bounds(prev_point)

    def get_nearest_prev_point(self, point):
        """Return the largest point < some arbitrary point."""
        if self.is_on_sequence(point):
            return self.get_prev_point(point)
        sequence_point = self._get_point_in_bounds(self.p_start)
        prev_point = None
        while sequence_point is not None:
            if sequence_point > point:
                # Technically, >=, but we already test for this above.
                break
            prev_point = sequence_point
            sequence_point = self.get_next_point(sequence_point)
        return prev_point

    def get_next_point(self, point):
        """Return the next point > point, or None if out of bounds."""
        if not self.i_step:
            # this is a one-off sequence
            # TODO - is this needed? if so, check it gives sensible behaviour
            if point < self.p_start:
                return self.p_start
            else:
                return None
        i = int(point - self.p_start) % int(self.i_step)
        next_point = point + self.i_step - IntegerInterval(i)
        return self._get_point_in_bounds(next_point)

    def get_next_point_on_sequence(self, point):
        """Return the next point > point assuming that point is on-sequence,
        or None if out of bounds."""
        # This can be used when working with a single sequence.
        if not self.i_step:
            return None
        next_point = point + self.i_step
        return self._get_point_in_bounds(next_point)

    def get_first_point(self, point):
        """Return the first point >= to point, or None if out of bounds."""
        # Used to find the first point >= suite initial cycle point.
        if point <= self.p_start:
            point = self._get_point_in_bounds(self.p_start)
        elif self.is_on_sequence(point):
            point = self._get_point_in_bounds(point)
        else:
            point = self.get_next_point(point)
        return point

    def get_start_point( self ):
        """Return the first point in this sequence, or None."""
        return self.p_start

    def get_stop_point(self):
        """Return the last point in this sequence, or None if unbounded."""
        return self.p_stop

    def __eq__(self, other):
        # Return True if other (sequence) is equal to self.
        if self.i_step and not other.i_step or \
                not self.i_step and other.i_step:
            return False
        else:
            return self.i_step == other.i_step and \
                self.p_start == other.p_start and \
                self.p_stop == other.p_stop


def init_from_cfg(cfg):
    """Placeholder function required by all cycling modules."""
    pass

def get_point_relative(offset_string, base_point):
    """Create a point from offset_string applied to base_point."""
    # This is fine so long as it is called deliberately
    # (absolute and relative integers look the same).
    return base_point + IntegerInterval(offset_string)

def test():
    """Run some simple tests for integer cycling."""
    sequence = IntegerSequence('R/1/P3', 1, 10)
    #sequence = IntegerSequence('R/c2/P2', 1, 10)
    #sequence = IntegerSequence('R2/c2/P2', 1, 10)
    #sequence = IntegerSequence('R2/c4/c6', 1, 10)
    #sequence = IntegerSequence('R2/P2/c6', 1, 10)

    sequence.set_offset(IntegerInterval('4'))

    start = sequence.p_start
    stop = sequence.p_stop

    point = start
    while point and stop and point <= stop:
        print ' + ' + str(point)
        point = sequence.get_next_point(point)
    print

    point = stop
    while point and start and point >= start:
        print ' + ' + str(point)
        point = sequence.get_prev_point(point)

    print
    sequence1 = IntegerSequence('R/c1/P1', 1, 10)
    sequence2 = IntegerSequence('R/c1/P1', 1, 10)
    print sequence1 == sequence2
    sequence2.set_offset(IntegerInterval('-2'))
    print sequence1 == sequence2


if __name__ == '__main__':
    test()
