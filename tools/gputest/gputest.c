/* Smallest proof that the Adreno runs commands: have the CP write a word to memory.  No Mesa needed. */
#include <fcntl.h>
#include <stdio.h>
#include <stdint.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <drm/drm.h>
#include <drm/msm_drm.h>

static uint32_t parity(uint32_t v)
{
	return (0x9669 >> (0xf & (v ^ (v >> 4) ^ (v >> 8) ^ (v >> 12) ^ (v >> 16) ^ (v >> 20) ^ (v >> 24) ^ (v >> 28)))) & 1;
}

static uint32_t pkt7(uint32_t op, uint32_t cnt)
{
	return 0x70000000 | cnt | parity(cnt) << 15 | op << 16 | parity(op) << 23;
}

static int fd;

static uint64_t param(uint32_t p)
{
	struct drm_msm_param a = { .pipe = MSM_PIPE_3D0, .param = p };

	if (ioctl(fd, DRM_IOCTL_MSM_GET_PARAM, &a)) {
		perror("get_param");
		return 0;
	}
	return a.value;
}

int main(void)
{
	struct drm_msm_gem_new gn = { .size = 4096, .flags = MSM_BO_WC };
	struct drm_msm_gem_info gi = { .info = MSM_INFO_GET_OFFSET };
	struct drm_msm_gem_info ga = { .info = MSM_INFO_GET_IOVA };
	struct drm_msm_gem_submit_bo bo = { .flags = MSM_SUBMIT_BO_READ | MSM_SUBMIT_BO_WRITE };
	struct drm_msm_gem_submit_cmd cmd = { .type = MSM_SUBMIT_CMD_BUF };
	struct drm_msm_gem_submit sub = { .flags = MSM_PIPE_3D0, .nr_bos = 1, .nr_cmds = 1 };
	struct drm_msm_wait_fence wf = { 0 };
	struct timespec ts;
	volatile uint32_t *m;
	uint64_t t0, t1, target;
	int n = 0;

	fd = open("/dev/dri/renderD128", O_RDWR);
	if (fd < 0) {
		perror("open");
		return 1;
	}
	printf("gpu id %llu chip %#llx gmem %llu\n", (unsigned long long)param(MSM_PARAM_GPU_ID),
	       (unsigned long long)param(MSM_PARAM_CHIP_ID), (unsigned long long)param(MSM_PARAM_GMEM_SIZE));
	t0 = param(MSM_PARAM_TIMESTAMP);
	usleep(100000);
	t1 = param(MSM_PARAM_TIMESTAMP);
	printf("ticks in 100 ms: %llu\n", (unsigned long long)(t1 - t0));

	if (ioctl(fd, DRM_IOCTL_MSM_GEM_NEW, &gn))
		return perror("gem_new"), 1;
	gi.handle = ga.handle = bo.handle = gn.handle;
	if (ioctl(fd, DRM_IOCTL_MSM_GEM_INFO, &gi) || ioctl(fd, DRM_IOCTL_MSM_GEM_INFO, &ga))
		return perror("gem_info"), 1;
	m = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, gi.value);
	if (m == MAP_FAILED)
		return perror("mmap"), 1;
	printf("iova %#llx\n", (unsigned long long)ga.value);

	target = ga.value + 0x800;
	m[0x800 / 4] = 0;
	m[n++] = pkt7(0x3d, 3);		/* CP_MEM_WRITE */
	m[n++] = target;
	m[n++] = target >> 32;
	m[n++] = 0xc0ffee42;

	cmd.size = n * 4;
	sub.bos = (uintptr_t)&bo;
	sub.cmds = (uintptr_t)&cmd;
	if (ioctl(fd, DRM_IOCTL_MSM_GEM_SUBMIT, &sub))
		return perror("submit"), 1;
	printf("submitted, fence %u\n", sub.fence);

	clock_gettime(CLOCK_MONOTONIC, &ts);
	wf.fence = sub.fence;
	wf.timeout.tv_sec = ts.tv_sec + 3;
	wf.timeout.tv_nsec = ts.tv_nsec;
	if (ioctl(fd, DRM_IOCTL_MSM_WAIT_FENCE, &wf))
		return perror("wait_fence"), 1;
	printf("fence signalled, memory now %#x (%s)\n", m[0x800 / 4], m[0x800 / 4] == 0xc0ffee42 ? "PASS" : "FAIL");
	return m[0x800 / 4] != 0xc0ffee42;
}
