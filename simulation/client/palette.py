"""Shared drawing colours.

Extracted from the old ``client/renderer.py`` when the ``Renderer`` and
``PIBTRenderer`` classes were removed as dead code. The palette itself was
never dead — ``pibt_interactive_renderer`` imports it — so it outlived the
module that happened to host it.

Plain tuples, **no pygame import**: a palette is data, and keeping it free
of the display library means importing it costs nothing on a headless path.
"""

# Tableau-10, cycled by agent_id.
AGENT_COLORS = [
    (31, 119, 180), (255, 127, 14), (44, 160, 44),  (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34),  (23, 190, 207),
]

OBJ_COLORS = {
    "obstacle": (180, 30, 30),
}

BG_A   = (240, 244, 255)   # checkerboard, light square
BG_B   = (255, 255, 255)   # checkerboard, white square
GRID_C = (200, 200, 200)
BLACK  = (0,   0,   0)
WHITE  = (255, 255, 255)
DARK   = (30,  30,  30)
