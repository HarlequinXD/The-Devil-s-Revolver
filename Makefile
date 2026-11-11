# The Devil's Revolver - GBA build
#   make            build with clang + lld (what CI uses)
#   make assets     regenerate src/assets/*.c (needs python3, numpy, Pillow)

TARGET   := devils_revolver
CC       := clang
LD       := ld.lld
OBJCOPY  := llvm-objcopy
PYTHON   ?= python3
ARCH     := --target=armv4t-none-eabi -mcpu=arm7tdmi

CFLAGS_COMMON := $(ARCH) -O2 -ffreestanding -nostdlib -fomit-frame-pointer -mlong-calls \
                 -Wall -Wno-unused-function -Isrc -fno-strict-aliasing
THUMB := -mthumb $(CFLAGS_COMMON)
ARM   := -marm $(CFLAGS_COMMON) -O3

BUILD := build
SRC_THUMB := src/main.c src/actors.c src/hud.c \
             src/assets/tables.c src/assets/ground.c src/assets/sky.c src/assets/town.c \
             src/assets/sprites.c src/assets/world.c
SRC_ARM   := src/render.c src/world.c
OBJS := $(BUILD)/crt0.o $(BUILD)/div.o $(BUILD)/fill.o $(BUILD)/runtime.o \
        $(patsubst src/%.c,$(BUILD)/%.o,$(SRC_THUMB)) $(patsubst src/%.c,$(BUILD)/%.o,$(SRC_ARM))

all: $(TARGET).gba

$(TARGET).gba: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	$(PYTHON) tools/fixheader.py $@

$(TARGET).elf: $(OBJS) src/gba.ld
	$(LD) -T src/gba.ld --gc-sections -o $@ $(OBJS)

$(BUILD)/%.o: src/%.s
	@mkdir -p $(dir $@)
	$(CC) $(ARCH) -c $< -o $@

$(BUILD)/runtime.o: src/runtime.c
	@mkdir -p $(dir $@)
	$(CC) $(THUMB) -fno-builtin -c $< -o $@

$(BUILD)/render.o $(BUILD)/world.o: $(BUILD)/%.o: src/%.c src/game.h src/gba.h src/world.h src/assets/assets.h
	@mkdir -p $(dir $@)
	$(CC) $(ARM) -c $< -o $@

$(BUILD)/%.o: src/%.c src/game.h src/gba.h src/assets/assets.h
	@mkdir -p $(dir $@)
	$(CC) $(THUMB) -c $< -o $@

assets:
	$(PYTHON) tools/gen_assets.py --preview

clean:
	rm -rf $(BUILD) $(TARGET).elf $(TARGET).gba

.PHONY: all clean assets
