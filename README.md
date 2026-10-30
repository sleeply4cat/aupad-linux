# Mainline Linux on the CHUWI AuPad

Mainline Linux 7.3-rc3 and postmarketOS on the CHUWI AuPad tablet: Qualcomm SM6225 ("khaje"), board UNC6851 CW108-WW,
10.51" 1200x1920. Upstream has no SM6225 support, so this port builds on `sm6115.dtsi` and overrides what differs.

**Status: bring-up.** It's a working developer port, not an installable release. It boots from UFS with no host
attached, but setting it up rewrites partitions, and getting it wrong can leave you needing EDL. Keep a full backup.

| Area | State |
|---|---|
| CPU, cpufreq, thermal, watchdog | Works. PMU node removed: it hangs the SoC, cause unknown |
| UFS | Works, HS-G3 x2 |
| USB | Gadget works, HS only. No USB3 PHY yet |
| Display | Works: DPU, 7 nm DSI, FT8201P panel, 60 Hz |
| Backlight | Works, PM6125 PWM |
| Touch | Works, up to 10 points. Far-apart fingers glitch, also seen on stock |
| GPU | Adreno 610: OpenGL ES 3.2 and Weston work, Vulkan driver loads, stress-tested at up to 1260 MHz |
| Battery | Gauge readout only. Charging runs on bootloader settings, no charger driver |
| Wi-Fi, BT, audio, modem, camera, sensors | Not started |
| Suspend | Not tested |

Known gaps: the GPU doesn't vote the MX rail, so 1260 MHz is tested rather than guaranteed. The LP6280S display bias chip
has no driver and relies on the bootloader. See [docs/PORT.md](docs/PORT.md) for how everything works and what went wrong.

## What's here

| Path | Contents |
|---|---|
| `patches/linux/` | Kernel series: clocks, UFS PHY, UBWC, PWM, panel, device tree |
| `patches/u-boot/` | U-Boot series: UFS on SM6225, boot environment |
| `configs/aupad_defconfig` | Kernel config |
| `stub/` | Pre-U-Boot stub: arms the watchdog, sets up the UART, jumps to the payload |
| `build/` | Boot image, rootfs and test-loop scripts, initramfs |
| `tools/` | Clock driver generators, GPU tests, register peek/poke, test patterns, USB-only package proxy |
| `docs/PORT.md` | Engineering notes |

No firmware, dumps or stock binaries are included. You need these from your own device or public sources:
GPU firmware `a630_sqe.fw` and `a610_zap.*` from `/vendor/firmware` into `firmware/`, and a static aarch64 busybox as
`build/initramfs/busybox`.

## Building

The patches were developed and tested on `mt6735-staging` at `a62a3e8f9` of
https://gitlab.com/mt6735-mainline/linux.git, a 7.3-rc3 tree. They only touch Qualcomm code, but plain upstream
7.3-rc3 is untested and may need small fixups.

```sh
python3 -m venv venv && venv/bin/pip install pyserial

git clone https://gitlab.com/mt6735-mainline/linux.git && cd linux
git checkout -b aupad a62a3e8f9 && git am ../patches/linux/*.patch
mkdir -p ../build/out && cp ../configs/aupad_defconfig ../build/out/.config
make O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image modules qcom/sm6225-chuwi-aupad.dtb
cd ..

aarch64-linux-gnu-gcc -O2 -static -o build/tests/rx build/tests/rx.c
aarch64-linux-gnu-gcc -O2 -static -o build/tests/rb build/tests/rb.c
cat ~/.ssh/id_ed25519.pub > build/tests/authorized_keys

CMDLINE="earlycon=qcom_geni,0x4a90000 console=tty0 console=ttyMSM0,115200n8 fbcon=font:TER16x32 ignore_loglevel \
clk_ignore_unused pd_ignore_unused rdinit=/init panic=10 root=pmos" build/mkboot.sh build/boot-pmos.img
```

U-Boot is based on `3973f3c4` of https://source.denx.de/u-boot/u-boot.git, configured with `qcom_defconfig` plus
`qcom-phone.config`, then `CONFIG_ENV_DEFAULT_ENV_TEXT_FILE="board/qualcomm/aupad.env"`, `PANIC_HANG` and
`TOOLS_MKEFICAPSULE` off. Then:

```sh
PAYLOAD=$PWD/build/uboot/u-boot-nodtb.bin EXTRA=-DSTUB_WDT=120 stub/mkstub.sh build/boot-ub.img
```

Boot chain and install steps are in [docs/PORT.md](docs/PORT.md): start at "Android-free loop" and "Rootfs". Stock ABL
doesn't take `fastboot boot`, so the first image goes to `recovery_b` from rooted Android or EDL.

## License

Patches are GPL-2.0, like the kernel and U-Boot code they change.
