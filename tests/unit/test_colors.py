import pytest

from videoqa.checks.colors import delta_e2000, hex_delta_e, hex_to_rgb, rgb_to_lab

def test_hex_to_rgb():
    assert hex_to_rgb("#FF3B30") == (255, 59, 48)
    assert hex_to_rgb("ff3b30") == (255, 59, 48)

def test_rgb_to_lab_white_and_black():
    L, a, b = rgb_to_lab((255, 255, 255))
    assert abs(L - 100) < 0.01 and abs(a) < 0.01 and abs(b) < 0.01
    assert abs(rgb_to_lab((0, 0, 0))[0]) < 0.01

def test_delta_e2000_sharma_pair():
    # Par 1 de los datos de prueba de Sharma et al. (2005)
    assert abs(delta_e2000((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485)) - 2.0425) < 0.001


# Datos de referencia de Sharma, Wu & Dalal (2005), "The CIEDE2000 Color-Difference Formula".
# Cubren las ramas frágiles de la fórmula: el wraparound de tono (pares 3, 30), el término
# rotacional RT en la zona azul (3, 30), los casos casi acromáticos con C' pequeño (17, 18),
# una diferencia grande (21) y un caso verde de referencia (26).
SHARMA = [
    ("3",  (50.0, 2.6772, -79.7751),      (50.0, 0.0, -82.7485),          2.0425),
    ("17", (50.0, 2.5, 0.0),              (50.0, 3.1736, 0.5854),         1.0000),
    ("18", (50.0, 2.5, 0.0),              (50.0, 3.2972, 0.0),            1.0000),
    ("21", (50.0, 2.5, 0.0),              (58.0, 24.0, 15.0),            19.4535),
    ("26", (60.2574, -34.0099, 36.2677),  (60.4626, -34.1751, 39.4387),   1.2644),
    ("30", (22.7233, 20.0904, -46.6940),  (23.0331, 14.9730, -42.5619),   2.0373),
]


@pytest.mark.parametrize("pair,lab1,lab2,expected", SHARMA, ids=[p[0] for p in SHARMA])
def test_delta_e2000_sharma_reference_data(pair, lab1, lab2, expected):
    assert delta_e2000(lab1, lab2) == pytest.approx(expected, abs=0.001)


def test_delta_e2000_is_symmetric():
    for _, lab1, lab2, _ in SHARMA:
        assert delta_e2000(lab1, lab2) == pytest.approx(delta_e2000(lab2, lab1), abs=1e-9)

def test_identical_is_zero_and_far_is_large():
    assert hex_delta_e("#FFFFFF", "#FFFFFF") == 0.0
    assert hex_delta_e("#FF3B30", "#FFFFFF") > 30
    assert hex_delta_e("#F5C518", "#F4C41A") < 3
