#!/usr/bin/env python

# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2016 NIWA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""Task to cylc progress messaging."""
from __future__ import print_function

import os
import sys
from time import sleep
import traceback
from cylc.remote import remrun
from cylc.suite_env import CylcSuiteEnv, CylcSuiteEnvLoadError
from cylc.wallclock import get_current_time_string
import cylc.flags

from cylc.task_outputs import (
    TASK_OUTPUT_STARTED, TASK_OUTPUT_SUCCEEDED, TASK_OUTPUT_FAILED)


class TaskMessage(object):

    """Send task (job) output messages."""

    CYLC_JOB_PID = "CYLC_JOB_PID"
    CYLC_JOB_INIT_TIME = "CYLC_JOB_INIT_TIME"
    CYLC_JOB_EXIT = "CYLC_JOB_EXIT"
    CYLC_JOB_EXIT_TIME = "CYLC_JOB_EXIT_TIME"
    CYLC_MESSAGE = "CYLC_MESSAGE"

    FAIL_MESSAGE_PREFIX = "Task job script received signal "
    VACATION_MESSAGE_PREFIX = "Task job script vacated by signal "

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    PRIORITIES = (NORMAL, WARNING, CRITICAL)

    ATTRS = (
        ('suite', 'CYLC_SUITE_NAME', '(CYLC_SUITE_NAME)'),
        ('task_id', 'CYLC_TASK_ID', '(CYLC_TASK_ID)'),
        ('retry_seconds', 'CYLC_TASK_MSG_RETRY_INTVL',
         '(CYLC_TASK_MSG_RETRY_INTVL)'),
        ('max_tries', 'CYLC_TASK_MSG_MAX_TRIES', '(CYLC_TASK_MSG_MAX_TRIES)'),
        ('try_timeout', 'CYLC_TASK_MSG_TIMEOUT', '(CYLC_TASK_MSG_TIMEOUT)'),
        ('owner', 'CYLC_SUITE_OWNER', None),
        ('host', 'CYLC_SUITE_HOST', '(CYLC_SUITE_HOST)'),
        ('port', 'CYLC_SUITE_PORT', '(CYLC_SUITE_PORT)'),
    )

    def __init__(self, priority=NORMAL):
        if priority in self.PRIORITIES:
            self.priority = priority
        else:
            raise Exception('Illegal message priority ' + priority)

        # load the environment
        self.env_map = dict(os.environ)

        # set some instance variables
        self.suite = None
        self.task_id = None
        self.retry_seconds = None
        self.max_tries = None
        self.try_timeout = None
        self.owner = None
        self.host = None
        self.port = None
        for attr, key, default in self.ATTRS:
            value = self.env_map.get(key, default)
            setattr(self, attr, value)

        # conversions from string:
        if self.try_timeout == 'None':
            self.try_timeout = None
        try:
            self.retry_seconds = float(self.retry_seconds)
            self.max_tries = int(self.max_tries)
        except ValueError:
            pass

        # 'scheduler' or 'submit', (or 'raw' if job script run manually)
        self.mode = self.env_map.get('CYLC_MODE', 'raw')

        self.suite_run_dir = self.env_map.get('CYLC_SUITE_RUN_DIR', '.')

        self.utc = self.env_map.get('CYLC_UTC') == 'True'
        # Record the time the messaging system was called and append it
        # to the message, in case the message is delayed in some way.
        self.true_event_time = get_current_time_string(
            override_use_utc=self.utc)

        self.ssh_messaging = (
            self.env_map.get('CYLC_TASK_COMMS_METHOD') == 'ssh')

        self.polling = (
            self.env_map.get('CYLC_TASK_COMMS_METHOD') == 'poll')

        self.ssh_login_shell = (
            self.env_map.get('CYLC_TASK_SSH_LOGIN_SHELL') != 'False')

    def send(self, messages):
        """Send messages back to the suite."""
        self._update_job_status_file(messages)
        if self.mode != 'scheduler' or self.polling:
            # no suite to communicate with, just print to stdout.
            self._print_messages(messages)
            return

        if self.ssh_messaging and self._send_by_ssh():
            return

        self._send_by_pyro(messages)

    def _get_client(self):
        """Return the Pyro client."""
        from cylc.network.task_msgqueue import TaskMessageClient
        return TaskMessageClient(
            self.suite, self.task_id, self.owner, self.host,
            self.try_timeout, self.port)

    def _load_suite_contact_file(self):
        """Override CYLC_SUITE variables using the contact environment file.

        In case the suite was stopped and then restarted on another port.

        """
        try:
            suite_env = CylcSuiteEnv.load(self.suite, self.suite_run_dir)
        except CylcSuiteEnvLoadError:
            if cylc.flags.debug:
                traceback.print_exc()
        else:
            for key, attr_key in suite_env.ATTRS.items():
                self.env_map[key] = getattr(suite_env, attr_key)
        # set some instance variables
        for attr, key, default in (
                ('task_id', 'CYLC_TASK_ID', '(CYLC_TASK_ID)'),
                ('owner', 'CYLC_SUITE_OWNER', None),
                ('host', 'CYLC_SUITE_HOST', '(CYLC_SUITE_HOST)'),
                ('port', 'CYLC_SUITE_PORT', '(CYLC_SUITE_PORT)')):
            value = self.env_map.get(key, default)
            setattr(self, attr, value)

    def _print_messages(self, messages):
        """Print message to send."""
        prefix = 'cylc (%s - %s): ' % (self.mode, self.true_event_time)
        for message in messages:
            if self.priority == self.NORMAL:
                print(prefix + message)
            else:
                print("%s%s %s" % (
                    prefix, self.priority, message), file=sys.stderr)

    def _send_by_pyro(self, messages):
        """Send message by Pyro."""
        self._print_messages(messages)
        from Pyro.errors import NamingError
        sent = False
        i_try = 0
        while not sent and i_try < self.max_tries:
            i_try += 1
            try:
                # Get a proxy for the remote object and send the message.
                self._load_suite_contact_file()  # may change between tries
                client = self._get_client()
                for message in messages:
                    client.put(self.priority, message)
            except NamingError as exc:
                print(exc, file=sys.stderr)
                print("Send message: try %s of %s failed: %s" % (
                    i_try,
                    self.max_tries,
                    exc
                ))
                print("Task proxy removed from suite daemon? Aborting.")
                break
            except Exception as exc:
                print(exc, file=sys.stderr)
                print("Send message: try %s of %s failed: %s" % (
                    i_try,
                    self.max_tries,
                    exc
                ))
                if i_try >= self.max_tries:
                    break
                print("   retry in %s seconds, timeout is %s" % (
                    self.retry_seconds,
                    self.try_timeout
                ))
                sleep(self.retry_seconds)
            else:
                if i_try > 1:
                    print("Send message: try %s of %s succeeded" % (
                        i_try,
                        self.max_tries
                    ))
                sent = True
        if not sent:
            # issue a warning and let the task carry on
            print('WARNING: MESSAGE SEND FAILED', file=sys.stderr)

    def _send_by_ssh(self):
        """Send message via SSH."""
        self._load_suite_contact_file()

        # The suite definition specified that this task should
        # communicate back to the suite by means of using
        # non-interactive ssh to re-invoke the messaging command on the
        # suite host.

        # The remote_run() function expects command line options
        # to identify the target user and host names:
        sys.argv.append('--user=' + self.owner)
        sys.argv.append('--host=' + self.host)
        if cylc.flags.verbose:
            sys.argv.append('-v')

        if self.ssh_login_shell:
            sys.argv.append('--login')
        else:
            sys.argv.append('--no-login')

        # Some variables from the task execution environment are
        # also required by the re-invoked remote command: Note that
        # $CYLC_TASK_SSH_MESSAGING is not passed through so the
        # re-invoked command on the remote side will not end up in
        # this code block.
        env = {}
        for var in [
                'CYLC_MODE', 'CYLC_TASK_ID', 'CYLC_VERBOSE',
                'CYLC_SUITE_DEF_PATH_ON_SUITE_HOST',
                'CYLC_SUITE_RUN_DIR',
                'CYLC_SUITE_NAME', 'CYLC_SUITE_OWNER',
                'CYLC_SUITE_HOST', 'CYLC_SUITE_PORT', 'CYLC_UTC',
                'CYLC_TASK_MSG_MAX_TRIES', 'CYLC_TASK_MSG_TIMEOUT',
                'CYLC_TASK_MSG_RETRY_INTVL']:
            # (no exception handling here as these variables should
            # always be present in the task execution environment)
            env[var] = self.env_map.get(var, 'UNSET')

        # The path to cylc/bin on the remote end may be required:
        path = os.path.join(self.env_map['CYLC_DIR_ON_SUITE_HOST'], 'bin')

        # Return here if remote re-invocation occurred,
        # otherwise drop through to local Pyro messaging.
        # Note: do not sys.exit(0) here as the commands do, it
        # will cause messaging failures on the remote host.
        try:
            return remrun().execute(env=env, path=[path])
        except SystemExit:
            return

    def _update_job_status_file(self, messages):
        """Write messages to job status file."""
        job_log_name = os.getenv("CYLC_TASK_LOG_ROOT")
        job_status_file = None
        if job_log_name:
            try:
                job_status_file = open(job_log_name + ".status", "ab")
            except IOError as exc:
                if cylc.flags.debug:
                    print(exc, file=sys.stderr)
        for i, message in enumerate(messages):
            if job_status_file:
                if message == TASK_OUTPUT_STARTED:
                    job_status_file.write(
                        ("%s=%s\n" % (
                            self.CYLC_JOB_PID, os.getenv(self.CYLC_JOB_PID))) +
                        ("%s=%s\n" % (
                            self.CYLC_JOB_INIT_TIME, self.true_event_time)))
                elif message == TASK_OUTPUT_SUCCEEDED:
                    job_status_file.write(
                        ("%s=%s\n" % (self.CYLC_JOB_EXIT,
                                      TASK_OUTPUT_SUCCEEDED.upper())) +
                        ("%s=%s\n" % (
                            self.CYLC_JOB_EXIT_TIME, self.true_event_time)))
                elif message == TASK_OUTPUT_FAILED:
                    job_status_file.write("%s=%s\n" % (
                        self.CYLC_JOB_EXIT_TIME, self.true_event_time))
                elif message.startswith(self.FAIL_MESSAGE_PREFIX):
                    job_status_file.write("%s=%s\n" % (
                        self.CYLC_JOB_EXIT,
                        message.replace(self.FAIL_MESSAGE_PREFIX, "")))
                elif message.startswith(self.VACATION_MESSAGE_PREFIX):
                    # Job vacated, remove entries related to current job
                    job_status_file_name = job_status_file.name
                    job_status_file.close()
                    lines = []
                    for line in open(job_status_file_name):
                        if not line.startswith("CYLC_JOB_"):
                            lines.append(line)
                    job_status_file = open(job_status_file_name, "wb")
                    for line in lines:
                        job_status_file.write(line)
                    job_status_file.write("%s=%s|%s|%s\n" % (
                        self.CYLC_MESSAGE, self.true_event_time, self.priority,
                        message))
                else:
                    job_status_file.write("%s=%s|%s|%s\n" % (
                        self.CYLC_MESSAGE, self.true_event_time, self.priority,
                        message))
            messages[i] += ' at ' + self.true_event_time
        if job_status_file:
            try:
                job_status_file.close()
            except IOError as exc:
                if cylc.flags.debug:
                    print(exc, file=sys.stderr)
