# THIS FILE IS PART OF THE CYLC WORKFLOW ENGINE.
# Copyright (C) NIWA & British Crown (Met Office) & Contributors.
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

"""Test cylc install."""

import pytest
from pathlib import Path

from .test_scan import init_flows

from cylc.flow.async_util import pipe
from cylc.flow.scripts import scan
from cylc.flow.workflow_files import WorkflowFiles
from cylc.flow.scripts.install import (
    InstallOptions,
    install_cli
)


SRV_DIR = Path(WorkflowFiles.Service.DIRNAME)
CONTACT = Path(WorkflowFiles.Service.CONTACT)
RUN_N = Path(WorkflowFiles.RUN_N)
INSTALL = Path(WorkflowFiles.Install.DIRNAME)


@pytest.fixture()
def src_run_dirs(mock_glbl_cfg, monkeypatch, tmp_path: Path):
    """Create some workflow source and run dirs for testing.

    Source dirs:
      <tmp-src>/w1
      <tmp-src>/w2

    Run dir:
      <tmp-run>/w1/run1

    """
    tmp_src_path = tmp_path / 'cylc-src'
    tmp_run_path = tmp_path / 'cylc-run'
    tmp_src_path.mkdir()
    tmp_run_path.mkdir()

    init_flows(
        tmp_run_path=tmp_run_path,
        running=('w1/run1',),
        tmp_src_path=tmp_src_path,
        src=('w1', 'w2')
    )
    mock_glbl_cfg(
        'cylc.flow.workflow_files.glbl_cfg',
        f'''
            [install]
                source dirs = {tmp_src_path}
        '''
    )
    monkeypatch.setattr('cylc.flow.pathutil._CYLC_RUN_DIR', tmp_run_path)

    return tmp_src_path, tmp_run_path


INSTALLED_MSG = "INSTALLED {wfrun} from"
WF_ACTIVE_MSG = '1 run of "{wf}" is already active:'
BAD_CONTACT_MSG = "Bad contact file:"


def test_install_scan_no_ping(src_run_dirs, capsys, caplog):
    """At install, running intances should be reported.

    Ping = False case: don't query schedulers.
    """

    opts = InstallOptions()
    opts.no_ping = True

    install_cli(opts, reg='w1')
    out = capsys.readouterr().out
    assert INSTALLED_MSG.format(wfrun='w1/run2') in out
    assert WF_ACTIVE_MSG.format(wf='w1') in out
    assert f"{BAD_CONTACT_MSG} w1/run1" in caplog.text

    install_cli(opts, reg='w2')
    out = capsys.readouterr().out
    assert WF_ACTIVE_MSG.format(wf='w2') not in out
    assert INSTALLED_MSG.format(wfrun='w2/run1') in out


def test_install_scan_ping(src_run_dirs, capsys, caplog):
    """At install, running intances should be reported.

    Ping = True case: but mock scan's scheduler query method.
    """

    @pipe
    async def mock_graphql_query(flow, fields, filters=None):
        """Mock cylc.flow.network.scan.graphql_query."""
        flow.update({"status": "running"})
        return flow

    scan.graphql_query = mock_graphql_query

    opts = InstallOptions()
    opts.no_ping = False

    install_cli(opts, reg='w1')
    out = capsys.readouterr().out
    assert INSTALLED_MSG.format(wfrun='w1/run2') in out
    assert WF_ACTIVE_MSG.format(wf='w1') in out
    assert scan.FLOW_STATE_SYMBOLS["running"] in out
    assert f"{BAD_CONTACT_MSG} w1/run1" in caplog.text

    install_cli(opts, reg='w2')
    out = capsys.readouterr().out
    assert INSTALLED_MSG.format(wfrun='w2/run1') in out
    assert WF_ACTIVE_MSG.format(wf='w2') not in out
