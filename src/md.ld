OUTPUT_ARCH(m68k)
ENTRY(_start)
/* Pages 0-1 (1 MB) are always mapped; the code gets the first 704 KB (tools/mkbanks.py CODE_END). Big data lives in higher ROM pages and is mapped into
   the windows at 0x180000 / 0x200000 / 0x300000 with the Sega mapper (see tools/mkbanks.py, src/bank.h). */
MEMORY {
  rom (rx) : ORIGIN = 0x000000, LENGTH = 0xB8000
  ram (rwx) : ORIGIN = 0xFF0000, LENGTH = 0x10000
}
SECTIONS {
  .text : {
    KEEP(*(.vectors))
    KEEP(*(.header))
    *(.text .text.*)
    *(.rodata .rodata.*)
    . = ALIGN(2);
    _etext = .;
  } > rom
  .data : AT(_etext) {
    _sdata = .;
    *(.data .data.*)
    . = ALIGN(2);
    _edata = .;
  } > ram
  .bss (NOLOAD) : {
    _sbss = .;
    *(.bss .bss.* COMMON)
    . = ALIGN(2);
    _ebss = .;
  } > ram
  ASSERT(_etext + SIZEOF(.data) <= 0xB8000, "code area full: raise CODE_END in tools/mkbanks.py and src/md.ld")
  INCLUDE banks.ld
  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame) }
}
