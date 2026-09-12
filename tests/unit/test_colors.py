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

def test_identical_is_zero_and_far_is_large():
    assert hex_delta_e("#FFFFFF", "#FFFFFF") == 0.0
    assert hex_delta_e("#FF3B30", "#FFFFFF") > 30
    assert hex_delta_e("#F5C518", "#F4C41A") < 3
