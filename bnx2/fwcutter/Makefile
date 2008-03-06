ifndef KERNEL_SOURCE
$(error Please define KERNEL_SOURCE)
endif
ifndef KERNEL_VERSION
$(error Please define KERNEL_VERSION)
endif

CFLAGS += -I$(KERNEL_SOURCE)/drivers/net
CFLAGS += --std=gnu99
LDFLAGS += -lz

all: bnx2_fwcutter_$(KERNEL_VERSION)

bnx2_fwcutter_$(KERNEL_VERSION): bnx2_fwcutter_$(KERNEL_VERSION).c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^
