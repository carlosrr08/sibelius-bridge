# Sibelius bridge

Lets Claude do layout and part editing in Sibelius 2020.6 (no Sibelius Connect before 2024.3).
Personal paths and project notes: `CLAUDE.local.md` (not in git).
`ClaudeBridge.plg` is a ManuScript plugin; `sib` writes commands to `io/cmd.txt`, presses the
plugin's keyboard shortcut in Sibelius, and prints `io/result.txt`.

## One-time setup

1. `./sib install`, then restart Sibelius.
2. Sibelius > Preferences > Keyboard Shortcuts: the built-in set is read-only, so first
   Add Feature Set (based on Standard). Then Plug-ins > Claude Bridge > Add: ctrl+opt+cmd+B.
   Another key works too: set `SIB_KEY` / `SIB_MODS`.
3. System Settings > Privacy & Security > Accessibility: allow the app that runs `sib` (Terminal,
   Claude, your MCP client) to press the shortcut. Screen Recording too, for screenshots.
4. First run shows "plug-ins cannot be undone": tick "don't say this again".

## Commands

One per line or argument, fields split by `|`. `P` = part index from `parts` (0 = full score).
Bars are internal bar numbers (1, 2, 3 ... regardless of bar number changes).

| command | does |
|---|---|
| `info` | title, file, bar/staff/part counts |
| `parts` | idx, name, staves, pages, staff size, page size, multirests |
| `map\|P[\|from\|to]` | per bar: page, system, position, break, multirest, notes (count of chords/notes the part plays), rehearsal mark |
| `break\|P\|bars\|type` | bars `4,8,12` or `1-40` or mixed; type `system`, `page`, `none`, `MiddleOfSystem`, `MiddleOfPage`, `NotEndOfSystem`, `SpecialPageBreak` or 1-8 |
| `setup\|P[\|Key=val,...]` | read or set Document Setup (mm): PageSize, Orientation, PageWidth, PageHeight, StaffSize, MarginType, Page*Margin, AboveTopStaveGap, BelowBottomStaveGap |
| `optimize\|P[\|from\|to]` | Layout > Optimize Staff Spacing |
| `multirests\|P\|0/1` | Show Multirests |
| `split\|P\|bars\|0/1` | split multirest at bars |
| `show\|P` | display that part in Sibelius |
| `pdf\|P\|/abs/path.pdf` | export score (P=0) or one part as PDF |
| `save[\|/abs/path.sib]` | save, or save a copy without switching to it |
| `rules\|P[\|Key=val,...]` | Engraving Rules (spaces): SpacesBetweenStaves, SpacesBetweenSystems, StaffJustificationPercentage, ExtraSpaceBetweenGroupsOfStaves, ExtraSpacesBelowVocalStaves |
| `resetspace\|P` | Layout > Reset Space Above/Below Staff, all staves of P |
| `resetpos\|P` | Layout > Reset Position on staff text, lines and hairpins of P |
| `dynabove\|P\|textDy\|hairpinDy` | vocal parts: Expression text + hairpins above the staff (1/32 spaces from middle line; 104/112 or 84/92) |
| `nudge\|P\|bar\|style\|dx\|dy` | move staff text of that style in that bar (1/32 spaces, dy up) |
| `hideempty\|P\|staves\|from\|to` / `showempty...` | hide/show empty staves (staff numbers from `staves`) in a bar range |
| `staves\|P` | staff numbers and names |
| `texts\|P` | system + staff text (bar, style, text) and hairpins |
| `replacetext\|P\|find\|repl` / `deltext\|P\|exact` | edit or delete text by content |
| `settext\|P\|style\|text` | set system text by style name (wildcards like `\$TITLE\` work; empty deletes) |
| `scoreinfo[\|Key=val,...]` | File > Score Info: Title, Subtitle, Composer, Arranger, Copyright |

Several commands in one `sib` call run in one plugin pass (faster).
`InMultirest` in `map`: 0 none, 1 starts, 2 ends, 3 middle.

## Working rules

- Never touch the original score. Copy it into a work folder, `open -a Sibelius copy.sib`.
- Plugin changes cannot be undone in Sibelius: `save|<work>/versions/NN.sib` before each pass.
- Loop per part: `map` -> decide breaks against `layout-rules.md` -> `break`/`optimize` ->
  `pdf` -> read the PDF pages -> fix -> repeat. Report rule violations that could not be fixed.
- Sibelius must stay frontmost while `sib` runs; the user should not type into it meanwhile.
- Editing `ClaudeBridge.plg`: `./sib reload` (saves, installs, restarts Sibelius on the same score).
- ManuScript gotchas: `to`/`type` are not usable as names; method bodies use single-quoted strings;
  hairpins are `CrescendoLine`/`DiminuendoLine`, not `Line`; a runtime error opens a modal
  message in Sibelius and `sib` then times out (screenshot to see it).
- Score page breaks are inherited by parts as system breaks. `break|P|n|none` falls back to that
  inherited break; use `NotEndOfSystem` to really suppress a break in a part (else multirests split).
- System spacing in single-staff parts is `rules SpacesBetweenSystems`; `optimize` does not fix
  lyric collisions between systems. Choir parts: `dynabove` + staff 6.5 mm + gap 12-14.
- Run multi-word shell loops in bash syntax carefully: the shell is zsh (no word splitting of $var).

## Audio / click export (NotePerformer 3.3.2)

- Reverb, mixer, click and audio export have no ManuScript API: drive the GUI (screenshot +
  `gui/act.sh click fx fy` / `gui/act.sh keys '<System Events statements>'`, `gui/drag.swift`; Play > Performance > Reverb "Dry", Mixer click strip Solo,
  File > Export > Audio, File > Export > MIDI). Only click when Sibelius is frontmost.
- Re-opening an already open score asks "open the previous version and lose your changes?"
  with Yes as default: answer No. Switch scores via the Window menu instead.
- NotePerformer's click woodblock rings ~0.4 s whatever the reverb preset and jitters +-18 ms;
  exports start with a 1.000 s lead-in and attacks ~30 ms late.
- Sibelius' click (prefs: Subdivide beats + Stress irregular beat groups) adds soft clicks:
  every eighth in compound meters (6/8, 12/8), beats 2,3,5,6 in 6/4. Most hide under the ring.
- Dry click: `python3 clicktrack.py raw.wav score.mid out.wav` (raw = audio export with the click
  soloed, mid = MIDI export of the same score). Keeps every click Sibelius plays, finds soft
  ones per meter class with a spectral-flux probe, places all on the exact tempo-map grid, and
  verifies the written file.
- Subdivide beats is a per-score click setting: one 12/8 score can subdivide, another not.
- Clear any selection before Export > Audio (Esc), or Sibelius exports only the selected staves.
- A metronome mark attached after beat 1 (MIDI tempo event at tick > 0) makes Sibelius play the
  first beat at its default tempo: the click keeps that, flag it to the user.
- Full-screen Sibelius has no title bar, so every ribbon position shifts: take a fresh screenshot
  before each click, never reuse coordinates.

## MCP

`mcp_server.py` exposes `sib` and `clicktrack.py` as MCP tools over stdio (stdlib only).
Tests: `python3 tests/test_clicktrack.py` and `python3 tests/test_mcp_server.py` (no Sibelius needed).
