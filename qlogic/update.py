#!/usr/bin/env python

import os, re
from ftplib import FTP

ftp = FTP('ftp.qlogic.com')
ftp.login()
ftp.cwd('/outgoing/linux/firmware')

files = {}

def check(line):
    match = re.match(r'^(?P<file>ql\d{4}_fw.bin) -- (?P<version>\d\.\d\d\.\d\d)', line)
    if match is None:
        return
    files[match.group('file')] = match.group('version')

ftp.retrlines('RETR CURRENT_VERSIONS', check)

new_files = []

for f, version in files.iteritems():
    f_out = '%s-%s' % (f, version)
    if not os.path.exists(f_out):
        fd = file(f_out, 'w')
        ftp.retrbinary('RETR %s' % f, fd.write)
        fd.close()
        del fd
        print "Retrieved %s" % f_out
        new_files.append(f_out)

if new_files:
    print "New files:", ' '.join(new_files)
else:
    print "Nothing done."
