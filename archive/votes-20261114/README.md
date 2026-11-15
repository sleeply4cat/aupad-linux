# Client Votes — данные 2026-11-14 (сырые артефакты сессии)

Сюда сложено всё из /tmp и с планшета по экспериментам с Client Votes / сном.
Файлы: sleepvote.sh/eudoff.sh — скрипты циклов; sleepvote.txt, eudoff.txt —
результаты с планшета; pingwatch*.log — непрерывные пинги через сны (разрыв =
настоящий сон); aupad-sleep.log — фазовый лог elogind-хука; eudlog.out — сырое
эхо EUD-консоли за день.

## Методика и находки

- **Пост-wake чтение голосов всегда опаздывает**: пользователи (и даже
  wake-instant из скрипта по elogind-пути) переголосовывают до первого чтения.
  Сырой `echo freeze` + мгновенное чтение тоже опаздывает: kernel-драйверы
  переголосовывают в device-resume до разморозки задач. Стабильные значения:
  awake-после-cycles 0x87838783, через 8 c после wake — то же.
- **syscore-снапшоттер не подходит**: freeze (s2idle) идёт мимо
  syscore_suspend() (suspend_enter() выходит на s2idle_loop до него,
  kernel/power/suspend.c:447-455). votes_snap.c (syscore) — мёртвый груз:
  без module_exit выгружается как "Resource busy", висит в lsmod, безвреден.
- **votes_nrq.c (freeze_noirq на фиктивном platform_device)** — собран,
  загружен, но за цикл ни одной строки в dmesg (dmesg к вечеру вообще отдаёт
  только boot-хвост — буфер, похоже, переполнен спамом; недоизучено).
- **rfkill-тогглы (awake, vlow)**: base 0x83818381 → wifi block: 0x83878381
  (byte1 81→87), +bt block: без изменений → unblock: 0x87838783. Байт-структура
  = 4 независимых байта-воксера; карта битов по-прежнему неизвестна.
- vmin-запись всегда 0x0 (append-блок, вероятно, не пишется для vmin).
- Агент-поиск расшифровки дважды упёрся в лимиты (5h и weekly, сброс 2026-11-18);
  downstream-поиск (CodeLinaro khaje rpm_stats.c) не выполнен.

## День 2 (2026-11-15): noirq-снапшоты работают

После ребута (вчерашний hook-цикл с rfkill заклинил UFS/userspace на ~час; вылечено
жёстким выключением) модуль votes_nrq доработан (resume_noirq + dump type/count) и
сняты оба снимка на hook-пути. Hook-цикл с wifi+bt off прошёл чисто (pre 2 c, post 5 c).

| Фаза | wifi/bt | vlow Client Votes |
|---|---|---|
| awake settled | on | 0x87838783 |
| awake (между циклами) | on | 0x83818381 / 0x81838183 (плавает) |
| awake, rfkill wifi (или wifi+bt) | off | 0x83878381 |
| freeze_noirq (сырой цикл, радио on) | on | 0x83878381 |
| resume_noirq (тот же цикл) | on | 0x83878381 |
| freeze_noirq (hook-цикл, радио off) | off | 0x85818581 |
| resume_noirq (тот же) | off | 0x85818581 |
| истинный пол сна (13.11, удачный post-wake) | on | 0x81 |

Наблюдения:
- **freeze == resume всегда**: RPM голоса за сон не переписывает (vlow cnt 0), ядро
  не переголосовывает до resume_noirq.
- Радио меняют noirq-пол (83/87-байты → 85/81-байты), но не монотонно — без карты
  битов из прошивки не интерпретируется. Алфавит байтов {81,83,85,87} = бит7 всегда +
  подмножество {0,1,2}.
- Разрыв между noirq-полом и истинным полом 0x81 — голоса, счищаемые только на
  финальном WFI (после noirq-фазы). To-do: чтение из IRQ-хендлера RTC-alarm, если
  понадобится ещё точнее.
- **Сырой freeze без elogind-хука роняет ADSP sensorspd** (frpc_dsp fatal, crash #1,
  WARN-шквал __mutex_lock) — все будущие циклы только через хук. Вероятная причина
  вчерашнего заклинивания — recovery после этого краша + UFS-столл.
- vmin append-блок всегда 0x0.

## День 2+: сравнение со стоковым Android (2026-11-15)

Путь: misc→qmmi (RAM-бут bcbclr, авто-ребут), Android 15 / msm-5.15.170-android13,
slot b, adb через Magisk su. Возврат: su-dd boot-recovery в misc (bcb.bin подход,
бэкап в misc-backup-20261115.bin).

**Главный вывод — сток на паритете с нашим портом, «vlow-блокер» это продукт, а не
дефект порта:**
- `qcom_sleep_stats`: **vlow Count = 0, vmin Count = 0 на стоке** (так же, как у нас);
  apss Count 1.14M (кластерные шатдауны), adsp 15728, modem 824.
- `rpm_master_stats`: **APSS xo_count = 0x0 на стоке** (MPSS xo_count 0x39b) — APSS
  никогда не гасит XO и на стоке. Этап D плана (vmin/vlow > 0) закрывается как N/A:
  сток этого не делает.
- `mem_sleep = [s2idle]` на стоке — тот же режим.
- **Стоковый suspend тоже сорвался**: `echo mem > /sys/power/state` →
  `last_failed_dev 4e00000.ssusb, errno -16 (EBUSY), step suspend` при активной
  adb-сессии. Наш pmOS засыпает с активным NCM-гаджетом и просыпается по RTC.
  Т.е. наш suspend по факту лучше стокового в этом сценарии.
- Стоковый rpm_stats: vlow Client_votes = 0x0 — append-блок не пишется вовсе (у нас
  он пишется: 0x81 во сне). Измеряемая «карта голосов» у нас ЕСТЬ, у стока нет.
- EUD под Android: хаб исчез — ABL/Android гасят mode_mgr2, стаб (recovery_b) при
  обычной загрузке в boot_b не запускается. Консоли под Android нет, всё через adb.

Следствие для работ: часы в vlow/vmin не цель — цель сравнение ватт в suspend
(energy_now до/после, сток vs pmOS) и вход RPM-Assisted-шатдауна. Карта битов —
академический интерес для апстрима (агент всё ещё ищет downstream-расшифровку).

## Следующий шаг

Повторить noirq-снапшот, предварительно очистив консольный спам, или добавить
в votes_nrq чтение голосов в freeze_noirq + resume_noirq и печать сразу при
resume_noirq (до переголосовки остальных). После 2026-11-18 — перезапустить
downstream-поиск карты битов.
