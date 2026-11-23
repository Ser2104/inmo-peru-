# Analizador inmobiliario Perú

Recolecta inmuebles y proyectos de todo el Perú, los compara con su zona y calcula si conviene comprarlos para alquilar o revender, a corto, mediano y largo plazo.

## Cómo funciona

| Pieza | Qué hace | Cuándo corre |
|---|---|---|
| Recolectores | Leen Urbania, Adondevivir, Properati, Nexo y las webs que encuentre el buscador | Cada 6 horas |
| BCRP | Baja tipo de cambio, índice de precios y PER (precio/alquiler) por distrito | Cada día |
| Agente buscador | Busca en internet preventas, remates (bancos, REMAJU) y constructoras nuevas, rotando 5 departamentos por día | Cada día |
| Agente explorador | Busca más allá de los portales: webs de constructoras pequeñas, foros (SkyscraperCity, Reddit), noticias regionales, remates (REMAJU, SUNAT, cajas), adjudicados de bancos, proyectos Mivivienda/Techo Propio, licencias municipales, terrenos y corredores independientes. Prioriza los departamentos con menos datos y las búsquedas que más resultados dan | Cada día |
| Agente verificador | Convierte cada pista en un inmueble con precio: abre la página (HTML o PDF), y si no tiene precio busca la web oficial. Tras 3 intentos fallidos la descarta | Cada 6 horas |
| Catálogos de bancos | Lee los PDF mensuales de adjudicados (BBVA y los que se agreguen) | Cada 6 horas |
| Agente Airbnb | Junta tarifa por noche, ocupación e ingresos de alquiler por días (AirDNA, Airbtics, AirROI, bnbcalc) en 38 zonas turísticas y distritos, y si la municipalidad lo restringe. Con `AIRROI_API_KEY` (US$0.01 por consulta) estima cada inmueble con su ubicación exacta | Cada día |
| Agente auditor | Marca duplicados, precios absurdos y avisos que ya no existen | Cada 6 horas |
| Agente analista | Calcula alquiler estimado, flujo de caja, TIR, VAN, precio máximo y puntajes | Cada 6 horas |
| Agente de alertas | Te manda por Telegram las oportunidades con veredicto "Comprar" | Cada 6 horas |
| Agente de mejora | Ajusta rentabilidad y vacancia por departamento con datos reales, repara solo los selectores cuando un portal cambia su diseño y abre issues en GitHub cuando algo falla | Cada día |
| Claude en GitHub | Lee esos issues, corrige el código y abre un PR con pruebas | Al abrirse un issue |

## Mapa

`mapa/` es una página que se publica sola en GitHub Pages (`https://ser2104.github.io/inmo-peru/`). Pide correo y contraseña: solo ven datos los correos de la tabla `usuarios_mapa`.

- Puntos de colores por veredicto (verde Comprar, ámbar Negociar, rojo Descartar). Letras: D = mejor por días, R = remate, P = preventa.
- Filtros: departamento, distrito, plazo (corto, mediano, largo), veredicto, forma de alquilar, tipo, situación, precio y puntaje.
- "Mejores": ranking de las 30 mejores oportunidades según los filtros.
- "Alquilar y operar por días": muestra el arbitraje de departamentos en alquiler.
- "Zonas": círculos por distrito con su puntaje y rentabilidad típica.
- Al tocar un punto: resumen en lenguaje simple, precio máximo a pagar, comparación tradicional vs. por días, peor y mejor caso, flujo de dinero de 10 años y riesgos.
- Si el aviso no trae dirección, el agente ubicador lo pone en su distrito y el mapa lo marca como ubicación aproximada.
- Vista de ejemplo sin datos reales: `.../inmo-peru/?demo`.

## Qué puede fallar y cómo se cubre

| Falla | Cómo la detecta | Qué hace el sistema |
|---|---|---|
| Un portal bloquea o tarda | Error al descargar | Reintenta 3 veces con espera creciente y se hace pasar por Chrome |
| Un portal cambia su diseño | Página con 0 avisos | La IA encuentra los nuevos selectores, los prueba y los guarda; si no, lee la página con IA |
| Un portal sigue caído | 3 fallos seguidos | Lo pausa 6 h, luego 12 h, 24 h… (máx. 7 días), avisa y abre un issue para Claude |
| Un portal trae muchos menos avisos de lo normal | Compara con su promedio | Avisa: puede haber cambiado la página sin dar error |
| Gemini sin cuota o caído | Error 429/5xx | Pasa a Claude (si hay clave) y reintenta |
| Supabase lento o caído | Error 5xx o de red | Reintenta 5 veces con espera creciente; si no, avisa por Telegram |
| Un agente se cuelga | Más de 90 min en un paso | Lo corta, lo registra y sigue con los demás |
| Un agente falla | Se guarda cada error en `ejecuciones` | El vigilante lo reporta y abre un issue con `@claude` |
| GitHub Actions se apaga o no tiene minutos | Un vigilante dentro de Supabase revisa cada hora | Avisa por Telegram si nada corre en 10 h |
| GitHub apaga los flujos por inactividad (60 días) | — | Un commit automático cada mes lo evita |
| BCRP caído | Tipo de cambio viejo | Usa el último valor y avisa a los 4 días |
| Datos absurdos (precio, área, TIR) | Reglas y comparación con la zona | Los marca como sospechosos y no los recomienda |
| Avisos duplicados o vendidos | Huella de área y precio; días sin verse | Los marca y los saca de los cálculos |
| Base de datos llena (500 MB gratis) | Mide el tamaño cada 2 h | Al 80% borra datos viejos y avisa |
| Pérdida de datos | — | Respaldo semanal guardado 90 días (`python -m inmo.cli restaurar`) |
| Un cambio de código rompe algo | Pruebas automáticas en cada cambio | Los PR de Claude solo se aceptan si pasan las pruebas |
| Falta una clave o configuración | `python -m inmo.cli diagnostico` | Lista qué funciona y qué falta |
| Departamentos sin datos | El vigilante cuenta inmuebles por departamento | El explorador busca más ahí |
| Una búsqueda no rinde | Estadística de pistas nuevas por categoría | Se usa menos; 25% de las veces prueba otras al azar |
| Una web nueva trae varios proyectos | 3 o más inmuebles del mismo dominio | Se agrega sola como fuente fija |
| Avisos repetidos | Huella de los problemas | Avisa una sola vez y otra cuando todo vuelve a la normalidad |

## Alquiler por días (Airbnb)

Cada inmueble en venta se evalúa de dos formas: alquiler tradicional y alquiler por días. Para alquiler por días se descuentan comisión de la plataforma con IGV, administración (20% por defecto; pon `gestion_temporal = 0` si lo manejas tú), limpieza, luz, agua e internet, amoblado inicial y reposición, mantenimiento todo el año, más desgaste y 5% de impuesto. El primer año se asume 75% de la ocupación normal.

Se elige alquiler por días solo si su TIR supera a la tradicional por al menos 1 punto (prima por el mayor riesgo) y el distrito no lo restringe (Miraflores ya está marcado como restringido).

Además, cada departamento **en alquiler** se evalúa como **arbitraje**: alquilarlo, amoblarlo y operarlo por días. Sale la ganancia mensual, el escenario pesimista y en cuántos meses recuperas el amoblado. Ojo: requiere autorización escrita del dueño para subarrendar.

`python -m validacion.airbnb_real` muestra el resultado con datos reales de Lima: el alquiler por días le gana al tradicional cuando la ocupación pasa de ~50–55% con administrador, o de ~35–45% si lo administras tú.

## Puntajes (0 a 10)

- **Corto (0–2 años):** precio frente a la zona, rentabilidad neta y flujo mensual. Baja si es en planos.
- **Mediano (5 años):** TIR a 5 años frente a la tasa mínima (8% por defecto).
- **Largo (10 años):** TIR a 10 años; baja si en el escenario pesimista se pierde dinero.
- **Veredicto:** Comprar (≥ 7.5), Negociar (≥ 6 o si el precio máximo recomendado está a menos de 10%), Descartar. Si los datos son pocos, sale "Revisar a mano".

El cálculo incluye alcabala (solo en reventa, con 10 UIT exentas), notaría, impuesto predial, reparaciones, seguro, vacancia, 5% de impuesto al alquiler, comisión e impuesto al vender, hipoteca y la diferencia entre el precio pedido y el valor de mercado.

## Instalación (gratis)

1. **Supabase:** crea el proyecto y corre en el editor SQL, en orden, los 3 archivos de `supabase/migrations/`. Para el vigilante interno agrega tu Telegram:
   `insert into secretos values ('telegram_token','...'), ('telegram_chat_id','...');`
2. **GitHub:** sube esta carpeta a un repositorio (público = minutos ilimitados de Actions; privado = 2,000 min/mes gratis).
3. En el repo, ve a *Settings → Secrets and variables → Actions* y agrega:
   - `SUPABASE_URL` y `SUPABASE_SERVICE_KEY` (en Supabase: *Project Settings → API*, clave `service_role`)
   - `GEMINI_API_KEY` (gratis en Google AI Studio) para el buscador y la lectura de webs
   - Opcional: `AIRROI_API_KEY` (datos de Airbnb por inmueble, pago por uso)
   - Opcional: `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID` para alertas; `ANTHROPIC_API_KEY` para que Claude arregle el código solo (y en ese caso instala la app de Claude en el repo con `/install-github-app` desde Claude Code)
4. Corre a mano el flujo **agentes** con la tarea `diagnostico`: debe salir todo en ✅. Luego córrelo con `completo`.
5. En *Settings → Pages*, en "Source" elige **GitHub Actions** para publicar el mapa.
6. Recomendado: en *Settings → Branches* protege `main` para que solo entren cambios con las pruebas en verde.

## API

```bash
pip install -r requirements.txt
export SUPABASE_URL=... SUPABASE_SERVICE_KEY=... INMO_API_KEY=una-clave
uvicorn inmo.api:app --reload
```

Se puede publicar gratis con el `Dockerfile` (por ejemplo en Render o Fly.io).

| Ruta | Para qué |
|---|---|
| `POST /analizar` | Analiza al instante un enlace (`{"url": "..."}`) o datos (`{"datos": {"precio": 150000, "area_m2": 90, "departamento": "Arequipa", "distrito": "Cayma"}}`). Acepta `renta_mensual_usd`, `cuota_inicial`, `tasa_hipoteca`, `plazo_hipoteca` |
| `GET /oportunidades` | Mejores inmuebles. Filtros: `departamento`, `distrito`, `tipo`, `estado`, `horizonte` (corto, mediano, largo, total), `min_puntaje`, `precio_max` |
| `GET /inmuebles/{id}` | Datos, análisis e historial de precios |
| `GET /inmuebles/{id}/reporte?k=CLAVE` | Reporte financiero en HTML |
| `GET /arbitraje` | Departamentos en alquiler que convienen operar por días |
| `GET /mercado-temporal` | Tarifa, ocupación e ingresos de Airbnb por zona y la regulación conocida |
| `GET /zonas` | Precio mediano por m² de cada zona |
| `GET /salud` | Estado de las fuentes y los agentes |

Todas (menos `/salud` y el reporte) piden la cabecera `X-API-Key`.

## Ajustes

Cualquier valor de `inmo/config.py → PARAMETROS_BASE` se puede cambiar sin tocar código, agregando una fila en la tabla `parametros` (por ejemplo `tasa_descuento = 0.09` o `cuota_inicial = 0.2` para simular hipoteca).

## Validación con datos reales (noviembre 2026)

`python -m validacion.mercado_real` corre el motor con 11 proyectos reales de Nexo Inmobiliario, el PER por distrito del BCRP (T1-2026) y los precios por m² de Urbania.

- Las cuentas (cuota, TIR, VAN, saldo de deuda) coinciden al centavo con `numpy-financial`.
- La rentabilidad bruta estimada (4–6.5%) cuadra con la del mercado limeño que publican Urbania (~5.4%) y el BCRP (PER promedio 16.7, ~6%).
- Comprar a precio de mercado en Lima da una TIR de ~5–7% a 10 años: el sistema sale "Negociar" o "Descartar", y da el precio máximo que conviene pagar.
- Con hipoteca al 7.5% la TIR cae a 0–3%: hoy el crédito cuesta más de lo que rinde el inmueble.
- Un departamento usado 30% bajo el precio de su zona en un distrito rentable (Lince, Surquillo) sale "Comprar". En Surco, que rinde menos por alquiler, ni con 30% de descuento llega.

## Límites

- Lo que no se publica en internet (carteles, boca a boca, grupos privados) no entra solo; usa `POST /analizar` con los datos.
- En zonas con pocos avisos la confianza baja y el sistema lo dice.
- Leer portales de forma automática puede ir contra sus términos de uso.
- Es una estimación, no asesoría financiera: revisa SUNARP, deudas y el estado del inmueble antes de comprar.

## Pruebas

```bash
pytest -q
```
