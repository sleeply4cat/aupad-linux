/* GPU stress with correctness check: render a heavy shader offscreen, compare each frame's CRC with
 * the first pass over 8 fixed frames, so an unstable clock shows up as wrong pixels.
 * usage: gpustress <seconds> <shader loop count>     build on the tablet: cc -O2 gpustress.c -lEGL -lGLESv2 */
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES3/gl3.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define W 1920
#define H 1200
#define KEYS 8

static const char *vs = "#version 300 es\nconst vec2 p[3]=vec2[3](vec2(-1,-1),vec2(3,-1),vec2(-1,3));\n"
	"void main(){gl_Position=vec4(p[gl_VertexID],0,1);}\n";
static const char *fsf = "#version 300 es\nprecision highp float;\nuniform float t;out vec4 c;\n"
	"void main(){vec2 u=gl_FragCoord.xy/vec2(%d.,%d.);vec3 v=vec3(u,t);float s=0.;\n"
	"for(int i=0;i<%d;i++){v=abs(v)/dot(v,v)-vec3(.7,.5,.3+.01*t);s+=length(v)*.01;v=v.zxy*mat3(.8,.6,0,-.6,.8,0,0,0,1);}\n"
	"c=vec4(fract(s),fract(s*7.),fract(s*13.),1);}\n";

static double now(void)
{
	struct timespec t;

	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec / 1e9;
}

static uint32_t crc(const uint32_t *p, int n)
{
	uint32_t h = 2166136261u;

	while (n--)
		h = (h ^ *p++) * 16777619u;
	return h;
}

static GLuint shader(GLenum type, const char *src)
{
	GLuint s = glCreateShader(type);
	GLint ok;
	char log[1024];

	glShaderSource(s, 1, &src, NULL);
	glCompileShader(s);
	glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
	if (!ok) {
		glGetShaderInfoLog(s, sizeof(log), NULL, log);
		fprintf(stderr, "shader: %s\n", log);
		exit(2);
	}
	return s;
}

int main(int argc, char **argv)
{
	double secs = argc > 1 ? atof(argv[1]) : 10;
	int loops = argc > 2 ? atoi(argv[2]) : 40;
	EGLint n, major, minor;
	EGLConfig cfg;
	const EGLint ca[] = { EGL_CONTEXT_MAJOR_VERSION, 3, EGL_NONE };
	const EGLint ea[] = { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_NONE };
	PFNEGLGETPLATFORMDISPLAYEXTPROC gpd = (void *)eglGetProcAddress("eglGetPlatformDisplayEXT");
	EGLDisplay d = gpd(EGL_PLATFORM_SURFACELESS_MESA, EGL_DEFAULT_DISPLAY, NULL);
	static uint32_t ref[KEYS], buf[W * H];
	static char fs[1024];
	GLuint tex, fbo, vao, prog;
	GLint ut;
	long frames = 0, bad = 0, keys = 0;
	double t0, last;

	if (!eglInitialize(d, &major, &minor) || !eglBindAPI(EGL_OPENGL_ES_API) ||
	    !eglChooseConfig(d, ea, &cfg, 1, &n) || !n)
		return fprintf(stderr, "egl init failed\n"), 2;
	if (!eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, eglCreateContext(d, cfg, EGL_NO_CONTEXT, ca)))
		return fprintf(stderr, "egl context failed\n"), 2;

	glGenTextures(1, &tex);
	glBindTexture(GL_TEXTURE_2D, tex);
	glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGBA8, W, H);
	glGenFramebuffers(1, &fbo);
	glBindFramebuffer(GL_FRAMEBUFFER, fbo);
	glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
	glGenVertexArrays(1, &vao);
	glBindVertexArray(vao);
	snprintf(fs, sizeof(fs), fsf, W, H, loops);
	prog = glCreateProgram();
	glAttachShader(prog, shader(GL_VERTEX_SHADER, vs));
	glAttachShader(prog, shader(GL_FRAGMENT_SHADER, fs));
	glLinkProgram(prog);
	glUseProgram(prog);
	ut = glGetUniformLocation(prog, "t");
	glViewport(0, 0, W, H);

	t0 = last = now();
	while (now() - t0 < secs) {
		int k = frames % KEYS;
		uint32_t h;

		glUniform1f(ut, k * 0.1f + 0.1f);
		glDrawArrays(GL_TRIANGLES, 0, 3);
		glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, buf);
		if (glGetError() != GL_NO_ERROR)
			return printf("GL error at frame %ld\n", frames), 3;
		h = crc(buf, W * H);
		if (frames < KEYS) {
			ref[k] = h;
		} else {
			keys++;
			if (h != ref[k])
				bad++;
		}
		frames++;
		if (now() - last >= 5) {
			printf("  %.0fs: %.2f fps, %ld/%ld bad\n", now() - t0, frames / (now() - t0), bad, keys);
			fflush(stdout);
			last = now();
		}
	}
	printf("frames %ld in %.1fs = %.2f fps, checked %ld, bad %ld\n", frames, now() - t0, frames / (now() - t0), keys, bad);
	return bad != 0;
}
