"""Touch Grass - a tiny game about going outside.

Click the grass before it withers. Golden grass is worth extra and adds
time. Don't touch the phones: doomscrolling costs points and breaks your
combo. Everything (graphics, music, sound effects) is generated in code,
so the game is a single file with no asset folder.
"""

import json
import math
import os
import random
import sys
from array import array

import pygame

WIDTH, HEIGHT = 960, 600
FPS = 60
ROUND_SECONDS = 60
GROUND_TOP = 300
TITLE = "Touch Grass"

SAMPLE_RATE = 22050

# Colors
SKY_TOP = (110, 180, 245)
SKY_BOTTOM = (200, 235, 255)
HILL_FAR = (120, 190, 110)
HILL_NEAR = (95, 170, 85)
GROUND = (86, 150, 70)
DIRT = (110, 85, 55)
WHITE = (255, 255, 255)
BLACK = (20, 20, 25)
SHADOW = (0, 0, 0)
GOLD = (255, 210, 60)
RED = (230, 70, 70)
PANEL = (25, 45, 30)


# ---------------------------------------------------------------------------
# Save data
# ---------------------------------------------------------------------------

def save_path():
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "TouchGrass", "save.json")


def load_save():
    data = {"high_score": 0, "music": True, "sfx": True}
    try:
        with open(save_path(), "r", encoding="utf-8") as f:
            data.update(json.load(f))
    except (OSError, ValueError):
        pass
    return data


def write_save(data):
    try:
        path = save_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Audio synthesis
# ---------------------------------------------------------------------------

def note_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _add_note(buf, start, length, freq, volume, wave, attack=0.01, release=0.08):
    """Mix one enveloped note into a float buffer (in place)."""
    sr = SAMPLE_RATE
    n = int(length * sr)
    s0 = int(start * sr)
    a = max(1, int(attack * sr))
    r = max(1, int(release * sr))
    step = freq / sr
    phase = 0.0
    end = min(n, len(buf) - s0)
    for i in range(end):
        if i < a:
            env = i / a
        elif i > n - r:
            env = max(0.0, (n - i) / r)
        else:
            env = 1.0
        if wave == "square":
            v = 0.6 if phase < 0.5 else -0.6
        elif wave == "triangle":
            v = 4 * abs(phase - 0.5) - 1
        else:  # soft sine with a touch of 2nd harmonic
            v = math.sin(phase * 6.283185) * 0.85 + math.sin(phase * 12.56637) * 0.15
        buf[s0 + i] += v * env * volume
        phase += step
        if phase >= 1.0:
            phase -= 1.0


def _to_sound(buf, channels):
    peak = max(1e-6, max(abs(v) for v in buf))
    scale = 32767 * 0.9 / max(1.0, peak)
    samples = array("h", (int(v * scale) for v in buf))
    if channels > 1:
        stereo = array("h", [0]) * (len(samples) * channels)
        for c in range(channels):
            stereo[c::channels] = samples
        samples = stereo
    return pygame.mixer.Sound(buffer=samples.tobytes())


def make_music(channels):
    """A cheerful 16-second chiptune loop: C - Am - F - G, two bars each."""
    bpm = 120
    beat = 60 / bpm
    bar = beat * 4
    buf = [0.0] * int(bar * 8 * SAMPLE_RATE)

    chords = [
        (48, [60, 64, 67, 72]),  # C
        (45, [57, 60, 64, 69]),  # Am
        (41, [53, 57, 60, 65]),  # F
        (43, [55, 59, 62, 67]),  # G
    ]
    # Melody: (midi note or None, beats) per two-bar chord
    melody = [
        [(72, 1), (76, 1), (79, 1.5), (76, 0.5), (77, 1), (76, 1), (74, 2)],
        [(72, 1), (69, 1), (72, 1.5), (76, 0.5), (74, 2), (None, 2)],
        [(69, 1), (72, 1), (77, 1.5), (76, 0.5), (74, 1), (72, 1), (69, 2)],
        [(71, 1), (74, 1), (79, 1), (77, 1), (76, 1), (74, 1), (71, 2)],
    ]

    for ci, (root, arp) in enumerate(chords):
        base = ci * bar * 2
        # Bass: bouncing eighth notes, root and octave
        for i in range(16):
            n = root if i % 2 == 0 else root + 12
            _add_note(buf, base + i * beat / 2, beat / 2 * 0.9, note_freq(n), 0.22, "triangle")
        # Arpeggio: sixteenths
        for i in range(32):
            n = arp[i % 4]
            _add_note(buf, base + i * beat / 4, beat / 4 * 0.8, note_freq(n), 0.07, "square",
                      attack=0.003, release=0.04)
        # Melody
        t = base
        for n, beats in melody[ci]:
            if n is not None:
                _add_note(buf, t, beats * beat * 0.95, note_freq(n), 0.22, "sine",
                          attack=0.02, release=0.12)
            t += beats * beat
    # Light noise "hi-hat" on off-beats
    rng = random.Random(7)
    hat_len = int(0.03 * SAMPLE_RATE)
    for i in range(16 * 4):
        if i % 2 == 1:
            s0 = int(i * beat / 2 * SAMPLE_RATE)
            for j in range(hat_len):
                if s0 + j < len(buf):
                    buf[s0 + j] += (rng.random() * 2 - 1) * 0.05 * (1 - j / hat_len)
    return _to_sound(buf, channels)


def make_sfx(channels):
    def tone(notes, wave, vol, length):
        buf = [0.0] * int(SAMPLE_RATE * (length + 0.15))
        for start, dur, n in notes:
            _add_note(buf, start, dur, note_freq(n), vol, wave, attack=0.003, release=0.05)
        return _to_sound(buf, channels)

    pluck = tone([(0, 0.08, 79), (0.05, 0.1, 84)], "sine", 0.5, 0.15)
    golden = tone([(0, 0.08, 84), (0.07, 0.08, 88), (0.14, 0.08, 91), (0.21, 0.2, 96)],
                  "square", 0.25, 0.41)
    bad = tone([(0, 0.12, 45), (0.1, 0.25, 40)], "square", 0.35, 0.35)
    click = tone([(0, 0.05, 72)], "triangle", 0.4, 0.05)
    end = tone([(0, 0.15, 72), (0.15, 0.15, 76), (0.3, 0.15, 79), (0.45, 0.45, 84)],
               "sine", 0.4, 0.9)
    pluck.set_volume(0.6)
    return {"pluck": pluck, "golden": golden, "bad": bad, "click": click, "end": end}


class Audio:
    def __init__(self, settings):
        self.settings = settings
        self.ok = False
        self.sfx = {}
        self.music = None
        try:
            init = pygame.mixer.get_init()
            if init and init[0] != SAMPLE_RATE:
                pygame.mixer.quit()  # pygame.init() may have opened it at another rate
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
            init = pygame.mixer.get_init()
            if init and init[0] == SAMPLE_RATE:
                channels = init[2]
                self.music = make_music(channels)
                self.music.set_volume(0.45)
                self.sfx = make_sfx(channels)
                self.ok = True
        except pygame.error:
            self.ok = False
        self.music_channel = None

    def play(self, name):
        if self.ok and self.settings["sfx"] and name in self.sfx:
            self.sfx[name].play()

    def start_music(self):
        if self.ok and self.settings["music"]:
            if self.music_channel is None or not self.music_channel.get_busy():
                self.music_channel = self.music.play(loops=-1, fade_ms=600)

    def stop_music(self):
        if self.ok and self.music:
            self.music.stop()
            self.music_channel = None

    def toggle_music(self):
        self.settings["music"] = not self.settings["music"]
        if self.settings["music"]:
            self.start_music()
        else:
            self.stop_music()

    def toggle_sfx(self):
        self.settings["sfx"] = not self.settings["sfx"]


# ---------------------------------------------------------------------------
# Visuals
# ---------------------------------------------------------------------------

def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def make_background():
    surf = pygame.Surface((WIDTH, HEIGHT))
    for y in range(GROUND_TOP):
        pygame.draw.line(surf, lerp_color(SKY_TOP, SKY_BOTTOM, y / GROUND_TOP), (0, y), (WIDTH, y))
    pygame.draw.circle(surf, (255, 245, 180), (820, 80), 52)
    pygame.draw.circle(surf, (255, 230, 120), (820, 80), 42)
    far = [(0, GROUND_TOP)]
    for x in range(0, WIDTH + 40, 40):
        far.append((x, GROUND_TOP - 50 - 30 * math.sin(x / 140) - 15 * math.sin(x / 53)))
    far.append((WIDTH, GROUND_TOP))
    pygame.draw.polygon(surf, HILL_FAR, far)
    near = [(0, GROUND_TOP + 10)]
    for x in range(0, WIDTH + 40, 40):
        near.append((x, GROUND_TOP - 15 - 20 * math.sin(x / 110 + 2)))
    near.append((WIDTH, GROUND_TOP + 10))
    pygame.draw.polygon(surf, HILL_NEAR, near)
    pygame.draw.rect(surf, GROUND, (0, GROUND_TOP, WIDTH, HEIGHT - GROUND_TOP))
    rng = random.Random(3)
    for _ in range(1400):
        x = rng.randrange(WIDTH)
        y = rng.randrange(GROUND_TOP, HEIGHT)
        shade = rng.randint(-20, 20)
        col = (max(0, GROUND[0] + shade), max(0, GROUND[1] + shade), max(0, GROUND[2] + shade))
        h = rng.randint(3, 8)
        pygame.draw.line(surf, col, (x, y), (x + rng.randint(-2, 2), y - h))
    for _ in range(25):
        x = rng.randrange(WIDTH)
        y = rng.randrange(GROUND_TOP + 20, HEIGHT)
        col = rng.choice([(255, 255, 255), (255, 220, 90), (240, 140, 200)])
        pygame.draw.circle(surf, col, (x, y), 3)
        pygame.draw.circle(surf, (255, 240, 120), (x, y), 1)
    return surf


class Cloud:
    def __init__(self, rng, x=None):
        self.x = x if x is not None else -150
        self.y = rng.randint(30, 170)
        self.speed = rng.uniform(8, 22)
        self.blobs = [(rng.randint(-50, 50), rng.randint(-12, 12), rng.randint(20, 36))
                      for _ in range(5)]

    def update(self, dt):
        self.x += self.speed * dt

    def draw(self, surf):
        for dx, dy, r in self.blobs:
            pygame.draw.circle(surf, (255, 255, 255), (int(self.x + dx), int(self.y + dy)), r)


_badge_fonts = {}


def badge_font(size):
    if size not in _badge_fonts:
        _badge_fonts[size] = pygame.font.Font(None, size)
    return _badge_fonts[size]


class Tuft:
    """A clickable thing on the ground: grass, golden grass or a phone."""

    def __init__(self, kind, x, y, life):
        self.kind = kind
        self.x = x
        self.y = y
        self.life = life
        self.age = 0.0
        self.phase = random.uniform(0, 6.28)
        self.scale = 0.85 + (y - GROUND_TOP) / (HEIGHT - GROUND_TOP) * 0.4
        self.blades = [(random.uniform(-18, 18), random.uniform(45, 75), random.uniform(-0.3, 0.3))
                       for _ in range(11)]

    @property
    def radius(self):
        return 44 * self.scale

    @property
    def expired(self):
        return self.age >= self.life

    def hit(self, pos):
        cx, cy = self.x, self.y - 22 * self.scale
        return (pos[0] - cx) ** 2 + (pos[1] - cy) ** 2 <= self.radius ** 2

    def update(self, dt):
        self.age += dt

    def draw(self, surf, t):
        grow = min(1.0, self.age / 0.25)
        wither = max(0.0, (self.age - self.life * 0.6) / (self.life * 0.4))
        s = self.scale * grow
        pygame.draw.ellipse(surf, DIRT, (self.x - 26 * s, self.y - 6 * s, 52 * s, 12 * s))
        if self.kind == "phone":
            self._draw_phone(surf, s, t, wither)
            return
        if self.kind == "golden":
            glow = 0.5 + 0.5 * math.sin(t * 6 + self.phase)
            pygame.draw.circle(surf, lerp_color(GOLD, WHITE, glow),
                               (int(self.x), int(self.y - 25 * s)), int(10 + 6 * glow), 2)
            base_col = lerp_color((255, 220, 70), (170, 140, 60), wither)
            tip_col = lerp_color((255, 250, 180), (190, 160, 90), wither)
        else:
            base_col = lerp_color((40, 140, 40), (140, 120, 60), wither)
            tip_col = lerp_color((130, 220, 90), (190, 170, 100), wither)
        sway = math.sin(t * 2.2 + self.phase) * 6
        droop = wither * 20
        for bx, h, lean in self.blades:
            h *= s * (1 - wither * 0.35)
            base_l = (self.x + bx * s - 4 * s, self.y)
            base_r = (self.x + bx * s + 4 * s, self.y)
            tip = (self.x + bx * s + (lean * 40 + sway) * s + droop * (1 if bx >= 0 else -1),
                   self.y - h + droop * 0.6)
            pygame.draw.polygon(surf, base_col, [base_l, base_r, tip])
            mid = ((base_l[0] + tip[0]) / 2, (base_l[1] + tip[1]) / 2)
            pygame.draw.line(surf, tip_col, mid, tip, 2)
        if self.kind == "golden":
            for i in range(3):
                ang = t * 3 + i * 2.1 + self.phase
                px = self.x + math.cos(ang) * 24 * s
                py = self.y - 30 * s + math.sin(ang) * 14 * s
                pygame.draw.circle(surf, WHITE, (int(px), int(py)), 2)

    def _draw_phone(self, surf, s, t, wither):
        bob = math.sin(t * 4 + self.phase) * 3
        w, h = 30 * s, 52 * s
        rect = pygame.Rect(0, 0, w, h)
        rect.midbottom = (self.x, self.y - 2 + bob)
        pygame.draw.rect(surf, BLACK, rect, border_radius=int(6 * s))
        screen = rect.inflate(-6 * s, -10 * s)
        glow = 0.5 + 0.5 * math.sin(t * 8 + self.phase)
        pygame.draw.rect(surf, lerp_color((60, 120, 220), (150, 200, 255), glow * (1 - wither)), screen,
                         border_radius=int(3 * s))
        for i in range(3):
            y = screen.top + 6 * s + i * 10 * s
            pygame.draw.line(surf, WHITE, (screen.left + 4 * s, y), (screen.right - 4 * s, y), 2)
        pygame.draw.circle(surf, RED, (int(rect.right - 2), int(rect.top + 2)), int(7 * s))
        badge = badge_font(max(12, int(16 * s))).render("99", True, WHITE)
        surf.blit(badge, badge.get_rect(center=(rect.right - 2, rect.top + 2)))


class Particle:
    def __init__(self, x, y, color):
        self.x, self.y = x, y
        self.vx = random.uniform(-160, 160)
        self.vy = random.uniform(-280, -80)
        self.life = random.uniform(0.4, 0.8)
        self.age = 0.0
        self.color = color
        self.size = random.randint(2, 4)

    def update(self, dt):
        self.age += dt
        self.vy += 600 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surf):
        pygame.draw.circle(surf, self.color, (int(self.x), int(self.y)), self.size)


class Popup:
    def __init__(self, text, pos, color, font):
        self.image = font.render(text, True, color)
        self.shadow = font.render(text, True, SHADOW)
        self.x, self.y = pos
        self.age = 0.0
        self.life = 0.9

    def update(self, dt):
        self.age += dt
        self.y -= 50 * dt

    def draw(self, surf):
        alpha = int(255 * max(0.0, 1 - self.age / self.life))
        for img, off in ((self.shadow, 2), (self.image, 0)):
            img.set_alpha(alpha)
            surf.blit(img, img.get_rect(center=(self.x + off, self.y + off)))


def draw_text(surf, font, text, pos, color=WHITE, anchor="center", shadow=True):
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    if shadow:
        sh = font.render(text, True, SHADOW)
        sh.set_alpha(120)
        surf.blit(sh, rect.move(3, 3))
    surf.blit(img, rect)
    return rect


class Button:
    def __init__(self, label, center, action, width=280, height=56):
        self.label = label
        self.rect = pygame.Rect(0, 0, width, height)
        self.rect.center = center
        self.action = action

    def draw(self, surf, font, selected):
        col = (70, 160, 70) if selected else (45, 105, 50)
        pygame.draw.rect(surf, (20, 50, 25), self.rect.move(0, 5), border_radius=14)
        pygame.draw.rect(surf, col, self.rect, border_radius=14)
        pygame.draw.rect(surf, (170, 230, 140) if selected else (90, 150, 90), self.rect, 3,
                         border_radius=14)
        draw_text(surf, font, self.label, self.rect.center)


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

RANKS = [
    (0, "Terminally Online"),
    (300, "Indoor Enthusiast"),
    (700, "Window Gazer"),
    (1200, "Park Visitor"),
    (2000, "Grass Toucher"),
    (3000, "Certified Outdoorsy"),
    (4500, "One With Nature"),
]


def rank_for(score):
    title = RANKS[0][1]
    for threshold, name in RANKS:
        if score >= threshold:
            title = name
    return title


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.settings = load_save()
        self.audio = Audio(self.settings)
        self.background = make_background()
        self.font_big = pygame.font.Font(None, 96)
        self.font_mid = pygame.font.Font(None, 48)
        self.font = pygame.font.Font(None, 36)
        self.font_small = pygame.font.Font(None, 26)
        self.rng = random.Random()
        self.clouds = [Cloud(self.rng, x=self.rng.randint(0, WIDTH)) for _ in range(4)]
        self.time = 0.0
        self.state = "menu"
        self.selected = 0
        self.running = True
        self.menu_tufts = [Tuft("grass", x, self.rng.randint(GROUND_TOP + 60, HEIGHT - 20), 1e9)
                           for x in range(40, WIDTH, 90)]
        for tuft in self.menu_tufts:
            tuft.age = 1.0
        self.reset_round()
        self.build_menu()
        self.audio.start_music()

    # -- setup --------------------------------------------------------------

    def build_menu(self):
        cx = WIDTH // 2
        self.buttons = {
            "menu": [
                Button("Play", (cx, 270), self.start_game),
                Button("How to Play", (cx, 340), lambda: self.goto("howto")),
                Button(self.music_label(), (cx, 410), self.toggle_music),
                Button(self.sfx_label(), (cx, 480), self.toggle_sfx),
                Button("Quit", (cx, 550), self.quit),
            ],
            "howto": [Button("Back", (cx, 540), lambda: self.goto("menu"))],
            "paused": [
                Button("Resume", (cx, 290), lambda: self.goto("playing")),
                Button(self.music_label(), (cx, 360), self.toggle_music),
                Button("Main Menu", (cx, 430), lambda: self.goto("menu")),
            ],
            "gameover": [
                Button("Play Again", (cx - 160, 520), self.start_game),
                Button("Main Menu", (cx + 160, 520), lambda: self.goto("menu")),
            ],
        }

    def music_label(self):
        return "Music: " + ("On" if self.settings["music"] else "Off")

    def sfx_label(self):
        return "Sound FX: " + ("On" if self.settings["sfx"] else "Off")

    def reset_round(self):
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.touched = 0
        self.missed = 0
        self.phones_touched = 0
        self.time_left = ROUND_SECONDS
        self.elapsed = 0.0
        self.spawn_timer = 0.3
        self.tufts = []
        self.particles = []
        self.popups = []
        self.last_hit = -10.0
        self.new_high = False
        self.shake = 0.0

    # -- actions ------------------------------------------------------------

    def goto(self, state):
        self.audio.play("click")
        self.state = state
        self.selected = 0

    def start_game(self):
        self.audio.play("click")
        self.reset_round()
        self.state = "playing"
        self.selected = 0

    def toggle_music(self):
        self.audio.toggle_music()
        write_save(self.settings)
        self.build_menu()

    def toggle_sfx(self):
        self.audio.toggle_sfx()
        self.audio.play("click")
        write_save(self.settings)
        self.build_menu()

    def quit(self):
        self.running = False

    def end_round(self):
        self.state = "gameover"
        self.selected = 0
        self.audio.play("end")
        if self.score > self.settings["high_score"]:
            self.settings["high_score"] = self.score
            self.new_high = True
            write_save(self.settings)

    # -- gameplay -----------------------------------------------------------

    @property
    def multiplier(self):
        return 1 + min(self.combo // 5, 4)

    def spawn(self):
        difficulty = min(1.0, self.elapsed / ROUND_SECONDS)
        roll = self.rng.random()
        if roll < 0.08:
            kind = "golden"
        elif roll < 0.08 + 0.12 + 0.12 * difficulty:
            kind = "phone"
        else:
            kind = "grass"
        for _ in range(20):
            x = self.rng.randint(60, WIDTH - 60)
            y = self.rng.randint(GROUND_TOP + 70, HEIGHT - 20)
            if all((x - t.x) ** 2 + (y - t.y) ** 2 > 90 ** 2 for t in self.tufts):
                break
        else:
            return
        life = lerp(2.6, 1.3, difficulty)
        if kind == "golden":
            life *= 0.7
        elif kind == "phone":
            life *= 1.2
        self.tufts.append(Tuft(kind, x, y, life))

    def burst(self, x, y, color, n=14):
        for _ in range(n):
            self.particles.append(Particle(x, y, color))

    def popup(self, text, pos, color=WHITE):
        self.popups.append(Popup(text, pos, color, self.font))

    def click_field(self, pos):
        for tuft in sorted(self.tufts, key=lambda t: -t.y):
            if tuft.hit(pos):
                self.tufts.remove(tuft)
                self.touch(tuft)
                return

    def touch(self, tuft):
        top = (tuft.x, tuft.y - 50 * tuft.scale)
        if tuft.kind == "phone":
            self.phones_touched += 1
            self.combo = 0
            self.score = max(0, self.score - 50)
            self.shake = 0.3
            self.audio.play("bad")
            self.burst(tuft.x, tuft.y - 20, (80, 140, 230))
            self.popup("-50 Doomscrolling!", top, RED)
            return
        self.combo += 1
        self.best_combo = max(self.best_combo, self.combo)
        self.touched += 1
        if tuft.kind == "golden":
            pts = 50 * self.multiplier
            self.time_left += 2
            self.audio.play("golden")
            self.burst(tuft.x, tuft.y - 20, GOLD, 24)
            self.popup(f"+{pts}  +2s", top, GOLD)
        else:
            pts = 10 * self.multiplier
            self.audio.play("pluck")
            self.burst(tuft.x, tuft.y - 20, (90, 200, 70))
            self.popup(f"+{pts}", top, WHITE)
        self.score += pts
        if self.combo in (5, 10, 15, 20):
            self.popup(f"Combo x{self.multiplier}!", (WIDTH // 2, GROUND_TOP - 40), (180, 255, 150))

    def update_playing(self, dt):
        self.elapsed += dt
        self.time_left -= dt
        if self.time_left <= 0:
            self.time_left = 0
            self.end_round()
            return
        self.spawn_timer -= dt
        if self.spawn_timer <= 0:
            self.spawn()
            difficulty = min(1.0, self.elapsed / ROUND_SECONDS)
            self.spawn_timer = lerp(0.6, 0.3, difficulty) * self.rng.uniform(0.7, 1.3)
        for tuft in self.tufts:
            tuft.update(dt)
        for tuft in [t for t in self.tufts if t.expired]:
            self.tufts.remove(tuft)
            if tuft.kind != "phone":
                self.missed += 1
                self.combo = 0
                self.popup("missed", (tuft.x, tuft.y - 30), (220, 200, 140))
        self.shake = max(0.0, self.shake - dt)

    def update(self, dt):
        self.time += dt
        for c in self.clouds:
            c.update(dt)
        self.clouds = [c for c in self.clouds if c.x < WIDTH + 150]
        if len(self.clouds) < 4 and self.rng.random() < dt * 0.3:
            self.clouds.append(Cloud(self.rng))
        if self.state == "playing":
            self.update_playing(dt)
        for p in self.particles + self.popups:
            p.update(dt)
        self.particles = [p for p in self.particles if p.age < p.life]
        self.popups = [p for p in self.popups if p.age < p.life]

    # -- input --------------------------------------------------------------

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return
        buttons = self.buttons.get(self.state, [])
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_m:
                self.toggle_music()
            elif event.key in (pygame.K_ESCAPE, pygame.K_p) and self.state == "playing":
                self.goto("paused")
            elif event.key == pygame.K_ESCAPE:
                if self.state == "menu":
                    self.quit()
                elif self.state == "paused":
                    self.goto("playing")
                else:
                    self.goto("menu")
            elif buttons and event.key in (pygame.K_UP, pygame.K_w, pygame.K_LEFT, pygame.K_a):
                self.selected = (self.selected - 1) % len(buttons)
            elif buttons and event.key in (pygame.K_DOWN, pygame.K_s, pygame.K_RIGHT, pygame.K_d):
                self.selected = (self.selected + 1) % len(buttons)
            elif buttons and event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                buttons[self.selected].action()
        elif event.type == pygame.MOUSEMOTION:
            for i, b in enumerate(buttons):
                if b.rect.collidepoint(event.pos):
                    self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.state == "playing":
                self.click_field(event.pos)
            else:
                for b in buttons:
                    if b.rect.collidepoint(event.pos):
                        b.action()
                        break

    # -- drawing ------------------------------------------------------------

    def draw_world(self, surf, tufts):
        surf.blit(self.background, (0, 0))
        for c in self.clouds:
            c.draw(surf)
        for tuft in sorted(tufts, key=lambda t: t.y):
            tuft.draw(surf, self.time)
        for p in self.particles:
            p.draw(surf)
        for p in self.popups:
            p.draw(surf)

    def dim(self, surf, alpha=140):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 25, 10, alpha))
        surf.blit(overlay, (0, 0))

    def draw_buttons(self, surf):
        for i, b in enumerate(self.buttons.get(self.state, [])):
            b.draw(surf, self.font, i == self.selected)

    def draw_hud(self, surf):
        bar = pygame.Surface((WIDTH, 56), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 90))
        surf.blit(bar, (0, 0))
        draw_text(surf, self.font, f"Score: {self.score}", (20, 28), anchor="midleft")
        draw_text(surf, self.font, f"Best: {max(self.settings['high_score'], self.score)}",
                  (230, 28), (220, 240, 200), anchor="midleft")
        col = RED if self.time_left < 10 and int(self.time * 4) % 2 == 0 else WHITE
        draw_text(surf, self.font_mid, f"{math.ceil(self.time_left)}", (WIDTH // 2, 30), col)
        if self.combo >= 2:
            draw_text(surf, self.font, f"Combo {self.combo}  x{self.multiplier}",
                      (WIDTH - 20, 28), (180, 255, 150), anchor="midright")
        frac = self.time_left / ROUND_SECONDS
        pygame.draw.rect(surf, (40, 40, 40), (0, 56, WIDTH, 6))
        pygame.draw.rect(surf, lerp_color(RED, (120, 230, 90), frac), (0, 56, int(WIDTH * min(1, frac)), 6))

    def draw_menu(self, surf):
        self.draw_world(surf, self.menu_tufts)
        self.dim(surf, 70)
        bob = math.sin(self.time * 2) * 6
        draw_text(surf, self.font_big, TITLE, (WIDTH // 2, 120 + bob), (230, 255, 200))
        draw_text(surf, self.font_small, "a game about going outside", (WIDTH // 2, 180), (220, 240, 210))
        draw_text(surf, self.font_small, f"High score: {self.settings['high_score']}",
                  (WIDTH // 2, 210), GOLD)
        self.draw_buttons(surf)
        draw_text(surf, self.font_small, "Arrows/Enter or mouse  ·  M: music", (WIDTH - 12, HEIGHT - 14),
                  (230, 240, 230), anchor="bottomright")

    def draw_howto(self, surf):
        self.draw_world(surf, self.menu_tufts)
        self.dim(surf, 170)
        draw_text(surf, self.font_mid, "How to Play", (WIDTH // 2, 80), (230, 255, 200))
        lines = [
            ("Click the grass before it withers:", "+10", WHITE),
            ("Golden grass is rare and quick:", "+50 & +2 sec", GOLD),
            ("Phones are a trap. Don't doomscroll:", "-50 & combo lost", RED),
            ("Every 5 touches in a row raises the multiplier", "up to x5", (180, 255, 150)),
            ("Letting grass wither breaks your combo", "", (220, 200, 140)),
            (f"You have {ROUND_SECONDS} seconds. Go outside!", "", WHITE),
            ("Esc / P pauses   ·   M toggles music", "", (200, 220, 200)),
        ]
        for i, (left, right, col) in enumerate(lines):
            y = 160 + i * 48
            draw_text(surf, self.font, left, (120, y), anchor="midleft")
            if right:
                draw_text(surf, self.font, right, (WIDTH - 120, y), col, anchor="midright")
        demo = [Tuft("grass", 60, 175, 1e9), Tuft("golden", 60, 223, 1e9), Tuft("phone", 60, 271, 1e9)]
        for t in demo:
            t.age = 1.0
            t.scale = 0.6
            t.draw(surf, self.time)
        self.draw_buttons(surf)

    def draw_playing(self, surf):
        self.draw_world(surf, self.tufts)
        self.draw_hud(surf)

    def draw_paused(self, surf):
        self.draw_playing(surf)
        self.dim(surf, 150)
        draw_text(surf, self.font_big, "Paused", (WIDTH // 2, 180))
        self.draw_buttons(surf)

    def draw_gameover(self, surf):
        self.draw_world(surf, self.tufts)
        self.dim(surf, 160)
        draw_text(surf, self.font_big, "Time's up!", (WIDTH // 2, 90), (230, 255, 200))
        draw_text(surf, self.font_mid, f"Score: {self.score}", (WIDTH // 2, 170))
        if self.new_high:
            pulse = 0.5 + 0.5 * math.sin(self.time * 6)
            draw_text(surf, self.font, "NEW HIGH SCORE!", (WIDTH // 2, 215), lerp_color(GOLD, WHITE, pulse))
        else:
            draw_text(surf, self.font, f"High score: {self.settings['high_score']}", (WIDTH // 2, 215), GOLD)
        draw_text(surf, self.font, f"Rank: {rank_for(self.score)}", (WIDTH // 2, 265), (180, 255, 150))
        total = self.touched + self.missed
        acc = 100 * self.touched / total if total else 0
        stats = [
            f"Grass touched: {self.touched}",
            f"Grass missed: {self.missed}  ({acc:.0f}% caught)",
            f"Best combo: {self.best_combo}",
            f"Phones touched: {self.phones_touched}",
        ]
        for i, s in enumerate(stats):
            draw_text(surf, self.font_small, s, (WIDTH // 2, 320 + i * 32), (230, 240, 230))
        self.draw_buttons(surf)

    def draw(self):
        surf = self.screen
        frame = pygame.Surface((WIDTH, HEIGHT))
        getattr(self, "draw_" + self.state)(frame)
        offset = (0, 0)
        if self.shake > 0:
            offset = (self.rng.randint(-6, 6), self.rng.randint(-6, 6))
        surf.fill(BLACK)
        surf.blit(frame, offset)

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(FPS) / 1000, 0.05)
            for event in pygame.event.get():
                self.handle_event(event)
            self.update(dt)
            self.draw()
            pygame.display.flip()
        write_save(self.settings)


def main():
    pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
    pygame.init()
    pygame.display.set_caption(TITLE)
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    icon = pygame.Surface((32, 32), pygame.SRCALPHA)
    for i in range(5):
        x = 6 + i * 5
        pygame.draw.polygon(icon, (60, 170, 60), [(x - 2, 31), (x + 2, 31), (x + (i - 2) * 2, 4 + abs(i - 2) * 4)])
    pygame.display.set_icon(icon)
    loading = pygame.font.Font(None, 40).render("Growing grass...", True, WHITE)
    screen.fill(PANEL)
    screen.blit(loading, loading.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
    pygame.display.flip()
    try:
        pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
    except pygame.error:
        pass
    Game(screen).run()
    pygame.quit()


if __name__ == "__main__":
    main()
