#!/usr/bin/env python3
"""Write examples/demo-chorale.musicxml: a 32-bar string-quartet chorale (original material, CC0)
for trying the bridge without touching your own scores. Open it in Sibelius (File > Open)."""
import os

PARTS = [  # id, name, MIDI program, clef sign/line
    ('P1', 'Violin I', 41, 'G', 2), ('P2', 'Violin II', 41, 'G', 2),
    ('P3', 'Viola', 42, 'C', 3), ('P4', 'Violoncello', 43, 'F', 4)]
CHORDS = {  # root, third, fifth as MIDI numbers in the octave above middle C
    'C': (60, 64, 67), 'Am': (69, 72, 76), 'F': (65, 69, 72), 'G': (67, 71, 74), 'Dm': (62, 65, 69),
    'E': (64, 68, 71), 'Em': (64, 67, 71)}
FORM = ['C', 'Am', 'F', 'G', 'C', 'F', 'G', 'C',          # A
        'C', 'Em', 'F', 'C', 'Dm', 'G', 'G', 'C',         # A'
        'Am', 'Dm', 'E', 'Am', 'F', 'Dm', 'E', 'E',       # B
        'C', 'Am', 'F', 'G', 'C', 'F', 'G', 'C']          # A''
MARKS = {9: 'A', 17: 'B', 25: 'C'}
STEPS = ['C', 'C', 'D', 'D', 'E', 'F', 'F', 'G', 'G', 'A', 'A', 'B']


def note(midi, beats):
    step, alter = STEPS[midi % 12], 1 if midi % 12 in (1, 3, 6, 8, 10) else 0
    kind = {1: 'quarter', 2: 'half', 4: 'whole'}[beats]
    return (f'<note><pitch><step>{step}</step>{"<alter>1</alter>" if alter else ""}<octave>{midi // 12 - 1}</octave></pitch>'
            f'<duration>{beats}</duration><type>{kind}</type></note>')


def bar_notes(part, chord, bar):
    r, t, f = CHORDS[chord]
    cadence = bar % 8 == 0
    if part == 'P1':
        if cadence:
            return [(r + 12, 4)]
        shape = [(t, f, r + 12, f), (f, r + 12, t + 12, r + 12), (r + 12, t + 12, f, t)][(bar // 8) % 3]
        return [(p, 1) for p in shape]
    if part == 'P2':
        return [(t, 4)] if cadence else [(t, 2), (f, 2)]
    if part == 'P3':
        return [(f - 12, 4)] if cadence else [(f - 12, 2), (r - 12 + (0 if r - 12 >= 48 else 12), 2)]
    return [(r - 24, 4)]


def main():
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="no"?>',
           '<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
           '"http://www.musicxml.org/dtds/partwise.dtd">',
           '<score-partwise version="3.1"><work><work-title>Demo Chorale</work-title></work>',
           '<identification><creator type="composer">sibelius-bridge</creator><rights>CC0</rights></identification>',
           '<part-list>']
    for pid, name, prog, _, _ in PARTS:
        out.append(f'<score-part id="{pid}"><part-name>{name}</part-name><score-instrument id="{pid}-I1">'
                   f'<instrument-name>{name}</instrument-name></score-instrument><midi-instrument id="{pid}-I1">'
                   f'<midi-program>{prog}</midi-program></midi-instrument></score-part>')
    out.append('</part-list>')
    for pid, _, _, sign, line in PARTS:
        out.append(f'<part id="{pid}">')
        for bar, chord in enumerate(FORM, 1):
            out.append(f'<measure number="{bar}">')
            if bar == 1:
                out.append('<attributes><divisions>1</divisions><key><fifths>0</fifths></key><time><beats>4</beats>'
                           f'<beat-type>4</beat-type></time><clef><sign>{sign}</sign><line>{line}</line></clef></attributes>')
                if pid == 'P1':
                    out.append('<direction placement="above"><direction-type><metronome><beat-unit>quarter</beat-unit>'
                               '<per-minute>96</per-minute></metronome></direction-type><sound tempo="96"/></direction>')
            if pid == 'P1' and bar in MARKS:
                out.append(f'<direction placement="above"><direction-type><rehearsal>{MARKS[bar]}</rehearsal>'
                           '</direction-type></direction>')
            out += [note(p, d) for p, d in bar_notes(pid, chord, bar)]
            if bar == len(FORM):
                out.append('<barline location="right"><bar-style>light-heavy</bar-style></barline>')
            out.append('</measure>')
        out.append('</part>')
    out.append('</score-partwise>')
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'demo-chorale.musicxml')
    with open(path, 'w') as f:
        f.write('\n'.join(out) + '\n')
    print(f'wrote {path}: {len(PARTS)} parts, {len(FORM)} bars')


if __name__ == '__main__':
    main()
