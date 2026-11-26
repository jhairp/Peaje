"""
Normalización de placas, validación de formato y búsqueda difusa ante errores probables de OCR
(O↔0, I↔1, B↔8, S↔5, Z↔2, G↔6) según Sección 4.7 y 4.8.
"""
import re
from typing import Dict, List, Set, Tuple

# Confusiones típicas de OCR bidireccionales exigidas en la Sección 4.8
PARES_CONFUSION_OCR: Dict[str, Tuple[str, ...]] = {
    "O": ("0", "Q", "D"),
    "0": ("O", "Q", "D"),
    "Q": ("0", "O"),
    "D": ("0", "O"),
    "I": ("1", "L", "T"),
    "1": ("I", "L", "T"),
    "L": ("1", "I"),
    "T": ("1", "I"),
    "B": ("8",),
    "8": ("B",),
    "S": ("5",),
    "5": ("S",),
    "Z": ("2",),
    "2": ("Z",),
    "G": ("6",),
    "6": ("G",),
}

MAPA_A_DIGITO = {
    "O": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "S": "5",
    "B": "8",
    "G": "6",
}

MAPA_A_LETRA = {
    "0": "O",
    "1": "I",
    "2": "Z",
    "5": "S",
    "8": "B",
    "6": "G",
}


def limpiar_placa_basico(texto: str) -> str:
    """Mayúsculas, sin guiones, puntos ni espacios."""
    if not texto:
        return ""
    return re.sub(r"[^A-Z0-9]", "", texto.strip().upper())


def normalizar_placa(texto: str, corregir_posiciones: bool = False) -> str:
    """
    Normaliza una placa:
      1. Mayúsculas, sin guiones ni espacios.
      2. Si corregir_posiciones=True y tiene 6 o 7 caracteres (formato boliviano 3-4 dígitos + 3 letras),
         corrige confusiones posicionales.
    """
    limpio = limpiar_placa_basico(texto)
    if corregir_posiciones and len(limpio) in (6, 7):
        n_dig = len(limpio) - 3
        pref = "".join(MAPA_A_DIGITO.get(c, c) for c in limpio[:n_dig])
        suf = "".join(MAPA_A_LETRA.get(c, c) for c in limpio[n_dig:])
        if pref.isdigit() and suf.isalpha():
            return pref + suf
    return limpio


def validar_formato_placa(placa_norm: str) -> bool:
    """Valida si una placa normalizada tiene formato válido (boliviana o internacional 4-10 caracteres)."""
    if not placa_norm or len(placa_norm) < 4 or len(placa_norm) > 10:
        return False
    if re.match(r"^\d{3,4}[A-Z]{3}$", placa_norm):
        return True
    if re.match(r"^[A-Z0-9]{4,10}$", placa_norm) and any(c.isdigit() for c in placa_norm):
        return True
    return False


def extraer_placa_de_mensaje(mensaje: str) -> str:
    """
    Extrae el candidato de placa dentro de una frase en lenguaje natural
    (ej. '¿Cuál es el estado de la placa 2673-TYH?' o '07-D-40426' o 'AA 50689').
    """
    if not mensaje:
        return ""
    msg = mensaje.upper().strip()

    # 1. Patrón irlandés con 2 guiones (ej. 07-D-40426, 232-D-17482, 241-D-24258, 92-W-7010)
    m_irl = re.search(r"\b(\d{2,3})[\s\-]+([A-Z])[\s\-]+(\d{4,6})\b", msg)
    if m_irl:
        return limpiar_placa_basico(m_irl.group(1) + m_irl.group(2) + m_irl.group(3))

    # 2. Patrón boliviano o internacional con guion o espacio (ej. 2673-TYH, AA 50689, ZV 45288, VSA 530, RJB-F8)
    m = re.search(r"\b([A-Z0-9]{2,4})[\s\-]+([A-Z0-9]{2,5})\b", msg)
    palabras_ignorar = {
        "PLACA",
        "PLACAS",
        "ESTADO",
        "PEAJE",
        "SALDO",
        "PASOS",
        "TIENE",
        "CONSULTA",
        "CONSULTAR",
        "VEHICULO",
        "CAMION",
        "MINIBUS",
        "ALERTA",
        "CUAL",
        "PARA",
        "COMO",
        "ESTA",
    }
    if m and m.group(1) not in palabras_ignorar and m.group(2) not in palabras_ignorar:
        unido = limpiar_placa_basico(m.group(1) + m.group(2))
        if 4 <= len(unido) <= 10 and any(c.isdigit() for c in unido):
            return unido

    # 3. Token único de 4 a 10 caracteres que contenga dígitos
    tokens = re.findall(r"\b[A-Z0-9\-]{4,11}\b", msg)
    for tok in tokens:
        limpio = limpiar_placa_basico(tok)
        if limpio in palabras_ignorar:
            continue
        if 4 <= len(limpio) <= 10 and any(c.isdigit() for c in limpio):
            return limpio

    # 4. Si el usuario solo escribió la placa corta
    limpio_total = limpiar_placa_basico(msg)
    if 4 <= len(limpio_total) <= 10 and limpio_total not in palabras_ignorar:
        return limpio_total
    return ""


def costo_confusion_caracter(c1: str, c2: str) -> float:
    """
    Devuelve costo 0.0 si son iguales, 0.35 si son una confusión típica de OCR (O↔0, I↔1, B↔8, S↔5, etc.),
    y 1.0 si son caracteres distintos.
    """
    if c1 == c2:
        return 0.0
    if c2 in PARES_CONFUSION_OCR.get(c1, ()):
        return 0.35
    return 1.0


def distancia_ocr(p1: str, p2: str) -> Tuple[float, bool]:
    """
    Calcula distancia ponderada por errores de OCR entre dos placas normalizadas.
    Devuelve (distancia, tiene_confusion_ocr).
    """
    if p1 == p2:
        return 0.0, False
    if abs(len(p1) - len(p2)) > 1:
        return 99.0, False

    if len(p1) == len(p2):
        costo = 0.0
        hubo_ocr = False
        diferencias = 0
        for a, b in zip(p1, p2):
            if a != b:
                diferencias += 1
                c = costo_confusion_caracter(a, b)
                if c < 1.0:
                    hubo_ocr = True
                costo += c
        if diferencias <= 2 and (hubo_ocr or diferencias == 1):
            return round(costo, 2), hubo_ocr
        return 99.0, False

    # Longitud difiere en 1 (inserción/omisión de 1 carácter)
    mayor, menor = (p1, p2) if len(p1) > len(p2) else (p2, p1)
    for idx in range(len(mayor)):
        recortada = mayor[:idx] + mayor[idx + 1 :]
        if recortada == menor:
            return 1.0, False
    return 99.0, False


def buscar_sugerencias_ocr(placa_buscada: str, placas_conocidas: Set[str], max_sugerencias: int = 3) -> List[str]:
    """
    Busca en el conjunto de placas de la BD (vehículos y pasos) coincidencias cercanas
    priorizando errores probables de OCR (O↔0, I↔1, B↔8, S↔5).
    """
    p_clean = limpiar_placa_basico(placa_buscada)
    if not p_clean:
        return []

    candidatos: List[Tuple[float, str]] = []
    # También probamos la variante con corrección posicional automática
    p_corr = normalizar_placa(p_clean, corregir_posiciones=True)

    for candidata in placas_conocidas:
        if candidata == p_clean:
            continue
        if candidata == p_corr:
            candidatos.append((0.1, candidata))
            continue
        dist, _ = distancia_ocr(p_clean, candidata)
        if dist <= 1.35:
            candidatos.append((dist, candidata))

    candidatos.sort(key=lambda x: (x[0], x[1]))
    return [placa for _, placa in candidatos[:max_sugerencias]]
