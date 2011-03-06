#!/usr/bin/python

import errno, filecmp, glob, os.path, re, sys

def main(for_main, source_dir, dest_dirs):
    sections = []
    section = None
    keyword = None
    filename = None
    licence = None

    for line in open(os.path.join(source_dir, 'WHENCE')):
        if line.startswith('----------'):
            # Finish old section
            if licence:
                section['licence'] = licence
                licence = None

            # Start new section
            section = {
                'driver': None,
                'file': {},
                'licence': None
                }
            sections.append(section)
            continue

        if not section:
            # Skip header
            continue

        if line == '\n':
            # End of field; end of file fields
            keyword = None
            filename = None
            continue

        match = re.match(
            r'(Driver|File|Info|Licen[cs]e|Source|Version'
            r'|Original licen[cs]e info(?:rmation)?):\s*(.*)\n',
            line)
        if match:
            keyword, value = match.group(1, 2)
            if keyword == 'Driver':
                section['driver'] = value.split(' ')[0].lower()
            elif keyword == 'File':
                match = re.match(r'(\S+)\s+--\s+(.*)', value)
                if match:
                    filename = match.group(1)
                    section['file'][filename] = {'info': match.group(2)}
                else:
                    for filename in value.strip().split():
                        section['file'][filename] = {}
            elif keyword in ['Info', 'Version']:
                section['file'][filename]['version'] = value
            elif keyword == 'Source':
                section['file'][filename]['source'] = value
            else:
                licence = value
        elif licence is not None:
            licence = (licence + '\n' +
                       re.sub(r'^(?:[/ ]\*| \*/)?\s*(.*?)\s*$', r'\1', line))

    # Finish last section; delete if empty
    if not section['driver']:
        sections.pop()
    elif licence:
        section['licence'] = licence

    for section in sections:
        licence = section['licence']
        if re.search(r'^BSD\b'
                     r'|^GPLv2 or OpenIB\.org BSD\b'
                     r'|\bPermission\s+is\s+hereby\s+granted\s+for\s+the\s+'
                     r'distribution\s+of\s+this\s+firmware\s+(?:data|image)\b'
                     r'(?!\s+as\s+part\s+of)'
                     r'|\bRedistribution\s+and\s+use\s+in(?:\s+source\s+and)?'
                     r'\s+binary\s+forms\b'
                     r'|\bPermission\s+is\s+hereby\s+granted\b[^.]+\sto'
                     r'\s+deal\s+in\s+the\s+Software\s+without'
                     r'\s+restriction\b'
                     r'|\bredistributable\s+in\s+binary\s+form\b',
                     licence):
            # Suitable for main or non-free depending on source availability
            pass
        elif re.match(r'^(?:D|Red)istributable\b', licence):
            # Only suitable for non-free
            if for_main:
                continue
        elif re.match(r'^GPL(?:v2|\+)?\b', licence):
            # Only suitable for main; source must be available
            if not for_main:
                continue
        else:
            # Probably not distributable
            continue
        for filename, file_info in section['file'].iteritems():
            if (file_info.get('source') or filename.endswith('.cis') or
                not for_main):
                update_file(source_dir, dest_dirs, filename)

def update_file(source_dir, dest_dirs, filename):
    source_file = os.path.join(source_dir, filename)
    if not os.path.isfile(source_file):
        return
    for dest_dir in dest_dirs:
        for dest_file in ([os.path.join(dest_dir, filename)] +
                          glob.glob(os.path.join(dest_dir, filename + '-*'))):
            if os.path.isfile(dest_file):
                if not filecmp.cmp(source_file, dest_file, True):
                    print '%s: changed' % filename
                return
    print '%s: could be added' % filename

if __name__ == '__main__':
    for_main = False
    i = 1
    if len(sys.argv) > i and sys.argv[i] == '--main':
        for_main = True
        i += 1
    if len(sys.argv) < i + 2:
        print >>sys.stderr, '''\
Usage: %s [--main] <linux-firmware-dir> <dest-dir>...

Report changes or additions in linux-firmware.git that may be suitable
for inclusion in firmware-nonfree or linux-2.6.

For firmware-nonfree, specify the per-package subdirectories as
<dest-dir>...

For linux-2.6, use the '--main' option and specify the
debian/build/build-firmware/firmware directory as <dest-dir>.
''' % sys.argv[0]
        sys.exit(2)
    main(for_main, sys.argv[i], sys.argv[i + 1 :])
