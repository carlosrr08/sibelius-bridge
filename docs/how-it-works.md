# How sibelius-bridge works

The bridge has three layers. Layer A edits the score through a plugin. Layer B drives the parts of the Sibelius interface that no plugin can reach. Layer C reads back what Sibelius exports, so every change is checked against the real output.

```
            Claude (Claude Code or any MCP client: shell, screenshots, image reading)
                 |                         |                          ^
   A. score edits (plugin)     B. interface automation      C. seeing and measuring
   sib -> io/cmd.txt           gui/act.sh + click.swift     PDF -> PNG, bar maps,
   keystroke ctrl+opt+cmd+B    screenshots, clicks, keys    WAV + MIDI -> clicktrack.py
                 |                         |                          |
           Sibelius 2020.6 (ClaudeBridge plugin, Mixer, Performance, Export pages)
```

## Layer A: score edits through the plugin

ManuScript is the only way to program Sibelius 2020. A plugin can read and change almost everything layout needs: breaks, parts, Document Setup, Engraving Rules, text, object positions and PDF export. Its limits decided the design:

- it has no network access;
- it has no timer or background loop, so it cannot wait for commands;
- it has no `eval`, so it cannot run code sent from outside;
- it starts only from the menu or a keyboard shortcut;
- its changes cannot be undone in Sibelius.

It can read and write files. The bridge is therefore a file mailbox plus a keyboard shortcut.

### The mailbox

| File | Written by | Meaning |
|---|---|---|
| `io/cmd.txt` | `sib` | the commands, one per line, fields separated by `\|` |
| `io/result.txt` | plugin | the output, line by line |
| `io/done.txt` | plugin, last | `result.txt` is complete |

One round trip, for example `./sib 'map|3'`:

1. `sib` deletes the old `result.txt` and `done.txt` and writes `cmd.txt`, converted to Latin-1 because ManuScript reads plain text in that encoding.
2. It remembers which app is in front, brings Sibelius forward and waits until Sibelius really is frontmost with a window, plus 0.8 s. When Sibelius runs full screen in its own Space, macOS takes about a second to switch, and a shortcut sent earlier goes to the wrong app.
3. It presses ctrl+opt+cmd+B.
4. The plugin starts, creates `result.txt`, reads `cmd.txt` and deletes it. The deletion is the signal that the shortcut worked. If `cmd.txt` is still there after about 5 s, `sib` presses again, up to 3 times, and then stops with "plugin did not start". That error has always meant an open dialog or an unassigned shortcut.
5. For each line the plugin writes `> command` into the result and runs it.
6. It writes `done.txt` last, so a half-written result is never read.
7. `sib` sees `done.txt`, switches back to the app that was in front, prints the result as UTF-8 and exits with 1 if any line starts with `error|`.

Several commands in one call run in one plugin pass. Exporting a full score and 34 part PDFs took one shortcut press and 10 seconds.

### Inside the plugin

`Run` reads the lines and hands each one to `Dispatch`, which splits it on `|` through `Arg(f, i)`, a helper that returns an empty string instead of failing on a missing field. Commands come in two kinds:

- score-level: `info`, `parts`, `scoreinfo`, `save`;
- part-scoped: the second field is a part number, 0 being the full score. The plugin sets `score.CurrentDynamicPart` first, because ManuScript edits one part at a time, and restores the original part afterwards so the view does not jump.

`map` is the core of layout work. With a part selected, `Bar.OnNthPage` and `Bar.OnNthSystem` give where each bar lands in that part's own layout, and the note count per bar shows where the rests are, which is what page turns need.

### Install, reload, undo

- `sib install` puts the absolute path of the mailbox into the plugin source, converts the file to UTF-16LE with a byte-order mark (the format of Sibelius's own plugins) and copies it to `~/Library/Application Support/Avid/Sibelius/Plugins/Claude/`.
- Sibelius loads plugins only at startup. `sib reload` saves the score, installs the plugin, quits Sibelius, reopens the same file and runs `info`.
- Plugin edits cannot be undone, so a numbered copy is saved before each pass with `save|/path/versions/NN.sib`. `SaveCopyAs` leaves the name of the working file unchanged.

### Sibelius behaviour found on the way

- Page breaks in the full score are inherited by the parts as system breaks. Setting `none` in a part only falls back to the inherited break; `NotEndOfSystem` suppresses it. Without that, a multirest in a part can be split by a break the part never asked for.
- Hairpins are `CrescendoLine` and `DiminuendoLine` objects, not plain `Line` objects.
- `to`, `from` and `type` cannot be used as variable names. A plugin that uses them fails at runtime with a dialog that blocks Sibelius until it is closed, and `sib` then times out.
- In Sibelius the zoom level is relative to the staff size, so changing the staff size also changes what is visible on screen.

## Layer C: seeing the result

Claude cannot watch Sibelius live, so every change is checked in two ways.

- **Numbers.** `map` for every part gives a table per bar. A short script turns it into pages, systems per page and bar ranges, and flags problems such as a multirest split at the end of a system.
- **Pictures.** `pdf` exports the score and parts; `pdftoppm` renders the pages as PNG and the pages are combined into contact sheets that Claude reads as images. This caught dynamics colliding with lyrics in choir parts, a "sim." touching a lyric syllable, and a crushed last page in a full score.

The working loop is: map the parts, decide the changes against `layout-rules.md`, apply them, map again, export, look, fix. On a 34-part orchestral arrangement the loop ran about ten times.

## Layer B: the interface outside the plugin's reach

The reverb preset (Play > Performance), the Mixer's solo buttons and the Audio and MIDI export pages have no ManuScript API in Sibelius 2020. Claude works them the way a person does, with a check after every step:

1. Take a screenshot with `screencapture` and read it.
2. Convert the target position into fractions of the screen.
3. Act through `gui/act.sh`, which brings Sibelius to the front and refuses to act when any other app is frontmost. `click` posts a real mouse click through `click.swift`; `keys` sends keystrokes or menu clicks through System Events; `drag.swift` sends a drag (used to enlarge the Mixer when it opens without its solo buttons).
4. Take a new screenshot and confirm the result, for example "Dry" in the reverb menu or a lit solo button on the click strip.

Rules for this layer: never press Return on an unknown dialog (reopening an open score asks whether to discard its changes, with Yes as the default); clear the selection before an audio export, because Sibelius otherwise exports only the selected staves; and move intermediate files out of the user's folders immediately.

## The click pipeline: clicktrack.py

Sibelius's own click export, rendered by NotePerformer 3.3.2, was measured on eight scores:

- it is never dry: the woodblock rings for about 0.4 s, and Dry and Cathedral reverb exports decay identically, so the ring belongs to the sample;
- it jitters: clicks land up to 18 to 20 ms off the beat, with a standard deviation of about 8 ms;
- it is late and padded: every attack comes about 30 ms late, after a fixed 1.000 s lead-in.

`clicktrack.py raw.wav score.mid out.wav` rebuilds the click from the audio export (only the click soloed) and a MIDI export of the same score, from which it uses only the tempo and time-signature events.

1. **Load** the 24-bit WAV and raise it to -1 dBFS, whatever the click fader was set to.
2. **Read the MIDI** with a small parser. When several events share a tick, the last one wins; this matters for metric modulations and for tempo marks that sit just after beat 1.
3. **Build the tempo map**, converting between ticks and seconds in both directions, clamped at the start (a click estimated at -9 ms once wrapped around to the end of a piece).
4. **Find the bar starts** from the time signatures, including bars such as 33/32.
5. **Find every click**: wherever the level jumps 2.5 times above the previous 20 ms. The attack is the first sample above 20 % of the hit's peak.
6. **Classify** each click from its first 30 ms: above 1150 Hz it is the accent (high woodblock, about 1300 Hz); otherwise it is the low woodblock (about 950 Hz), a beat, or a soft click when it is more than 7 dB quieter.
7. **Snap the loud clicks to the grid.** Each click's position is estimated from the tempo map minus the lead-in and NotePerformer's delay (starting at 30 ms, refined three times by median) and rounded to the eighth-note grid of its bar. A 32nd grid was tried first, but at a dotted quarter of 130 a 32nd lasts only 38 ms, so 20 ms of jitter can pick the wrong one. Clicks that fit no eighth within 25 ms, as in odd bars, fall back to the 32nd grid. The script stops if any click is still more than 25 ms off, if two clicks land on one position, or if the accents do not match the MIDI bar starts.
8. **Find the soft clicks.** With "Subdivide beats" on, Sibelius adds soft clicks on every eighth in compound meters and on the inner beats of irregular groups. Most of them are buried under the ring of the previous click, so a loudness detector misses them. A probe measures the new energy above 1.5 kHz that appears within ±20 ms of each candidate eighth: a decaying ring only loses energy, and a new hit adds some even under the ring. The sixteenth before each candidate is probed as a control, because Sibelius never clicks there. One probe alone is too weak, but the pattern is fixed per meter, so all candidates with the same meter, group length and position decide together: a median at least 0.45 above the control means a soft click in every bar of that class, 0.15 or less means none, and anything between stops the script with "ambiguous, check by ear".
9. **Build the hits**: one accent, one beat and, if needed, one soft click are cut from Sibelius's own export, 2 ms before to 60 ms after the attack, with a 2 ms fade-in and a 25 ms fade-out.
10. **Render**: every hit is placed at exactly 1.000 s plus its tempo-map time, rounded to the sample, over silence and at the length of the original export, so the click lines up with any audio exported from the same score.
11. **Check the output**: the written file is loaded and analysed again. It must contain the same number of clicks, each within 2 samples of its target, with the same accent, beat and soft pattern, and digital silence between clicks.

After each change to the method, the earlier scores were processed again and compared with the files already delivered; they came out bit-identical, or the change was explained. `tests/test_clicktrack.py` keeps that guarantee for the future with a simulated export that has the ring, the delay, drifting jitter and buried soft eighths in 6/8.

## Limits

- It works only where a shell can run `sib` (Claude Code, or an MCP client through `mcp_server.py`).
- Sibelius must stay in front while a command runs, and any open dialog blocks the plugin.
- New capabilities need a new command in the plugin and a restart of Sibelius.
- Interface steps depend on the screen layout (full screen and windowed differ), so Claude takes a new screenshot before every click instead of reusing coordinates.

On Sibelius 2024.3 or later, Sibelius Connect could start plugin methods directly over a WebSocket. That would replace the keyboard shortcut and let the bridge run in the background; everything else would carry over.
