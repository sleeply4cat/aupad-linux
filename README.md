# Mainline Linux on the CHUWI AuPad

Mainline Linux 7.3-rc3 and postmarketOS on the CHUWI AuPad tablet: Qualcomm SM6225 ("khaje"), board UNC6851 CW108-WW,
10.51" 1200x1920. Upstream has no SM6225 support, so this port builds on `sm6115.dtsi` and overrides what differs.

**Status: bring-up.** It's a working developer port, not an installable release. It boots from UFS with no host
attached, but setting it up rewrites partitions, and getting it wrong can leave you needing EDL. Keep a full backup.

> [!WARNING]
> **Non-standard unlock.** This tablet is unlocked by a two-byte `devinfo` edit plus a modified `vbmeta`, not the usual
> `fastboot flashing unlock`. Only the two together are known to work. The procedure is widely known, but the right `vbmeta`
> depends on your tablet's state and stock OS version: `vbmeta_a` and `vbmeta_b` can be different builds and aren't
> interchangeable. A wrong one can drop the tablet into a ramdump on every boot. `adb reboot edl`
> needs a running Android, so recovery then takes a magic cable. Patch the image from the slot you're running, and back up
> everything first.

| Area | Status | Notes |
|---|---|---|
| CPU, cpufreq, thermal | Works | Cluster and CCI idle work. PMU node removed: it hangs the SoC |
| UFS | Works | HS-G3 x2 |
| USB | Partial | Gadget only, HS. No USB3 PHY |
| Display, backlight | Works | 60 Hz |
| Touch | Works | Up to 10 points. Far-apart fingers glitch, also on stock |
| Buttons | Works | Power-off restarts if USB is attached |
| GPU | Works | GLES 3.2 and Weston. Vulkan loads |
| Desktop | Works | Phosh with auto-rotate, installed by `build/pmos-install.sh`. Starts upside down if the tablet lies flat |
| Wi-Fi | Works | 2.4 and 5 GHz, generated MAC |
| Bluetooth | Works | Pairing and A2DP audio, tested with one headset. Calls untested |
| microSD | Partial | Reads work, writes and removal untested |
| Accelerometer | Works | Through the ADSP. Other sensors not exposed |
| Speakers | Works | Software volume, 14 dB under stock level |
| Internal mic | Partial | Signal measured, not yet checked by ear |
| Headphones, headset mic | Not tested | Jack ribbon disconnected on the dev tablet |
| ADSP, CDSP, modem | Partial | Firmware boots. ADSP crash recovery can panic the kernel. Reinserting a SIM while powered on needs a reboot |
| Mobile data | Partial | LTE through ModemManager, ping tested on one SIM. Browsing and speed untested |
| Calls, SMS | Partial | USSD works from `mmcli`, the Phosh dialer shows no reply. No call audio driver. SMS untested |
| GPS | Works | Fixes through ModemManager, confirmed on the tablet |
| Battery | Partial | Percentage, status and measured current work. No charger control: bootloader settings, 500 mA USB input, low battery untested |
| Boot | Broken | Some boots freeze the whole SoC around 10 s |
| Suspend | Partial | Works only with workarounds, no whole-chip sleep, USB lost on resume. Disabled |
| Rear camera | Partial | OV13B10 through CAMSS and libcamera, works in Snapshot. Fixed focus in apps, no gain control, crops in portrait. Megapixels has controls but its preview blinks |
| Front camera | Not working | GC5035 not detected, ribbon on the dev tablet unchecked |
| USB3, packaging for pmaports | Not started | |

Known gaps: a boot can freeze the whole SoC, and the kernel on disk then needs a host to recover, see "Boot hang" in the docs. The GPU doesn't vote the MX rail, so 1260 MHz is tested rather than guaranteed. The LP6280S display bias chip
has no driver and relies on the bootloader. See [docs/PORT.md](docs/PORT.md) for how everything works and what went wrong.

## What's here

| Path | Contents |
|---|---|
| `patches/linux/` | Kernel series: clocks, UFS PHY, UBWC, PWM, panel, audio, camera, battery, device tree |
| `patches/u-boot/` | U-Boot series: UFS on SM6225, boot environment |
| `configs/aupad_defconfig` | Kernel config |
| `stub/` | Pre-U-Boot stub: arms the watchdog, sets up the UART, jumps to the payload |
| `build/` | Boot image, rootfs and test-loop scripts, initramfs, audio topology source and UCM profile, camera config |
| `tools/` | Clock driver generators, GPU tests, register peek/poke, test patterns, USB-only package proxy, UART recorder, ramdump capture |
| `docs/PORT.md` | Engineering notes |

No firmware, dumps or stock binaries are included. You need these from your own device or public sources:
GPU firmware `a630_sqe.fw` and `a610_zap.*` from `/vendor/firmware` into `firmware/`, and a static aarch64 busybox as
`build/initramfs/busybox`. The audio topology is built from source. Modem, DSP, Wi-Fi, Bluetooth and sensor files are listed in [docs/PORT.md](docs/PORT.md).

## Building

The patches were developed and tested on `mt6735-staging` at `a62a3e8f9` of
https://gitlab.com/mt6735-mainline/linux.git, a 7.3-rc3 tree. They only touch Qualcomm code, but plain upstream
7.3-rc3 is untested and may need small fixups.

```sh
python3 -m venv venv && venv/bin/pip install pyserial pyusb

git clone https://gitlab.com/mt6735-mainline/linux.git && cd linux
git checkout -b aupad a62a3e8f9 && git am ../patches/linux/*.patch
mkdir -p ../build/out && cp ../configs/aupad_defconfig ../build/out/.config
make O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- olddefconfig
make O=../build/out ARCH=arm64 CROSS_COMPILE=aarch64-linux-gnu- -j$(nproc) Image modules qcom/sm6225-chuwi-aupad.dtb
cd ..

aarch64-linux-gnu-gcc -O2 -static -o build/tests/rx build/tests/rx.c
aarch64-linux-gnu-gcc -O2 -static -o build/tests/rb build/tests/rb.c
cat ~/.ssh/id_ed25519.pub > build/tests/authorized_keys

CMDLINE="earlycon=qcom_geni,0x4a90000 console=ttyMSM0,115200n8 ignore_loglevel \
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
