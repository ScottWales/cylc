#!/bin/bash
# THIS FILE IS PART OF THE CYLC SUITE ENGINE.
# Copyright (C) 2008-2015 NIWA
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
#-------------------------------------------------------------------------------
# Test cylc job-poll, "loadleveler" jobs
. $(dirname $0)/test_header
SSH='ssh -oBatchMode=yes'
#-------------------------------------------------------------------------------

function get_fake_job_id() {
    if [[ -n ${FAKE_JOB_ID:-} ]]; then
        echo $FAKE_JOB_ID
        return
    fi
    local T_JOB_ID=$(get_real_job_id)
    llcancel $T_JOB_ID 1>/dev/null 2>&1
    while llq -f%id $T_JOB_ID | grep -q -e $T_JOB_ID; do
        sleep 2
    done
    echo $T_JOB_ID
}

function get_real_job_id() {
    cat >$TEST_NAME_BASE.ll <<'__LLSUBMIT__'
#!/bin/sh
#@output=$(jobid).out
#@error=$(jobid).err
#@notification=never
#@wall_clock_limit=120,60
#@class=serial
#@job_type=serial
__LLSUBMIT__
    while read; do
        if [[ -z $REPLY ]]; then
            continue
        fi
        KEY=${REPLY%% =*}
        if grep -q -e "#@$KEY=.*$" $TEST_NAME_BASE.ll; then
            sed -i "s/^#@$KEY=.*$/#@$REPLY/" $TEST_NAME_BASE.ll
        else
            echo "#@$REPLY" >>$TEST_NAME_BASE.ll
        fi
    done <<<"$T_DIRECTIVES_MORE"
    cat >>$TEST_NAME_BASE.ll <<'__LLSUBMIT__'
#@queue
sleep 60
__LLSUBMIT__
    local ID=$(llsubmit $TEST_NAME_BASE.ll 2>/dev/null \
        | awk -F'"' '/llsubmit: The job/ {print $2}')
    while ! (llq -f%id $ID | grep -q -e $ID); do
        sleep 2
    done
    echo $ID
}

function ssh_mkdtemp() {
    local T_HOST=$1
    $SSH $T_HOST python - <<'__PYTHON__'
import os
from tempfile import mkdtemp
print mkdtemp(dir=os.path.expanduser("~"), prefix="cylc-")
__PYTHON__
}
#-------------------------------------------------------------------------------
if ! ${IS_AT_T_HOST:-false}; then
    RC_ITEM='[test battery][batch systems]loadleveler]host'
    T_HOST=$(cylc get-global-config -i "${RC_ITEM}")
    if [[ -z $T_HOST ]]; then
        skip_all "\"${RC_ITEM}\" not defined"
    fi
    if [[ $T_HOST != 'localhost' ]]; then
        T_HOST_CYLC_DIR=$(ssh_mkdtemp $T_HOST)
        rsync -a --exclude=*.pyc $CYLC_DIR/* $T_HOST:$T_HOST_CYLC_DIR/
        $SSH $T_HOST bash -l <<__BASH__
echo "test" >$T_HOST_CYLC_DIR/VERSION
IS_AT_T_HOST=true \
CYLC_DIR=$T_HOST_CYLC_DIR \
PYTHONPATH=$T_HOST_CYLC_DIR/lib \
$T_HOST_CYLC_DIR/tests/cylc-job-poll/$TEST_NAME_BASE.t
__BASH__
        $SSH $T_HOST rm -rf $T_HOST_CYLC_DIR
        exit
    fi
fi
#-------------------------------------------------------------------------------
T_DIRECTIVES_MORE=
if ! ${HAS_READ_T_DIRECTIVES_MORE:-false}; then
    RC_ITEM='[test battery][batch systems]loadleveler][directives]'
    export T_DIRECTIVES_MORE=$(cylc get-global-config -i "${RC_ITEM}")
    export HAS_READ_T_DIRECTIVES_MORE=true
fi
FAKE_JOB_ID=$(get_fake_job_id)

set_test_number 12
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-null
# A non-existent status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
T_JOB_ID=$FAKE_JOB_ID
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 submission failed
__OUT__
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-submitted
# A non-existent status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
# Give it a real PID
REAL_JOB_ID=${REAL_JOB_ID:-$(get_real_job_id)}
T_JOB_ID=$REAL_JOB_ID
cat >"${T_ST_FILE}" <<__STATUS__
CYLC_BATCH_SYS_NAME=loadleveler
CYLC_BATCH_SYS_JOB_ID=${T_JOB_ID}
__STATUS__
sleep 1
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 submitted
__OUT__
llcancel $T_JOB_ID 2>/dev/null
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-started
# Give it a real PID
REAL_JOB_ID=${REAL_JOB_ID:-$(get_real_job_id)}
T_JOB_ID=$(get_real_job_id)
sleep 1
# Status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
T_INIT_TIME=$(date +%FT%H:%M:%S)
cat >"${T_ST_FILE}" <<__STATUS__
CYLC_BATCH_SYS_NAME=loadleveler
CYLC_BATCH_SYS_JOB_ID=${T_JOB_ID}
CYLC_JOB_PID=$T_JOB_ID
CYLC_JOB_INIT_TIME=$T_INIT_TIME
__STATUS__
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 started at $T_INIT_TIME
__OUT__
llcancel $T_JOB_ID 2>/dev/null
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-succeeded
T_JOB_ID=$FAKE_JOB_ID
# Status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
T_INIT_TIME=$(date +%FT%H:%M:%S)
T_EXIT_TIME=$(date +%FT%H:%M:%S)
cat >"${T_ST_FILE}" <<__STATUS__
CYLC_BATCH_SYS_NAME=loadleveler
CYLC_BATCH_SYS_JOB_ID=${T_JOB_ID}
CYLC_JOB_PID=$T_JOB_ID
CYLC_JOB_INIT_TIME=$T_INIT_TIME
CYLC_JOB_EXIT=SUCCEEDED
CYLC_JOB_EXIT_TIME=$T_EXIT_TIME
__STATUS__
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 succeeded at $T_EXIT_TIME
__OUT__
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-failed
T_JOB_ID=$FAKE_JOB_ID
# Status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
T_INIT_TIME=$(date +%FT%H:%M:%S)
T_EXIT_TIME=$(date +%FT%H:%M:%S)
cat >"${T_ST_FILE}" <<__STATUS__
CYLC_BATCH_SYS_NAME=loadleveler
CYLC_BATCH_SYS_JOB_ID=${T_JOB_ID}
CYLC_JOB_PID=$T_JOB_ID
CYLC_JOB_INIT_TIME=$T_INIT_TIME
CYLC_JOB_EXIT=ERR
CYLC_JOB_EXIT_TIME=$T_EXIT_TIME
__STATUS__
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 failed at $T_EXIT_TIME
__OUT__
#-------------------------------------------------------------------------------
TEST_NAME=$TEST_NAME_BASE-failed-bad
T_JOB_ID=$FAKE_JOB_ID
# Status file
T_ST_FILE="${PWD}/1/${TEST_NAME}/01/job.status"
mkdir -p "${PWD}/1/${TEST_NAME}/01"
T_INIT_TIME=$(date +%FT%H:%M:%S)
T_EXIT_TIME=$(date +%FT%H:%M:%S)
cat >"${T_ST_FILE}" <<__STATUS__
CYLC_BATCH_SYS_NAME=loadleveler
CYLC_BATCH_SYS_JOB_ID=${T_JOB_ID}
CYLC_JOB_PID=$T_JOB_ID
CYLC_JOB_INIT_TIME=$T_INIT_TIME
__STATUS__
run_ok $TEST_NAME cylc job-poll "${T_ST_FILE}"
cmp_ok $TEST_NAME.stdout <<__OUT__
polled ${TEST_NAME}.1 failed at unknown-time
__OUT__
#-------------------------------------------------------------------------------
exit
