#include "vdp.h"
#include "input.h"
#include "text.h"
#include "sound.h"
#include "menu.h"
#include "match.h"
#include "player.h"
#include "rand.h"
#include "assets.h"
#include "movie.h"
#include "bonus.h"
#include "ranking.h"

/* The arcade's attract loop: Neo Geo logo, Data East, title, a demo match, GO FOR BROKE! with
 * one character profile, the dog demo, the ranking. Returns when Start is pressed. */
static void attract(void)
{
    static const Movie *const profiles[6] = { &mv_profile0, &mv_profile1, &mv_profile2, &mv_profile3, &mv_profile4, &mv_profile5 };
    static u16 cycle;
    for (;; cycle++) {
        u16 a, b;
        spr_clear();
        text_clear();
        movie_begin();
        if (movie_play(&mv_neogeo, MOVIE_SKIP, 0) || movie_play(&mv_dataeast, MOVIE_SKIP, 0)
            || movie_play(&mv_title, MOVIE_SKIP, 0))
            break;
        movie_end();
        a = rand16() % NUM_CHARS;
        b = (a + 1 + rand16() % (NUM_CHARS - 1)) % NUM_CHARS;
        match_set_cpu_level(2);
        match_set_music(&mus_match);
        match_set_round(0);
        if (match_run(a, b, rand16() % NUM_COURTS, CTRL_CPU, CTRL_CPU) == 0xFFFF) return;
        snd_music(0);
        text_clear();
        movie_begin();
        if (movie_play(profiles[cycle % 6], MOVIE_SKIP, 0)) break;
        movie_end();
        if (bonus_demo()) return;
        if (ranking_show()) break;                  /* the live RANKING TOP5 */
    }
    movie_end();
    rand_seed(frame_counter);
    sfx_play(SFX_SELECT);
}

static void one_player_game(void) {
    u16 me, unused, court;
    select_players(0, &me, &unused);
    court = court_select(0);
    u16 order[NUM_CHARS], n = NUM_CHARS, i, stage;
    /* as the original: 6 rounds, one against each character (yourself too), the last ROUND FINAL */
    for (i = 0; i < NUM_CHARS; i++) order[i] = i;
    for (i = n - 1; i > 0; i--) {                     /* shuffle opponents */
        u16 j = rand16() % (i + 1), t = order[i];
        order[i] = order[j]; order[j] = t;
    }
    match_score_reset();
    for (stage = 0; stage < n; ) {
        vs_screen(me, order[stage], stage + 1);
        {   /* the round, moved by OPTIONS / LEVEL (4 = the arcade's default) */
            s16 lv = (s16)stage + (s16)game_level - 4;
            match_set_cpu_level(lv < 0 ? 0 : (u16)lv);
        }
        match_set_music(&mus_match);
        match_set_round(stage + 1);
        if (match_run(me, order[stage], court, CTRL_HUMAN, CTRL_CPU) == 0) {
            /* as the original (P-ROM 0x115A2): the score's last digit counts the rounds won, and
               a round won 2-0 is worth 10000 more */
            match_score_add(0, 1 + (match_sets(1) ? 0 : 10000));
            stage++;
            court = (court + 1) % NUM_COURTS;
            if (stage == 2) bonus_dog(me);                         /* as the original: DOG DISTANCE after round 2 (adds its points), */
            if (stage == 4) match_score_add(0, bonus_bowl(me));    /* FLYING DISC BOWLING after round 4 */
        } else if (!continue_screen()) {
            return;
        }
    }
    ending_show();
    ranking_after_ending(match_score(0), me);       /* as the original: NAME, then the ranking */
}

static void two_player_game(void) {
    u16 c0, c1, court, w;
    select_players(1, &c0, &c1);
    court = court_select(0);
    vs_screen(c0, c1, 0);
    match_set_music(&mus_match);
    match_set_round(0);
    match_score_reset();
    w = match_run(c0, c1, court, CTRL_HUMAN, CTRL_HUMAN);
    if (w == MATCH_DRAW) ending_screen(c0, "DRAW GAME", 0);
    else ending_screen(w ? c1 : c0, w ? "PLAYER 2 WINS!" : "PLAYER 1 WINS!", 0);
}

int main(void) {
    vdp_init();
    input_init();
    ranking_init();
    snd_init();
    text_init();
    vdp_boot_stage(0x0EE);                       /* stage 4: YELLOW - pads, sound, font ready */
    __asm__ volatile("move.w #0x2000, %sr");
    vdp_boot_stage(0xE0E);                       /* stage 5: MAGENTA - interrupts on, waiting for vblank */
    vdp_wait_vblank();
    vdp_boot_stage(0xEE0);                       /* stage 6: CYAN - vblank interrupt works */
    {   /* keep each colour visible for a moment so the sequence can be seen on a TV */
        u16 i;
        for (i = 0; i < 30; i++) vdp_wait_vblank();
    }
#ifdef TEST_DEMO      /* automated balance test: make CFLAGS_EXTRA=-DTEST_DEMO=0x0102 (char0<<8 | char1) */
    match_set_cpu_level(2);
#ifdef TEST_ROUND
    match_set_round(TEST_ROUND);
#endif
#ifdef TEST_BONUS
    for (;;) bonus_dog(TEST_DEMO >> 8);
#endif
#ifdef TEST_BOWL
    for (;;) bonus_bowl(TEST_DEMO >> 8);
#endif
#ifdef TEST_ENDING
    for (;;) ending_show();
#endif
#ifdef TEST_DEEND     /* after the ending: NAME over the DATA EAST screen, then the ranking */
    for (;;) ranking_after_ending(85000, 1);
#endif
#ifdef TEST_RANK      /* a 1P loss with a score for the ranking: NAME, CONTINUE, GAME OVER, the ranking */
    for (;;) {
        match_score_reset();
        match_score_add(0, 75000);
        match_set_round(1);
        match_run(TEST_DEMO >> 8, TEST_DEMO & 0xFF, 0, CTRL_HUMAN, CTRL_CPU);
        continue_screen();
        ranking_show();
    }
#endif
#ifdef TEST_IDLE      /* nobody touches the pads: every set ends 0-0 (rules test) */
    match_run(TEST_DEMO >> 8, TEST_DEMO & 0xFF, 0, CTRL_HUMAN, CTRL_HUMAN);
#elif defined(TEST_FULL)  /* CPU vs CPU without the demo's time limit */
    match_set_cpu_level(4);
    match_run(TEST_DEMO >> 8, TEST_DEMO & 0xFF, 0, CTRL_CPU | 0x80, CTRL_CPU);
#else
    match_run(TEST_DEMO >> 8, TEST_DEMO & 0xFF, 0, CTRL_CPU, CTRL_CPU);
#endif
    for (;;) vdp_wait_vblank();
#endif
    for (;;) {
        attract();
        music_play(&mus_menu);
        how_to_play();                              /* as the original after Start (any button skips) */
        if (mode_select() == MODE_VS_CPU) one_player_game();
        else two_player_game();
    }
}
