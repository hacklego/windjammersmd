#pragma once
#include "types.h"
#include "sounddata.h"     /* generated: music streams, sample table, SFX_* sample ids */

#define TEMPO_NORMAL 64

void snd_init(void);
void snd_music(const Music *m);     /* 0 = stop; restarts the tune */
void music_play(const Music *m);    /* start a tune unless it is already playing */
void snd_tempo(u16 rate);           /* TEMPO_NORMAL = original speed */
void snd_sfx(u16 sample_id);
void snd_psg(const u8 *stream);
void snd_step(void);                /* called twice per frame from the HBlank interrupt */
void hblank_handler(void);
extern volatile u16 hint_count;

#define sfx_play(id) snd_sfx(id)
#define voice_play(kind, character) snd_sfx(voice_table[kind][character])
