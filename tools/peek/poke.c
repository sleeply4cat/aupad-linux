/* Write one 32-bit MMIO register, for live experiments: poke <addr> <value> */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

int main(int argc, char **argv)
{
	unsigned long a = strtoul(argv[1], NULL, 0);
	int fd = open("/dev/mem", O_RDWR | O_SYNC);
	volatile unsigned int *p;

	if (fd < 0 || argc != 3)
		return perror("poke"), 1;
	p = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, a & ~4095UL);
	if (p == MAP_FAILED)
		return perror("mmap"), 1;
	printf("%#lx: %08x", a, p[(a & 4095) / 4]);
	p[(a & 4095) / 4] = strtoul(argv[2], NULL, 0);
	printf(" -> %08x\n", p[(a & 4095) / 4]);
	return 0;
}
