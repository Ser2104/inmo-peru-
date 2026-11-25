

def test_antiguedad():
    from inmo.collectors.base import antiguedad
    assert antiguedad("Con solo 8 años de antigüedad") == 8
    assert antiguedad("Antigüedad: 15") == 15
    assert antiguedad("Depa a estrenar") == 0
    assert antiguedad("bonito depa") is None


def test_antiguedades_urbania():
    from inmo.collectors.navent import antiguedades
    html = '"postingId":"123456"x\\"CFT5\\":{\\"featureId\\":\\"CFT5\\",\\"label\\":\\"Antig\\",\\"value\\":\\"14\\"}'
    assert antiguedades(html) == {"123456": 14}
