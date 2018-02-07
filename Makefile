# This file implements the GNOME Build API:
# http://people.gnome.org/~walters/docs/build-api.txt

FIRMWAREDIR = /lib/firmware

all:

check:
	./check_whence.py

install:
	mkdir -p $(DESTDIR)$(FIRMWAREDIR)
	cp -r * $(DESTDIR)$(FIRMWAREDIR)
	rm -rf $(DESTDIR)$(FIRMWAREDIR)/usbdux
	find $(DESTDIR)$(FIRMWAREDIR) \( -name 'WHENCE' -or -name 'LICENSE.*' -or \
		-name 'LICENCE.*' \) -exec rm -- {} \;
