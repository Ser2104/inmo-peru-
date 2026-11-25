from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*tile.openstreetmap.org/**", lambda r: r.abort())
    pg.goto("http://localhost:8765/index.html?demo", wait_until="load")
    pg.wait_for_timeout(1500)
    for capa in ["b-negocios", "b-oportunidades"]:
        pg.click("#" + capa)
        pg.wait_for_timeout(500)
        n = pg.evaluate("grupo.getLayers().length")
        if not n:
            print(capa, "sin marcadores"); continue
        pg.evaluate("(() => { const l = grupo.getLayers()[0]; mapa.setView(l.getLatLng(), 18, {animate:false}); })()")
        pg.wait_for_timeout(800)
        box = pg.evaluate("(() => { const l = grupo.getLayers()[0]; const r = l._icon && l._icon.getBoundingClientRect(); return r ? [r.x + r.width/2, r.y + r.height/2] : null; })()")
        if not box:
            print(capa, "icono no visible"); continue
        pg.mouse.click(*box)
        pg.wait_for_timeout(800)
        print(capa, "detalle abierto:", pg.locator("#detalle.abierto").count(), "|", pg.locator("#contenido").inner_text()[:120].replace("\n", " "))
        print("  enlaces:", pg.eval_on_selector_all("#contenido a", "as => as.map(a => a.href).slice(0,3)"))
        pg.evaluate("document.getElementById(\"detalle\").classList.remove(\"abierto\")")
    print("errores:", errs[:5])
    b.close()
