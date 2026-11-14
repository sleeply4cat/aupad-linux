/* poke <addr> [value]: read a 32-bit physical register, write value if given. */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	unsigned long addr, page = getpagesize();
	volatile unsigned *r;
	unsigned old;
	int fd;

	if (argc < 2)
		return 2;
	addr = strtoul(argv[1], NULL, 0);
	fd = open("/dev/mem", (argc > 2 ? O_RDWR : O_RDONLY) | O_SYNC);
	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	r = mmap(NULL, page, PROT_READ | (argc > 2 ? PROT_WRITE : 0), MAP_SHARED, fd, addr & ~(page - 1));
	if (r == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	r += (addr % page) / 4;
	old = *r;
	if (argc > 2)
		*r = strtoul(argv[2], NULL, 0);
	printf(argc > 2 ? "0x%08x -> 0x%08x\n" : "0x%08x\n", old, *r);
	return 0;
}
