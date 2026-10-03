# touchgrass
A game where you touch grass with a score, for Windows and Linux.

Grass sprouts all over a sunny field. Click it before it withers! Golden grass
is worth more and gives you extra time. Phones are a trap: touching one means
you're doomscrolling, which costs points and breaks your combo.

## Features
- **Main menu**: Play, How to Play, Music and Sound FX toggles, Quit (mouse or keyboard)
- **Music**: an original chiptune loop, generated in code when the game starts
- **Score system**: points, a combo multiplier (up to x5), a 60-second timer, an end-of-round
  rank and stats, and a saved high score
- **Pause menu** (Esc / P), music toggle (M)

Everything (graphics, music, sound effects) is generated in code, so there are no asset files.
Settings and high score are saved to `%APPDATA%\TouchGrass\save.json` on Windows
(`~/.local/share/TouchGrass/save.json` on Linux).

## Play
**Download:** grab `TouchGrass.exe` from the latest
[GitHub Actions build](../../actions/workflows/build.yml) (artifact *TouchGrass-Windows*) or from
a release. Then just double-click it.

**From source** (Python 3.9+):
```
pip install -r requirements.txt
python touchgrass.py
```

## Build the .exe yourself (Windows)
Double-click `build.bat` (or run it from a terminal). It installs
[pygame-ce](https://pyga.me/) and [PyInstaller](https://pyinstaller.org/) and writes
`dist\TouchGrass.exe`. On Linux, run `./build.sh`.

Pushing a tag like `v1.0` makes the workflow attach the Windows and Linux builds to a GitHub release.

## Controls
| Action | Input |
| --- | --- |
| Touch grass | Left click |
| Menu navigation | Mouse, or Arrows/WASD + Enter/Space |
| Pause | Esc or P |
| Toggle music | M |

# AI Disclaimer
## It's entirely vibecoded by Claude Code and is reviewed and tested by a human.
