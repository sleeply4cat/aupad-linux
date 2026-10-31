#!/usr/bin/env python3
# Pull the hand-made parts of the tablet's system out of a rootfs backup: mkoverlay.py <backup.tar.gz> <overlay.tar.gz>
# The result holds the Wi-Fi password, the user's password hash and stock firmware: local only, never publish.
import sys, tarfile
KEEP = ("etc/elogind/sleep.conf.d/50-aupad-nosuspend.conf", "etc/conf.d/rmtfs", "etc/conf.d/hexagonrpcd-adsp-sensorspd",
        "etc/conf.d/unudhcpd", "etc/wpa_supplicant/wpa_supplicant.conf", "etc/ssh/ssh_host_",
        "etc/NetworkManager/conf.d/50-aupad-usb0.conf", "etc/NetworkManager/system-connections/",
        "etc/local.d/audio-gain.start", "etc/local.d/bt-addr.start", "etc/modprobe.d/aupad.conf",
        "etc/udev/rules.d/60-aupad-touch.rules", "etc/udev/rules.d/61-aupad-accel.rules", "etc/udev/rules.d/70-wlan-mac.rules",
        "etc/bluetooth/bdaddr", "etc/phosh/phoc.ini", "lib/firmware/qcom/", "lib/firmware/qca/", "lib/firmware/ath10k/",
        "usr/share/qcom/", "usr/share/alsa/ucm2/Qualcomm/sm6225/", "usr/share/alsa/ucm2/conf.d/sm6225/",
        "var/lib/rmtfs/", "var/lib/bluetooth/", "var/lib/greetd/.config/pulse/default.pa",
        "usr/sbin/gputest", "usr/sbin/gpustress", "usr/sbin/gpusweep", "usr/sbin/peek", "usr/sbin/poke", "usr/sbin/wifi-join",
        "root/.config/weston.ini")
n = 0
with tarfile.open(sys.argv[1]) as src, tarfile.open(sys.argv[2], "w:gz") as dst:
    for m in src:
        name = m.name.removeprefix("./")
        if not name.startswith(KEEP):
            if name == "etc/shadow":
                for l in src.extractfile(m).read().decode().splitlines():
                    if l.startswith("user:"):
                        shadow = l
            continue
        dst.addfile(m, src.extractfile(m) if m.isreg() else None)
        n += 1
    import io
    data = (shadow + "\n").encode()
    ti = tarfile.TarInfo("etc/aupad-user-shadow"); ti.size = len(data); ti.mode = 0o600
    dst.addfile(ti, io.BytesIO(data))
print(n + 1, "entries")
