#!/bin/sh -e

wget -r -nH -N --cut-dirs=3 -P qlogic-fw ftp://ftp.qlogic.com/outgoing/linux/firmware/
