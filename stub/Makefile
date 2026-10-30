CROSS ?= aarch64-linux-gnu-
CFLAGS := -O2 -ffreestanding -fno-builtin -nostdlib -mgeneral-regs-only \
	  -mstrict-align -fno-pic -fno-pie -mcmodel=small \
	  -fno-stack-protector -fno-asynchronous-unwind-tables -Wall

CFLAGS += $(EXTRA)

stub.bin: stub.elf
	$(CROSS)objcopy -O binary $< $@

stub.elf: start.o main.o stub.ld
	$(CROSS)ld -nostdlib -no-pie -T stub.ld -o $@ start.o main.o

%.o: %.S
	$(CROSS)gcc $(CFLAGS) -c -o $@ $<

%.o: %.c
	$(CROSS)gcc $(CFLAGS) -c -o $@ $<

clean:
	rm -f *.o stub.elf stub.bin
