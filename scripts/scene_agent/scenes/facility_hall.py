"""A facility-scale laboratory hall, as scene-agent source.

This is the reference the library was built against: a 13 x 22 x 4 m hall holding a synthesis line
of seven fume hoods, a gantry with three arms over four workbenches of plate hotels, five
characterisation bays, a consumables run under a glazed wall, a control station, and a transport
robot on a marked lane. 448 mesh nodes.

It exists for two reasons. It is the standing regression case for `prelude.py`, because every helper
that room-scale work needed was found by rendering this and looking at it. And it is the shape a
facility-scale twin arrives in: `export_scene` turns it into GLB plus digest plus a draft
`twin.yaml` that `opensdl twin validate` accepts, which is the handoff D14 requires and the one that
has to work before any domain-specific buildout is worth starting.

The camera is deliberate rather than fitted. `frame_all` would retreat outside the room to see the
whole hall; an establishing shot from inside it wants the near four metres of floor empty, which is
a composition decision the framing check cannot make.
"""

from __future__ import annotations

#: The scene, as a script for `render_script` or `export_scene`. Both inject `prelude.PRELUDE`
#: ahead of it, so every helper called here is defined there.
SOURCE = r"""
scene = new_scene(); p = palette()
floor = tiled('floor', colour=(0.42,0.41,0.40), grout=(0.30,0.295,0.29), tile=0.60)
wall  = material('wall', (0.55,0.555,0.565), 0.80)
ceil  = material('ceil', (0.58,0.58,0.59), 0.85)
st    = material('steel', (0.52,0.53,0.55), 0.16, 1.0)
al    = material('alu',   (0.50,0.51,0.525), 0.34, 1.0)
dark  = material('dark',  (0.085,0.085,0.095), 0.55)
glass = material('glass', (0.62,0.70,0.72), 0.06)
amber = material('amber', (0.85,0.52,0.10), 0.45)
sig   = material('signal',(0.15,0.55,0.35), 0.40)
warn  = material('warn',  (0.72,0.16,0.14), 0.45)

W, D, H = 13.0, 22.0, 4.0
shell = room(width=W, depth=D, height=H, floor_material=floor, wall_material=wall,
             ceiling_material=ceil, open_side='front', glazed='right')
LX, RX = -W/2 + 0.55, W/2 - 0.50

# ---------------------------------------------------------------- synthesis line, left wall
for i in range(7):
    y = -5.6 + i*2.55
    box('Hood%d_Body' % i, (1.05, 2.30, 2.55), (LX, y, 1.28), al)
    box('Hood%d_Void' % i, (0.80, 2.05, 1.05), (LX+0.16, y, 1.42), dark)
    box('Hood%d_Sash' % i, (0.05, 2.05, 0.72), (LX+0.53, y, 1.80), glass)
    box('Hood%d_Deck' % i, (0.86, 2.10, 0.05), (LX+0.14, y, 0.885), st)
    box('Hood%d_Panel'% i, (0.05, 0.52, 0.26), (LX+0.55, y-0.72, 1.06), dark)
    box('Hood%d_Lamp' % i, (0.04, 0.10, 0.08), (LX+0.57, y-0.86, 1.06), sig)
    box('Hood%d_Duct' % i, (0.34, 0.34, 1.45), (LX, y, 3.28), al)
box('DuctSpine', (0.42, 18.6, 0.42), (LX, 1.9, 3.86), al)

# ---------------------------------------------------------------- robot aisle, left of centre
box('RailBeam', (0.30, 14.0, 0.22), (-2.55, 2.4, 1.30), al)
for i in range(4):
    y = -4.0 + i*4.0
    box('RailPost%d' % i, (0.22, 0.22, 1.20), (-2.55, y, 0.60), al)
for a in range(3):
    y = -3.2 + a*4.6
    box('Arm%d_Base'  % a, (0.40, 0.40, 0.22), (-2.55, y, 1.52), dark)
    cylinder('Arm%d_Turret' % a, 0.17, 0.28, (-2.55, y, 1.75), amber)
    box('Arm%d_Shoulder'%a,(0.24, 0.24, 0.20), (-2.55, y, 1.99), dark)
    box('Arm%d_Link1' % a, (0.15, 0.15, 0.80), (-2.42, y, 2.45), amber)
    box('Arm%d_Elbow' % a, (0.19, 0.19, 0.19), (-2.42, y, 2.88), dark)
    box('Arm%d_Link2' % a, (0.13, 0.78, 0.13), (-2.42, y+0.44, 2.88), amber)
    box('Arm%d_Wrist' % a, (0.15, 0.15, 0.16), (-2.42, y+0.86, 2.86), dark)
    box('Arm%d_Grip'  % a, (0.05, 0.05, 0.20), (-2.42, y+0.86, 2.70), st)
    box('Arm%d_Jaw'   % a, (0.11, 0.03, 0.10), (-2.42, y+0.86, 2.57), st)

# workbenches under the rail, each carrying plate hotels
for b in range(4):
    y = -4.2 + b*4.0
    box('Bench%d_Top' % b, (1.55, 2.90, 0.06), (-1.30, y, 0.90), st)
    box('Bench%d_Skirt'%b, (1.42, 2.78, 0.62), (-1.30, y, 0.55), al)
    for L in range(6):
        box('Hotel%d_%d' % (b,L), (1.02, 0.62, 0.035), (-1.30, y+1.05, 1.03 + L*0.30), st)
        box('Plate%d_%d' % (b,L), (0.86, 0.52, 0.075), (-1.30, y+1.05, 1.085 + L*0.30),
            [p['labware'], p['crate'], p['glass']][L % 3])
    box('Bench%d_Frame'%b, (0.05, 0.05, 1.90), (-1.81, y+1.05, 1.85), al)
    box('Bench%d_Frame2'%b,(0.05, 0.05, 1.90), (-0.79, y+1.05, 1.85), al)

# ---------------------------------------------------------------- characterisation line, right of centre
NAMES = ('XRD', 'Raman', 'SEM', 'DSC', 'GC')
for i, nm in enumerate(NAMES):
    y = -0.6 + i*4.15
    box('%s_Cab' % nm,   (1.45, 2.45, 2.05), (2.15, y, 1.03), al)
    box('%s_Face' % nm,  (0.06, 2.05, 1.50), (1.44, y, 1.28), dark)
    box('%s_Door' % nm,  (0.05, 0.95, 0.88), (1.40, y-0.38, 1.26), glass)
    box('%s_Screen' % nm,(0.05, 0.58, 0.38), (1.39, y+0.66, 1.64), sig)
    box('%s_Vent' % nm,  (1.20, 0.55, 0.22), (2.15, y, 2.19), al)
    box('%s_Rear' % nm,  (0.05, 2.05, 1.60), (2.86, y, 1.20), dark)
    for g in range(5):
        box('%s_Fin%d' % (nm,g), (0.06, 1.70, 0.07), (2.89, y, 0.62 + g*0.30), al)
    box('%s_Cond' % nm,  (0.10, 0.10, 1.95), (2.94, y+1.15, 1.00), al)
    box('%s_Foot' % nm,  (1.50, 2.50, 0.09), (2.15, y, 0.045), dark)
    box('%s_Front' % nm, (1.30, 0.05, 1.35), (2.15, y-1.24, 1.20), dark)
    box('%s_Band' % nm,  (1.36, 0.05, 0.20), (2.15, y-1.26, 1.98), amber)
    box('%s_Grille'% nm, (1.05, 0.05, 0.42), (2.15, y-1.26, 0.42), al)
    for k in range(3):
        box('%s_Led%d' % (nm,k), (0.04, 0.07, 0.07), (1.38, y+0.56, 1.08 - k*0.14),
            [sig, amber, warn][k])

# ---------------------------------------------------------------- consumables run, under the glazing
box('RTop', (0.85, 15.0, 0.06), (RX, 1.4, 0.92), st)
for i in range(12):
    box('RCab%d' % i, (0.78, 1.36, 0.84), (RX, -5.6 + i*1.42, 0.44), al)
    box('RHandle%d'%i, (0.03, 0.72, 0.035), (RX-0.42, -5.6 + i*1.42, 0.70), dark)
for j in range(16):
    m = [p['crate'], p['labware'], p['timber'], p['copper'], p['glass']][j % 5]
    box('RBox%d' % j, (0.50, 0.60, 0.30), (RX-0.04, -5.4 + j*1.06, 1.10), m)

# ---------------------------------------------------------------- control station, far wall
box('RackA', (1.05, 1.00, 2.20), (-3.4, D/2-0.85, 1.10), dark)
box('RackB', (1.05, 1.00, 2.20), (-2.25, D/2-0.85, 1.10), dark)
for r in range(11):
    box('RackA_U%d' % r, (0.95, 0.05, 0.13), (-3.4, D/2-1.37, 0.30 + r*0.17), al)
    box('RackB_U%d' % r, (0.95, 0.05, 0.13), (-2.25, D/2-1.37, 0.30 + r*0.17), al)
    box('RackA_L%d' % r, (0.06, 0.03, 0.04), (-3.78, D/2-1.40, 0.30 + r*0.17), sig)
    box('RackB_L%d' % r, (0.06, 0.03, 0.04), (-2.63, D/2-1.40, 0.30 + r*0.17), amber)
box('DeskTop', (4.6, 0.85, 0.06), (0.6, D/2-0.70, 0.76), st)
for i, x in enumerate((-1.5, 0.6, 2.7)):
    box('Mon%d' % i, (1.05, 0.05, 0.60), (x, D/2-0.42, 1.15), dark)
    box('MonFace%d' % i, (0.98, 0.03, 0.54), (x, D/2-0.455, 1.15), sig)
    box('MonStand%d' % i, (0.14, 0.14, 0.24), (x, D/2-0.44, 0.91), al)

# ---------------------------------------------------------------- transport robot in the aisle
box('AMR_Body', (0.86, 1.24, 0.34), (0.15, -1.4, 0.28), amber)
box('AMR_Deck', (0.94, 1.30, 0.05), (0.15, -1.4, 0.47), st)
box('AMR_Load', (0.62, 0.78, 0.42), (0.15, -1.4, 0.71), p['crate'])
for w in ((-0.36,-0.44),(0.36,-0.44),(-0.36,0.44),(0.36,0.44)):
    cylinder('AMR_W%s%s' % w, 0.11, 0.09, (0.15+w[0], -1.4+w[1], 0.11), dark)
box('AMR_Mast', (0.07, 0.07, 0.60), (0.15, -1.94, 0.78), al)
box('AMR_Beacon', (0.10, 0.10, 0.09), (0.15, -1.94, 1.12), sig)

# ---------------------------------------------------------------- floor markings for the transport lane
lane = material('lane', (0.72, 0.58, 0.10), 0.75)
for s in range(22):
    box('Lane_L%d' % s, (0.09, 0.62, 0.006), (-0.62, -8.4 + s*0.86, 0.004), lane)
    box('Lane_R%d' % s, (0.09, 0.62, 0.006), ( 0.92, -8.4 + s*0.86, 0.004), lane)

box('Tray_Spine', (0.30, 19.0, 0.08), (-0.30, 1.4, 3.88), al)
for t in range(13):
    box('Tray_Hanger%d' % t, (0.05, 0.05, 0.16), (-0.30, -7.4 + t*1.55, 3.94), al)
    box('Tray_Cond%d' % t,   (0.05, 19.0, 0.05), (-0.40 + (t%5)*0.05, 1.4, 3.82), dark)
for f in range(9):
    box('Fixture%d_A' % f, (1.30, 0.30, 0.10), (-3.9, -7.0 + f*2.1, 3.90), al)
    box('Fixture%d_B' % f, (1.30, 0.30, 0.10), ( 3.3, -7.0 + f*2.1, 3.90), al)

outside(shell, side='right', distance=9.0, brightness=3.0)
cam = interior_view(target=(0.15, 7.0, 1.45), stand=(-0.10, -10.5, 2.05), lens=26.0)
interior_lighting(shell, rows=6, cols=3, energy=23)
daylight(direction=(-0.82, 0.30, -0.50), energy=4.6)
"""
