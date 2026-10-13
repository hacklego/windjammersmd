# Windjammers for Mega Drive -- build from your own Neo Geo ROM set.
#   make ROM=path/to/wjammers.zip    (MAME wjammers.zip or a directory with its files)
ROM      ?=
BUILD    ?= build
OUT      ?= windjammers.bin

# libgcc is not linked: src/arith.s provides 68000-safe helpers.
# Cross toolchain: any m68k gcc works (m68k-elf-*, SGDK's, or the one tools/setup_toolchain.sh fetches)
TC_LOCAL := $(CURDIR)/.toolchain/root/usr
ifneq ($(wildcard $(TC_LOCAL)/bin/m68k-linux-gnu-gcc-13),)
  PREFIX  ?= $(TC_LOCAL)/bin/m68k-linux-gnu-
  CC      := $(PREFIX)gcc-13 -B$(TC_LOCAL)/libexec/gcc/m68k-linux-gnu/13/
  export LD_LIBRARY_PATH := $(TC_LOCAL)/lib/x86_64-linux-gnu:$(LD_LIBRARY_PATH)
else
  PREFIX  ?= m68k-elf-
  CC      := $(PREFIX)gcc
endif
OBJCOPY  := $(PREFIX)objcopy
PYTHON   ?= python3

CFLAGS   := -m68000 -mstrict-align -fno-store-merging -O2 -fomit-frame-pointer -ffreestanding -fno-builtin -nostdlib \
            -Wall -Wextra -Wno-unused-parameter -I$(BUILD) -Isrc $(CFLAGS_EXTRA)
LDFLAGS  := -m68000 -nostdlib -T src/md.ld -L$(BUILD) -Wl,--gc-sections -Wl,--no-check-sections

SRCS     := $(wildcard src/*.c)
OBJS     := $(patsubst src/%.c,$(BUILD)/%.o,$(SRCS)) $(BUILD)/crt0.o $(BUILD)/arith.o $(BUILD)/assets.o $(BUILD)/chardata.o $(BUILD)/discdata.o $(BUILD)/sounddata.o $(BUILD)/banks.o $(BUILD)/movies.o $(BUILD)/moviesnd.o $(EXTRA_OBJS)

all: $(OUT)

ifeq ($(filter clean,$(MAKECMDGOALS)),)
ifeq ($(strip $(ROM)),)
$(error No ROM given. Build with: make ROM=path/to/wjammers.zip (or a directory with the ROM files) [BIOS=path/to/neogeo.zip])
endif
ifeq ($(wildcard $(ROM)),)
$(error ROM not found: $(ROM))
endif
endif

$(BUILD)/assets.h $(BUILD)/assets.s $(BUILD)/chardata.c $(BUILD)/discdata.c&: tools/extract.py tools/mdgfx.py tools/neogeo.py tools/manifest_wjammers.py
	$(PYTHON) tools/extract.py $(ROM) $(BUILD)

# Sound: run the game's original Z80 sound driver (tools/snd/sndsim.c) and convert what it plays
Z80CORE  := .toolchain/src/z80
$(BUILD)/sndsim: tools/snd/sndsim.c
	@mkdir -p $(BUILD)
	gcc -O2 -w -I$(Z80CORE) -o $@ $< $(Z80CORE)/z80.c

$(BUILD)/sounddata.s $(BUILD)/sounddata.h&: $(BUILD)/sndsim tools/mksound.py tools/manifest_wjammers.py
	$(PYTHON) tools/mksound.py $(ROM) $(BUILD)

# Scenes of the original game: run it in a minimal Neo Geo (tools/ngrec, Musashi 68000 core +
# the Z80 core) and convert what it shows into movies. Needs the MVS BIOS: BIOS=dir or neogeo.zip
BIOS     ?= $(ROM)
MUSASHI  := .toolchain/src/musashi
$(BUILD)/m68kmake: $(MUSASHI)/m68kmake.c
	@mkdir -p $(BUILD)
	gcc -O2 -w -o $@ $<
$(BUILD)/m68kops.c: $(BUILD)/m68kmake
	cd $(BUILD) && ./m68kmake . $(CURDIR)/$(MUSASHI)/m68k_in.c
$(BUILD)/ngrec: tools/ngrec/ngrec.c $(BUILD)/m68kops.c
	gcc -O2 -w -I$(MUSASHI) -I$(BUILD) -I$(Z80CORE) -o $@ tools/ngrec/ngrec.c $(Z80CORE)/z80.c \
	    $(MUSASHI)/m68kcpu.c $(MUSASHI)/m68kdasm.c $(MUSASHI)/softfloat/softfloat.c $(BUILD)/m68kops.c -lm

$(BUILD)/movies.s $(BUILD)/movies.c $(BUILD)/movies.h&: $(BUILD)/ngrec $(BUILD)/assets.h $(BUILD)/sounddata.h tools/mkmovies.py tools/mkmovie.py tools/manifest_wjammers.py
	$(PYTHON) tools/mkmovies.py $(ROM) $(BIOS) $(BUILD)

$(BUILD)/movies.o: $(BUILD)/movies.s
	$(CC) -m68000 -c $< -o $@

$(BUILD)/moviesnd.o: $(BUILD)/movies.c $(BUILD)/sounddata.h
	$(CC) $(CFLAGS) -c $< -o $@

# Big data (music streams, movies) goes to ROM pages above 2 MB, switched in by the Sega mapper
$(BUILD)/banks.s $(BUILD)/banks.ld&: $(BUILD)/sounddata.s $(BUILD)/movies.s $(BUILD)/chardata.c tools/mkbanks.py
	$(PYTHON) tools/mkbanks.py $(BUILD)

$(BUILD)/banks.o: $(BUILD)/banks.s
	$(CC) -m68000 -c $< -o $@

$(BUILD)/sounddata.o: $(BUILD)/sounddata.s
	$(CC) -m68000 -c $< -o $@

$(BUILD)/%.o: src/%.c $(BUILD)/assets.h $(BUILD)/sounddata.h $(BUILD)/movies.h $(wildcard src/*.h)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%data.o: $(BUILD)/%data.c src/chardata.h
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/%.o: src/%.s
	@mkdir -p $(BUILD)
	$(CC) -m68000 -c $< -o $@

$(BUILD)/assets.o: $(BUILD)/assets.s
	cd $(BUILD) && $(CC) -m68000 -c assets.s -o assets.o

$(BUILD)/game.elf: $(OBJS) $(BUILD)/banks.ld src/md.ld
	$(CC) $(LDFLAGS) $(BUILD)/crt0.o $(filter-out $(BUILD)/crt0.o,$(OBJS)) -o $@

$(OUT): $(BUILD)/game.elf
	$(OBJCOPY) -O binary $< $@
	$(PYTHON) tools/romfix.py $@

clean:
	rm -rf $(BUILD) $(OUT)

.PHONY: all clean
