/* rx <port> <file>: accept one TCP connection on [::]:port, save the stream. */
#include <arpa/inet.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	static char buf[1 << 20];
	struct sockaddr_in6 a = { .sin6_family = AF_INET6 };
	int s = socket(AF_INET6, SOCK_STREAM, 0), on = 1, c, f;
	long n, total = 0;

	if (argc < 3)
		return 2;
	a.sin6_port = htons(atoi(argv[1]));
	setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &on, sizeof(on));
	if (bind(s, (void *)&a, sizeof(a)) || listen(s, 1)) {
		perror("bind");
		return 1;
	}
	c = accept(s, NULL, NULL);
	f = open(argv[2], O_CREAT | O_TRUNC | O_WRONLY, 0644);
	while ((n = read(c, buf, sizeof(buf))) > 0) {
		write(f, buf, n);
		total += n;
	}
	close(f);
	dprintf(c, "%ld\n", total);
	printf("rx %s %ld\n", argv[2], total);
	return 0;
}
