OUTPUT_ARCH(aarch64)
ENTRY(_start)

SECTIONS
{
	. = 0;
	.text : {
		KEEP(*(.text.head))
		*(.text .text.*)
	}
	.rodata : { *(.rodata .rodata.*) }
	.data : { *(.data .data.*) }
	. = ALIGN(16);
	__bss_start = .;
	.bss : { *(.bss .bss.*) *(COMMON) }
	. = ALIGN(16);
	__bss_end = .;
	. = . + 0x4000;
	stack_top = .;
	/* The payload Image is appended at this fixed offset by mkstub.sh. */
	. = ALIGN(0x10000);
	_stub_end = .;
	_image_size = _stub_end;
	/DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) }
}
