# Черновик письма Filippo Falezza (автору upstream-фикса UTMI-resume)

Кому: Filippo Falezza <f.falezza@outlook.com> (адрес из серии 20261027-dwc3-utmi-resume;
сверить с patchew перед отправкой)
Тема: your dwc3 UTMI-resume fix — mirrored into dwc3-qcom-legacy, tested on SM6225

Текст письма:

---

Subject: your dwc3 UTMI-resume fix — mirrored into dwc3-qcom-legacy, tested on SM6225

Hi Filippo,

I'm bringing up mainline on a Chuwi AuPad tablet (SM6225, the khaje/qcm2290
die family), and your series "dwc3: fix gadget failures after system suspend"
(20261027-dwc3-utmi-resume) fixed exactly the failure we saw: the controller
lost its QSCRATCH GENERAL_CFG UTMI-as-pipe-clk programming over a CX collapse
during s2idle and the gadget died with "failed to enable ep0out" on resume.

One gap: this board's usb@4ef8800 carries the legacy "qcom,sm6115-dwc3",
"qcom,dwc3" compatibles, so it binds dwc3-qcom-legacy — the glue your series
(understandably) left alone. I mirrored the fix there: remember
qcom,select-utmi-as-pipe-clk at probe and reselect the UTMI clock in
dwc3_qcom_resume(), with dwc3_qcom_select_utmi_clk() moved above its new
caller. Hardware-tested on the AuPad: the ep0out failure is gone and the
controller survives resume. (The gadget link itself still needs an
unbind/bind after resume on this board — I suspect our SNPS femto-PHY
bring-up rather than the glue, and EUD being enabled keeps the PHY alive
across suspend here; not your patch's problem.)

If you ever want to extend the series to the legacy glue, the tested patch
is below/attached (it's against 7.3.1 + your v1; happy to rebase on your
tree).

Thanks for the fix and the clear commit message — it made the port
straightforward.

Best regards,
kirill / sleeply4cat

--- патч: содержимое patches/linux/0044-usb-dwc3-qcom-legacy-restore-the-UTMI-PIPE-clock-o.patch ---
(приложить файлом; из шапки убрать строку From acad036027..., оставить
Subject/From/Signed-off-by; строки Co-Authored-By/Claude-Session — по твоему
усмотрению, для upstream-переписки их обычно не шлют)

---

## Заметки

- Отправка — руками (mutt/thunderbird): адрес взять с patchew-страницы серии,
  не из этого черновика.
- Если решишь отправлять сам патч в LKML как формальную серию — нужно
  `./scripts/checkpatch.pl`, формат cover letter и Cc: linux-usb@, Greg KH.
  Для личного письма достаточно текста выше.
- Наблюдение про femto-PHY/EUD можно убрать, если не хочешь углубляться —
  но оно честно объясняет, почему мы не рапортуем «полностью починенный
  resume».
