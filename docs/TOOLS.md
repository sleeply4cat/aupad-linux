# Tool index

One line per utility, from its own docstring. Status column marks what replaced what;
everything else is current. Descriptions of the deeper traps live in [PORT.md](PORT.md)
sections that use each tool.

## Host workflow scripts (`build/`)

| Tool | What it does | Status |
|---|---|---|
| `build/mkboot.sh` | Pack Image.gz + AuPad DTB + busybox initramfs into a header-v2 boot image for stock ABL | current |
| `build/mkrootfs.sh` | Stage 1 rootfs: Alpine minirootfs + signed package cache; the tablet finishes the install itself (`test=stage2`) | current |
| `build/fl.sh` | Replace recovery_b from a tablet running mainline (push over USB, it flashes itself and reboots; stub + U-Boot images only) | current |
| `build/flr.sh` | Push a rootfs image into the pmos partition of a tablet running the mainline initramfs | current |
| `build/kup.sh` | Install a kernel on running pmOS, verified, reboot into it; previous one stays as `/boot/boot.old` | current |
| `build/mods.sh` | Install this build's stripped kernel modules on running pmOS; run before `kup.sh`, same build | current |
| `build/cam.sh` | Camera bring-up loop: install this build's modules beside the running ones, RAM-boot it | current |
| `build/ub.sh` | RAM-boot an image through U-Boot, no flashing, no Android | current |
| `build/pmos-install.sh` | Second half of a fresh OS: the Phosh system and everything hand-made; rerunnable | current |
| `build/rdcap.sh` | Capture a ramdump (05c6:900e) over raw USB, write `logs/rd-<time>/`, reset | current |
| `build/mkbootimg_v2.py` | Android boot-image v2 packer used by `mkboot.sh` | current |
| `build/mkoverlay.py` | Build the pmOS overlay tarball consumed by `pmos-install.sh` | current |

## Device-side utilities (`tools/devicetests/`, was `build/tests/`)

| Tool | What it does | Status |
|---|---|---|
| `Makefile` | Out-of-tree module build against `build/out` (`make -C ../../linux O=../../build/out … M=$(pwd) modules`) | current |
| `eudoff.c` → `eudoff.ko` | The sanctioned runtime EUD disable: SCM write to mode_mgr2 + CTLOUT (a plain MMIO write there panics) | current; the hardware verdict: keep EUD on |
| `votes_nrq.c` | RPM client-votes snapshots from freeze_noirq/resume_noirq on a fake platform device (syscore never runs for s2idle) | current |
| `rx.c` → `rx` | Accept one TCP connection, save the stream (initramfs file push) | current, baked into the initramfs |
| `rb.c` → `rb` | Restart passing an arg to the kernel's reboot notifiers (busybox reboot can't) | current, baked into the initramfs |
| `poke.c` → `poke` | Read/write one 32-bit physical register from userspace | current, baked into the initramfs |
| `misc.head` | The original 32-byte misc-partition command field (BCB restore reference) | data blob |
| `flash.sh` | On-tablet: write a boot image to recovery_b, verify, reboot into it (the only partition it ever writes) | current |
| `flashroot.sh` | On-tablet: write an ext4 rootfs image to the pmos partition and verify | current |
| `stage2.sh` | `test=stage2`: finish the rootfs install on the tablet itself; safe to rerun | current |
| `bcbclr.sh` | Put back misc's original 32-byte command field so ABL boots Android again | current |
| `gpusweep.sh` | Pin the GPU to each OPP in turn and run gpustress (runs on the tablet) | current |
| `eudoff.sh` | EUD-off link test harness: load the module, freeze 45 s on an RTC alarm, watch the link | session harness from the votes/EUD work |
| `sleepvote.sh` | One RAW suspend cycle with client-votes snapshots, then a self-rebind of the gadget | session harness from the votes work |

## Host Python tools (`tools/`)

| Tool | What it does | Status |
|---|---|---|
| `eudlog.py` | Record the kernel console from the EUD COM across reboots and panics; creates the `/tmp/aupad-eud` pty others talk to | current; the main console logger |
| `tab.py` | Drive the tablet through its boot states (`state`, `fastboot`, …) | current; the main test-cycle driver |
| `ubcmd.py` | Stop U-Boot's autoboot, run commands one by one, boot on (over the EUD COM pty) | current |
| `ubfast.py` | Get an idle U-Boot prompt into fastboot, repeating the first command until USB shows up | superseded by `tab.py fastboot` |
| `ubstop.py` | Stop U-Boot's autoboot and start fastboot over the EUD COM pty | superseded by `tab.py fastboot` |
| `flpush.py` | Send a boot image to the tablet's flash loader | used by `build/fl.sh` |
| `usbproxy.py` | HTTP/CONNECT proxy for the tablet, listening on the USB link only (package installs) | current |
| `uartd.py` | Own the nanobridge UART: log every line to `logs/uart/`, offer it as a pty, auto-capture ramdumps | current for the nanobridge UART |
| `uartlog.py` | One-shot nanobridge UART capture with host timestamps | simpler alternative to `uartd.py` |
| `rdraw.py` | Read a ramdump over raw USB with real timeouts (edl's read path hangs) | current |
| `rdscan.py` | Find the printk text in a ramdump and save it | current |
| `sahara_reset.py` | Send a raw Sahara RESET_REQ to a wedged memory-dump session | current |
| `gptsplit.py` | Split userdata on LUN 0 in GPT images (shrink in place, add `pmos`); touches no device | current |
| `evdec.py` | Summarise a raw evdev capture from the multitouch screen | current |
| `fbtest.py` | Make a raw XRGB8888 test pattern for the panel | current |
| `cc_port.py` | Convert downstream dispcc/gpucc-khaje.c into a mainline driver; register data copied, never edited | current |
| `gcc_port.py` | Same for gcc-khaje.c | current |
| `test_eudlog.py` | Mock tests for `eudlog.py` (resync, backpressure, disconnect) against a fake pyusb | current |

## EUD / OpenOCD (`tools/ocd/`)

| Tool | What it does | Status |
|---|---|---|
| `server` | Run OpenOCD for the tablet (patched tree in `tools/ext/openocd`, patch in `eud-sm6225.patch`), output to `logs/ocd.log` | current |
| `g` | GDB on the tablet, starting the server if needed: `g kernel` (8 Kryo cores as threads) or `g rpm` | current |
| `oc` | Run OpenOCD commands on the running server | current |
| `up` | Get the OpenOCD server running from whatever state the tablet is in; resets the EUD hub when its control function is missing | current |
| `srst` | Hard-reset the tablet through the EUD SRST line (also the way out of EDL) | current |
| `hunt.py` | Reboot until the RPM enters its abort path, halt it there and dump `logs/hang/<time>/` | current |
| `eud-sm6225.patch`, `khaje.cfg` | The OpenOCD driver patch and config behind `server` | current |

## Small C helpers (`tools/peek/`, `tools/gpustress/`, `tools/gputest/`)

| Tool | What it does | Status |
|---|---|---|
| `tools/peek/peek.c` | Read single 32-bit MMIO registers (never walk ranges: holes crash the SoC) | current |
| `tools/peek/poke.c` | Write one 32-bit MMIO register for live experiments | near-duplicate of `tools/devicetests/poke.c` (that one reads and writes) |
| `tools/gpustress/gpustress.c` | GPU stress with per-frame CRC correctness check (unstable clock → wrong pixels) | current |
| `tools/gputest/gputest.c` | Smallest proof the Adreno runs commands: CP writes a word to memory, no Mesa | current |
