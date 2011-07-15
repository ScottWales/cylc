#!/bin/bash

set -e

usage() {
    echo "USAGE: update-from-release.sh CYLC_DIR"
    echo "Replace PDF and HTML documentation with the same from"
    echo "the specified new release."
}

if [[ $# != 1 ]]; then
    usage
    exit 1
fi

RELDIR=$1

if [[ ! -x $RELDIR/bin/cylc ]]; then
    usage
    exit 1
fi

rm -f cug-html*.html cug-html.css
rm -f CylcUserGuide.pdf
rm changelog.txt

# There may be extra screenshots in the web site graphics, so we don't 
# remove and update these automatically.

cp $RELDIR/doc/cug-html* .
cp $RELDIR/doc/CylcUserGuide.pdf .
cp $RELDIR/changelog.txt .
