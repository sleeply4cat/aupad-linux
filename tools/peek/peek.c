/* Read single 32-bit MMIO registers: peek <addr>...  Never walk ranges with it: holes crash the SoC. */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

int main(int argc, char **argv)
{
	int fd = open("/dev/mem", O_RDONLY | O_SYNC);

	if (fd < 0) {
		perror("/dev/mem");
		return 1;
	}
	for (int i = 1; i < argc; i++) {
		unsigned long a = strtoul(argv[i], NULL, 0);
		volatile unsigned int *p = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, a & ~4095UL);

		if (p == MAP_FAILED) {
			perror("mmap");
			return 1;
		}
		printf("%#lx: %08x\n", a, p[(a & 4095) / 4]);
		fflush(stdout);
		munmap((void *)p, 4096);
	}
	return 0;
}
