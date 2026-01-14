import os
import math
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

import requests


# =========================
# LOGGING (ES)
# =========================
def configurar_logger() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)

    nivel_str = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    nivel = getattr(logging, nivel_str, logging.INFO)

    logger = logging.getLogger("cotizations-bot")
    logger.setLevel(nivel)
    logger.handlers.clear()

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler()
    ch.setLevel(nivel)
    ch.setFormatter(formato)
    logger.addHandler(ch)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_log = os.path.join("logs", f"run_{ts}.log")
    fh = logging.FileHandler(ruta_log, encoding="utf-8")
    fh.setLevel(nivel)
    fh.setFormatter(formato)
    logger.addHandler(fh)

    logger.info(f"Logger inicializado. Nivel={nivel_str}. Archivo={ruta_log}")
    return logger


# =========================
# CONFIG (SIN INPUTS)
# =========================
@dataclass(frozen=True)
class Config:
    RDA_COMMISSION: float = 0.87
    BINANCE_COMMISSION_TO_SUBSTRACT: float = 0.96

    ONLY_PAYO: bool = False
    PUBLISH_COTIZATIONS: bool = False

    # Dolarhoy: usá la página específica del blue (la que vos estás mirando)
    DOLARHOY_URLS: Tuple[str, ...] = (
        "https://dolarhoy.com/cotizacion-dolar-blue",
        "https://dolarhoy.com/cotizaciondolarblue",
    )

    BINANCE_P2P_API_URL: str = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    FIAT: str = "ARS"
    ASSET: str = "USDT"
    TRADE_TYPE: str = "SELL"

    ROWS: int = 20

    HTTP_TIMEOUT_SECS: int = 25
    HTTP_RETRIES: int = 3


cfg = Config()

FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSer5Xb5IZs21XdsdJqBXhdhZRCtvHsVe9iywJ1_ouiUEmSQuQ/formResponse"
FORM_FIELDS = {
    "blue_compra": "entry.1296954884",
    "blue_venta": "entry.2063587065",
    "binance_low": "entry.1697056713",
    "valor_real": "entry.861833082",
    "cotizacion_final": "entry.1842390756",
    "comision_aplicada": "entry.71619083",
}


# =========================
# HTTP helpers
# =========================
def crear_sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    })
    return s


def request_seguro(method: str, url: str, logger: logging.Logger, session: requests.Session, **kwargs) -> requests.Response:
    ultimo_error: Optional[Exception] = None
    for intento in range(1, cfg.HTTP_RETRIES + 1):
        try:
            logger.debug(f"HTTP {method} intento {intento}/{cfg.HTTP_RETRIES}: {url}")
            r = session.request(method, url, timeout=cfg.HTTP_TIMEOUT_SECS, **kwargs)
            r.raise_for_status()
            return r
        except Exception as e:
            ultimo_error = e
            logger.warning(f"Error HTTP (intento {intento}/{cfg.HTTP_RETRIES}) hacia {url}: {e}")
    raise RuntimeError(f"Fallo HTTP luego de {cfg.HTTP_RETRIES} reintentos: {url}. Último error: {ultimo_error}")


# =========================
# Parsing de montos
# =========================
def _parsear_monto(monto: str) -> float:
    s = monto.strip().replace("$", "").strip()

    # Caso AR típico: 1.485,00 -> 1485.00
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        if "," in s and "." not in s:
            s = s.replace(",", ".")
    return float(s)


def _formatear_pesos(valor: float) -> str:
    if abs(valor - round(valor)) < 1e-9:
        return str(int(round(valor)))
    return f"{valor:.2f}"


# =========================
# DOLARHOY (Blue) - parser por estructura topic/value
# =========================
def obtener_dolar_blue(logger: logging.Logger, session: requests.Session) -> Tuple[float, float]:
    """
    Parseo basado en tu estructura real:
    <div class="topic">Compra</div><div class="value">$1485,00</div>
    <div class="topic">Venta</div><div class="value">$1505,00</div>
    """
    import re

    logger.info("Obteniendo Dólar Blue desde Dolarhoy...")

    # Regex estricta a topic/value
    patron_compra = re.compile(
        r'<div\s+class="topic">\s*Compra\s*</div>\s*<div\s+class="value">\s*\$?\s*([0-9\.,]+)\s*</div>',
        re.IGNORECASE | re.DOTALL
    )
    patron_venta = re.compile(
        r'<div\s+class="topic">\s*Venta\s*</div>\s*<div\s+class="value">\s*\$?\s*([0-9\.,]+)\s*</div>',
        re.IGNORECASE | re.DOTALL
    )

    ultimo_html: Optional[str] = None
    ultima_url: Optional[str] = None

    for url in cfg.DOLARHOY_URLS:
        logger.info(f"Consultando: {url}")
        try:
            r = request_seguro("GET", url, logger, session)
            html = r.text
            ultimo_html = html
            ultima_url = url

            # Ubicamos el bloque real de cotizacion_moneda.
            # Usamos rfind para esquivar definiciones de CSS en el <head>.
            lower = html.lower()
            idx = lower.rfind("cotizacion_moneda")
            ventana = html[idx:] if idx != -1 else html

            m_c = patron_compra.search(ventana) or patron_compra.search(html)
            m_v = patron_venta.search(ventana) or patron_venta.search(html)

            if not m_c or not m_v:
                logger.warning(f"No se encontró Compra/Venta en {url} (sigo probando otra URL).")
                continue

            compra = _parsear_monto(m_c.group(1))
            venta = _parsear_monto(m_v.group(1))

            logger.info(f"Dólar Blue obtenido OK desde {url}: compra={_formatear_pesos(compra)} venta={_formatear_pesos(venta)}")
            return compra, venta

        except Exception as e:
            logger.warning(f"Error consultando/parsing Dolarhoy en {url}: {e}")

    logger.error("No se pudo parsear Compra/Venta en Dolarhoy. Guardando HTML en logs/dolarhoy_debug.html")
    if ultimo_html is not None:
        with open("logs/dolarhoy_debug.html", "w", encoding="utf-8") as f:
            f.write(f"<!-- URL: {ultima_url} -->\n\n")
            f.write(ultimo_html)

    raise RuntimeError("No se pudo parsear el Dólar Blue (compra/venta) desde Dolarhoy (cambió el HTML).")


# =========================
# BINANCE P2P - API
# =========================
def obtener_precios_binance_p2p(logger: logging.Logger, session: requests.Session) -> List[float]:
    payload = {
        "page": 1,
        "rows": cfg.ROWS,
        "payTypes": [],
        "asset": cfg.ASSET,
        "fiat": cfg.FIAT,
        "tradeType": cfg.TRADE_TYPE,
    }

    logger.info(f"Obteniendo Binance P2P por API: asset={cfg.ASSET} fiat={cfg.FIAT} tradeType={cfg.TRADE_TYPE} rows={cfg.ROWS}")
    r = request_seguro("POST", cfg.BINANCE_P2P_API_URL, logger, session, json=payload)

    raw = r.text
    try:
        data = r.json()
    except Exception:
        logger.error("Binance no devolvió JSON. Guardando respuesta cruda en logs/binance_raw.txt")
        with open("logs/binance_raw.txt", "w", encoding="utf-8") as f:
            f.write(raw)
        raise RuntimeError("La respuesta de Binance no es JSON (posible bloqueo o cambio del endpoint).")

    ofertas = data.get("data") or []
    if not ofertas:
        logger.error("Binance devolvió JSON sin ofertas. Guardando en logs/binance_empty.json")
        with open("logs/binance_empty.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        raise RuntimeError("Binance devolvió 0 ofertas (posible bloqueo/región/cambio).")

    precios: List[float] = []
    for item in ofertas:
        adv = item.get("adv") or {}
        price_str = adv.get("price")
        if price_str:
            try:
                precios.append(float(price_str))
            except ValueError:
                logger.debug(f"Precio no parseable (se omite): {price_str}")

    if not precios:
        logger.error("No se pudo extraer adv.price. Guardando JSON en logs/binance_badshape.json")
        with open("logs/binance_badshape.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        raise RuntimeError("No se pudieron parsear precios desde la respuesta de Binance.")

    logger.info(f"Precios Binance OK: cantidad={len(precios)} min={min(precios)} max={max(precios)}")
    return precios


# =========================
# Cálculos
# =========================
def calcular_valor_real_wise_payo(low: float, high: float) -> float:
    internal = (((high - low) / 2) + low) * cfg.BINANCE_COMMISSION_TO_SUBSTRACT
    return round(internal, 2)


def calcular_cotizacion_final(binance_low: float) -> int:
    return math.floor(binance_low * cfg.RDA_COMMISSION)


def enviar_a_form(logger: logging.Logger, valores: dict) -> None:
    """
    Publica los valores en el Google Form vinculado a la Sheet.
    Espera claves:
      blue_compra, blue_venta, binance_low, valor_real,
      cotizacion_final, comision_aplicada
    """
    payload = {}
    for clave, entry_id in FORM_FIELDS.items():
        if clave in valores:
            payload[entry_id] = valores[clave]
    if not payload:
        logger.debug("Payload de Google Form vacío; no se envía nada.")
        return

    r = requests.post(FORM_URL, data=payload, timeout=10)
    if r.status_code != 200:
        logger.warning(f"Google Form devolvió status {r.status_code}: {r.text[:200]}")
    else:
        logger.info("Valores publicados en Google Form/Sheet correctamente.")


# =========================
# MAIN
# =========================
def main() -> int:
    logger = configurar_logger()
    session = crear_sesion()

    logger.info("Iniciando ejecución...")
    logger.info(f"Configuración: comisión={cfg.RDA_COMMISSION} ONLY_PAYO={cfg.ONLY_PAYO} PUBLICAR_FOROS={cfg.PUBLISH_COTIZATIONS}")

    blue_compra, blue_venta = obtener_dolar_blue(logger, session)

    precios = obtener_precios_binance_p2p(logger, session)
    binance_low = min(precios)
    binance_high = max(precios)

    valor_real = calcular_valor_real_wise_payo(binance_low, binance_high)
    cotizacion_final = calcular_cotizacion_final(binance_low)

    # OUTPUT (como pediste)
    print("")
    print(f"Dólar Blue (compra): {_formatear_pesos(blue_compra)}")
    print(f"Dólar Blue (venta):  {_formatear_pesos(blue_venta)}")
    print(f"Dólar Binance cambio (low): {binance_low}")
    print(f"Valor real que me queda por Wise/Payoneer: {valor_real}")
    print(f"COTIZACIÓN FINAL con comisión ({cfg.RDA_COMMISSION}) aplicada: {cotizacion_final}")
    print("")

    logger.info("Salida generada correctamente.")
    logger.info(
        "Resumen -> "
        f"blue_compra={_formatear_pesos(blue_compra)} | "
        f"blue_venta={_formatear_pesos(blue_venta)} | "
        f"binance_low={binance_low} | "
        f"valor_real={valor_real} | "
        f"cotizacion_final={cotizacion_final}"
    )

    try:
        enviar_a_form(logger, {
            "blue_compra": _formatear_pesos(blue_compra),
            "blue_venta": _formatear_pesos(blue_venta),
            "binance_low": f"{binance_low}",
            "valor_real": _formatear_pesos(valor_real),
            "cotizacion_final": f"{cotizacion_final}",
            "comision_aplicada": f"{cfg.RDA_COMMISSION}",
        })
    except Exception as e:
        logger.warning(f"No se pudo enviar al Google Form: {e}")

    logger.info("Ejecución finalizada OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
