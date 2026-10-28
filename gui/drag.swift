import Cocoa
// usage: drag.swift fx1 fy1 fx2 fy2 (fractions of the main screen)
let a = CommandLine.arguments.dropFirst().map { Double($0)! }
let f = NSScreen.screens[0].frame
let p1 = CGPoint(x: f.width * a[0], y: f.height * a[1]), p2 = CGPoint(x: f.width * a[2], y: f.height * a[3])
func post(_ t: CGEventType, _ p: CGPoint) { CGEvent(mouseEventSource: nil, mouseType: t, mouseCursorPosition: p, mouseButton: .left)!.post(tap: .cghidEventTap); usleep(30000) }
post(.leftMouseDown, p1)
for i in 1...20 { let k = Double(i) / 20; post(.leftMouseDragged, CGPoint(x: p1.x + (p2.x - p1.x) * k, y: p1.y + (p2.y - p1.y) * k)) }
post(.leftMouseUp, p2)
print("drag \(p1) -> \(p2)")
