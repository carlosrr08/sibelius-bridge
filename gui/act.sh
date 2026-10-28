#!/bin/bash
# act.sh click fx fy | act.sh keys "<applescript key statements>" : only acts when Sibelius is frontmost
S=$(dirname "$0")
front=$(osascript <<'A'
tell application "Sibelius" to activate
tell application "System Events"
  repeat 30 times
    if frontmost of process "Sibelius" then exit repeat
    delay 0.1
  end repeat
  delay 0.4
  return name of first process whose frontmost is true
end tell
A
)
[[ "$front" == "Sibelius" ]] || { echo "ABORT: frontmost is $front"; exit 1; }
case "$1" in
  click) swift "$S/click.swift" "$2" "$3" | tail -1 ;;
  keys)  osascript -e "tell application \"System Events\"" -e "$2" -e "end tell" ;;
esac
sleep 1
