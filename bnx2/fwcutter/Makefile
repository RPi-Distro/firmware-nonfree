test :=
ifdef KERNEL_SOURCE
test += source
endif
ifdef KERNEL_VERSION
test += version
endif

ifeq "$(test)" " source version"
CFLAGS += -I$(KERNEL_SOURCE)/drivers/net
CFLAGS += --std=gnu99
LDFLAGS += -lz

all: bnx2_fwcutter_$(KERNEL_VERSION)

bnx2_fwcutter_$(KERNEL_VERSION): bnx2_fwcutter_$(KERNEL_VERSION).c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
else
all:
	$(error Please define KERNEL_SOURCE and KERNEL_VERSION)
endif

clean:
	rm -f $(basename $(wildcard bnx2_fwcutter_*.c))
