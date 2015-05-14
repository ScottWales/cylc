#!/bin/bash
# vim:filetype=sh
# Copyright (C) 2008-2015 NIWA
# Copyright (C) 2015 ARC Centre of Excellence for Climate Systems Science
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
#------------------------------------------------------------------------------

source "$(dirname "$0")/test_header"

set_test_number 4

for state in success fail; do
    install_suite "$TEST_NAME_BASE" "${TEST_NAME_BASE}:${state}"
    run_ok "${TEST_NAME_BASE}:${state}:validate" cylc validate "${SUITE_NAME}"
    suite_run_ok "${TEST_NAME_BASE}:${state}:run" cylc run --reference-test --debug "${SUITE_NAME}"
    purge_suite "${SUITE_NAME}"
done

