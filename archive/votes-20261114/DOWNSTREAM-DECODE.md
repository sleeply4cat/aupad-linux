# Downstream-расшифровка Client Votes (агент cheap-gp, 2026-11-15)

Полный отчёт агента по поиску карты битов. Краткая выжимка + ссылки; дословные
цитаты сохранены агентом (копии источников в /tmp/soc_sleep_stats_54.c,
/tmp/rpm_stats_71.c, /tmp/rpm_master_stat.c, /tmp/bengal-pm.dtsi,
/tmp/clk_smd_rpm.c, /tmp/pro1x_sleep.md, /tmp/qcom_stats_mainline.c).

## Главные выводы

1. **Публичной таблицы декода нет нигде** — расшифровка живёт в закрытой прошивке
   rpm_proc. Все открытые драйверы (msm-5.4 khaje-gen soc_sleep_stats.c, старый CAF
   rpm_stats.c, mainline) печатают client_votes сырым hex.
2. **Семантика от инженера Qualcomm (Maulik Shah, LKML 2021, thread про qcm2290 —
   НАШ die!):**
   - «vlow and xosd are same; vmin is xosd plus voltage minimization of chip,
     memory rails»
   - «Count will increase only when all the subsystems (APSS/Modem,etc) are in
     power down mode and finally RPM decides to turn off xo clock»
   - **«Client votes are history of client votes on xo. Each byte represents xo
     clock votes from subsystems.»** — u32 = 4-байтная история/кольцо 8-битных
     снапшотов (или байт-на-мастер; обе интерпретации согласуются по битам).
     Источник: https://lkml.iu.edu/hypermail/linux/kernel/2110.2/05647.html
3. Бит7 в каждом ненулевом байте на всех трёх платформах (наш {81,83,85,87},
   qcm2290 {81,80}, SM6115 Pro1-X {87,8f}) — похоже, маркер валидности голоса, а
   не блокер; биты 0-2 (у SM6115 ещё 3) — накапливающиеся блокеры.
4. Наш истинный пол 0x81 = одна группа (почти наверняка APSS-сторона) держит XO
   голос, остальные три отсутствуют (= в power down) — точь-в-точь сигнатура Pro1-X
   до фикса («all masters power-collapse, yet APSS XO shutdown 0 and vlow/vmin 0»).
5. **Конкретный апстрим-подозреваемый: `clk_smd_rpm_handoff()` в
   drivers/clk/qcom/clk-smd-rpm.c** — голосует INT_MAX в ОБЕ сеты (active+sleep) за
   каждую клоку при probe; неклаймленные клоки держат sleep-голос вечно → «blocking
   XO shutdown». Патч Imran Shaik «clk: qcom: smd-rpm: Skip proxy votes on clocks
   for QCM2290» (https://lkml.iu.edu/2609.2/12878.html, Konrad Dybcio подтвердил
   механику) — QCM2290-only, НЕ влит в master. khaje — та же логика.
6. Pro1-X (SM6115) после этих фиксов: vmin 85% времени сна, 35-40 mA (было 75 mA,
   vlow/vmin=0). Их ноты: github.com/moWerk/sailfishos-pro1x-mainline notes/sleep.md.
   У них остаточные держатели XO: UFS lane clks через gpll0 (upstream f07317a8d57f)
   и disp_cc_mdss_ahb через bi_tcxo.
7. bengal-pm.dtsi (SM6225 spes): rpm-stats@4600000 + offset@4690014, 5 мастеров,
   но 4 байта — Maulik: «TZ covered by APSS» → APSS/MPSS/ADSP/CDSP.

## Важно в свете нашего сток-сравнения (день 2+)

Сток тоже vlow=0/xo=0 — но стоковый suspend у нас не прошёл и один раз (EBUSY на
ssusb с adb). Прошивка/vendor-ядро могли бы дойти в нормальном idle без adb.
Поэтому câu «достижим ли vlow на этом продукте» строго не закрыт; но у mainline
появился конкретный, чинимый кандидат (handoff proxy votes) — он проверяется у нас.

## Следующие эксперименты (от агента, по убыванию ценности)

1. **clk_summary-аудит на freeze_noirq** (метод Pro1-X «clksleep»): подготовленные
   счётчики bi_tcxo/rpm_smd_xo и кто их держит (gpll0←UFS lane clks, USB
   mock_utmi/phy_aux, dispcc mdss_ahb, QUP s3). Цель — ничего не prepared на
   bi_tcxo в suspend.
2. **Бекпорт skip_clks_handoff (QCM2290→khaje)** или свой патч: не отдавать
   proxy-голосы за неклаймленные клоки.
3. Пер-мастерная изоляция байтов: по одному тогглу за цикл (modem PIL down, wifi,
   bt, ADSP sensors) + чтение votes сразу после полного цикла.
4. Следить за APSS xo_count в master stats: когда XO-голос реально снят, xo_count
   начинает расти и vlow Count следует (цепочка Maulik).
5. ICC sleep-теги (RPM_ALWAYS_TAG) — блокер ступени vlow→vmin.
6. UFS: lane-clock gating / PHY retention при появлении крашей после гейтирования.
