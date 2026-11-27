from inmo.collectors.estructurado import parsear


def test_infocasas_jsonld():
    item = '{"@type":"Offer","url":"https://www.infocasas.com.pe/depa/%d","name":"Depa","price":"88000","priceCurrency":"USD","mainEntity":{"@type":"Accommodation","floorSize":{"@type":"QuantitativeValue","value":"%d"},"numberOfBedrooms":"2","address":{"addressLocality":"Yanahuara","addressRegion":"Arequipa"},"geo":{"latitude":"-16.39","longitude":"-71.55"}}}'
    html = '<script type="application/ld+json">{"itemListElement":[%s]}</script>' % ",".join(item % (i, 80 + i) for i in range(3))
    r = parsear(html, "https://www.infocasas.com.pe/venta")
    assert len(r) == 3 and r[0]["area_m2"] == 80 and r[0]["moneda"] == "USD" and r[0]["distrito"] == "Yanahuara" and r[0]["lat"] == -16.39
