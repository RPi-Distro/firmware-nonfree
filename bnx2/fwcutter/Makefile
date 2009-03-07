test :=
ifdef KERNEL_SOURCE
test += source
endif
ifdef KERNEL_VERSION
test += version
endif

ifeq "$(test)" " source version"
CFLAGS += -I$(KERNEL_SOURCE)/include -I$(KERNEL_SOURCE)/drivers/net
CFLAGS += --std=gnu99
LDFLAGS += -lz

all: bnx2_fwcutter_$(KERNEL_VERSION)

bnx2_fwcutter_$(KERNEL_VERSION): bnx2_fwcutter_$(KERNEL_VERSION).c bnx2_fwcutter_$(KERNEL_VERSION).h bnx2_fwcutter.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<

bnx2_fwcutter_$(KERNEL_VERSION).h: $(KERNEL_SOURCE)/drivers/net/bnx2.h
	sed "/^#define BNX2.*[^\\]$$/p; /^#define BNX2.*\\$$/,/[^\\]$$/p; d" $^ > $@
else
all:
	$(error Please define KERNEL_SOURCE and KERNEL_VERSION)
endif

clean: ALL = $(basename $(wildcard bnx2_fwcutter_*.c))
clean:
	rm -f $(ALL) $(ALL:=.h)
