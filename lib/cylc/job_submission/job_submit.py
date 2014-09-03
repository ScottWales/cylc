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
Job submission base class.

Writes a temporary "job file" that encapsulates the task runtime settings
(execution environment, command scripting, etc.) then submits it by the
chosen method on the chosen host (using passwordless ssh if not local).

Derived classes define the particular job submission method.
"""

import os
import sys
import stat
import socket

import cylc.flags
from cylc.job_submission.jobfile import JobFile
from cylc.cfgspec.globalcfg import GLOBAL_CFG
from cylc.owner import is_remote_user
from cylc.suite_host import is_remote_host
from cylc.envvar import expandvars
from cylc.command_env import pr_scripting_sl


class JobSubmit(object):
    """Base class for method-specific job script and submission command."""

    LOCAL_COMMAND_TEMPLATE = "(%(command)s)"

    # For remote jobs copy the job file to a temporary file and
    # then rename it, in case of a common filesystem (else this
    # is trouble: 'ssh HOST "cat > $DIR/foo.sh" < $DIR/foo.sh').
    REMOTE_COMMAND_TEMPLATE = (
        " '" +
        pr_scripting_sl +
        "; " +
        # Retry "mkdir" once to avoid race to create log/job/CYCLE/
        " (mkdir -p %(jobfile_dir)s || mkdir -p %(jobfile_dir)s)" +
        " && rm -f $(dirname %(jobfile_dir)s)/NN"
        " && ln -s $(basename %(jobfile_dir)s) $(dirname %(jobfile_dir)s)/NN"
        " && cat >%(jobfile_path)s.tmp" +
        " && mv %(jobfile_path)s.tmp %(jobfile_path)s" +
        " && chmod +x %(jobfile_path)s" +
        " && rm -f %(jobfile_path)s.status" +
        " && (%(command)s)" +
        "'")

    def __init__(self, task_id, suite, jobconfig, submit_num):

        self.jobconfig = jobconfig

        self.task_id = task_id
        self.suite = suite
        self.logfiles = jobconfig.get('log files')

        self.command = None
        self.job_submit_command_template = jobconfig.get('command template')

        common_job_log_path = jobconfig.get('common job log path')
        self.local_jobfile_path = jobconfig.get('local job file path')
        self.logfiles.add_path(self.local_jobfile_path)

        task_host = jobconfig.get('task host')
        task_owner = jobconfig.get('task owner')

        self.remote_shell_template = GLOBAL_CFG.get_host_item(
            'remote shell template', task_host, task_owner)

        if is_remote_host(task_host) or is_remote_user(task_owner):
            self.local = False
            if task_owner:
                self.task_owner = task_owner
            else:
                self.task_owner = None

            if task_host:
                self.task_host = task_host
            else:
                self.task_host = socket.gethostname()

            remote_job_log_dir = GLOBAL_CFG.get_derived_host_item(
                self.suite,
                'suite job log directory',
                self.task_host,
                self.task_owner)

            remote_jobfile_path = os.path.join(
                    remote_job_log_dir, common_job_log_path)

            # Remote log files
            self.stdout_file = remote_jobfile_path + ".out"
            self.stderr_file = remote_jobfile_path + ".err"

            # Used in command construction:
            self.jobfile_path = remote_jobfile_path

            # Record paths of remote log files for access by gui
            if True:
                # by ssh URL
                url_prefix = self.task_host
                if self.task_owner:
                    url_prefix = self.task_owner + "@" + url_prefix
                self.logfiles.add_path(url_prefix + ':' + self.stdout_file)
                self.logfiles.add_path(url_prefix + ':' + self.stderr_file)
            else:
                # CURRENTLY DISABLED:
                # If the remote and suite hosts see a common filesystem, or
                # if the remote task is really just a local task with a
                # different owner, we could just use local filesystem access.
                # But to use this: (a) special namespace config would be
                # required to indicate we have a common filesystem, and
                # (b) we'd need to consider how the log directory can be
                # specified (for example use of '$HOME' as for remote
                # task use would not work here as log file access is by
                # gui under the suite owner account.
                self.logfiles.add_path(self.stdout_file)
                self.logfiles.add_path(self.stderr_file)
        else:
            # LOCAL TASKS
            self.local = True
            self.task_owner = None
            # Used in command construction:
            self.jobfile_path = self.local_jobfile_path

            # Local stdout and stderr log file paths:
            self.stdout_file = self.local_jobfile_path + ".out"
            self.stderr_file = self.local_jobfile_path + ".err"

            # interpolate environment variables in extra logs
            for idx in range(0, len(self.logfiles.paths)):
                self.logfiles.paths[idx] = expandvars(self.logfiles.paths[idx])

            # Record paths of local log files for access by gui
            self.logfiles.add_path(self.stdout_file)
            self.logfiles.add_path(self.stderr_file)

        # set some defaults that can be overridden by derived classes
        self.jobconfig['directive prefix'] = None
        self.jobconfig['directive final'] = "# FINAL DIRECTIVE"
        self.jobconfig['directive connector'] = " "
        self.jobconfig['job vacation signal'] = None

        # overrideable methods
        self.set_directives()
        self.set_job_vacation_signal()
        self.set_scripting()
        self.set_environment()

    def set_directives(self):
        """OVERRIDE IN DERIVED JOB SUBMISSION CLASSES THAT USE DIRECTIVES

        (directives will be ignored if the prefix below is not overridden)

        Defaults set in task.py:
        self.jobconfig = {
         PREFIX: e.g. '#QSUB' (qsub), or '# @' (loadleveler)
             'directive prefix' : None,
         FINAL directive, WITH PREFIX, e.g. '# @ queue' for loadleveler
             'directive final' : '# FINAL_DIRECTIVE '
         CONNECTOR, e.g. ' = ' for loadleveler, ' ' for qsub
             'directive connector' :  " DIRECTIVE_CONNECTOR "
        }
        """
        pass

    def set_scripting(self):
        """Derived class can use this to modify pre/post-command scripting"""
        return

    def set_environment(self):
        """Derived classes can use this to modify task execution environment"""
        return

    def set_job_vacation_signal(self):
        """Derived class can set self.jobconfig['job vacation signal']."""
        return

    def construct_job_submit_command(self):
        """DERIVED CLASSES MUST OVERRIDE THIS METHOD to construct

        self.command, the command to submit the job script to
        run by the derived class job submission method.

        """
        raise NotImplementedError('ERROR: no job submission command defined!')

    def filter_output(self, out, err):
        """Filter the stdout/stderr from a job submission command.

        Derived classes should override this method.
        Used to prevent routine logging of irrelevant information.

        """
        return out, err

    def get_id(self, out, err):
        """Get the job submit ID from a job submission command output.

        Derived classes should override this method.

        """
        raise NotImplementedError()

    def write_jobscript(self):
        """ submit the task and return the process ID of the job
        submission sub-process, or None if a failure occurs."""

        job_file = JobFile(
            self.suite,
            self.jobfile_path,
            self.__class__.__name__,
            self.task_id,
            self.jobconfig)

        job_file.write(self.local_jobfile_path)
        # make it executable
        mode = (os.stat(self.local_jobfile_path).st_mode |
                stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        os.chmod(self.local_jobfile_path, mode)

    def get_job_submission_command(self, dry_run=False):
        """Construct the command to submit the jobfile to run"""
        # (Exceptions here caught in task_pool.py).
        self.construct_job_submit_command()
        if self.local:
            command = self.LOCAL_COMMAND_TEMPLATE % {
                "jobfile_path": self.jobfile_path,
                "command": self.command}
        else:
            command = self.REMOTE_COMMAND_TEMPLATE % {
                "jobfile_dir": os.path.dirname(self.jobfile_path),
                "jobfile_path": self.jobfile_path,
                "command": self.command}
            if self.task_owner:
                destination = self.task_owner + "@" + self.task_host
            else:
                destination = self.task_host
            command = self.remote_shell_template % destination + command

        # execute the local command to submit the job
        if dry_run:
            # this is needed by the 'cylc jobscript' command:
            print "JOB SCRIPT: " + self.local_jobfile_path
            print "THIS IS A DRY RUN. HERE'S HOW I WOULD SUBMIT THE TASK:"
            print 'SUBMIT:', command
            return None

        # Ensure old job's status files do not get left behind
        st_file_path = self.jobfile_path + ".status"
        if os.path.exists(st_file_path):
            os.unlink(st_file_path)

        if not self.local:
            # direct the local jobfile across the ssh tunnel via stdin
            command = command + ' < ' + self.local_jobfile_path

        return command
