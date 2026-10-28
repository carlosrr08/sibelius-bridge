import Cocoa
// usage: click.swift fx fy [double]  (fractions of the main screen)
let a = CommandLine.arguments
let f = NSScreen.screens[0].frame
let p = CGPoint(x: f.width * Double(a[1])!, y: f.height * Double(a[2])!)
let n = a.count > 3 ? 2 : 1
for i in 1...n {
  for t in [CGEventType.leftMouseDown, .leftMouseUp] {
    let e = CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)!
    e.setIntegerValueField(.mouseEventClickState, value: Int64(i))
    e.post(tap: .cghidEventTap)
    usleep(60000)
  }
}
print("click \(p)")
