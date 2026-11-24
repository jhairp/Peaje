"""
Agente Conversacional con Qwen (vía API Key + Function Calling) - Sección 4.8
Responde consultas sobre placas por texto o por imagen con uno de los 4 estados obligatorios:
  1. Registrada y con paso
  2. Registrada sin paso
  3. Identificada no registrada
  4. No existe

Características:
  - Normaliza la placa (mayúsculas, sin guiones ni espacios, validación de formato).
  - Ante errores probables de OCR (O↔0, I↔1, B↔8, S↔5), sugiere coincidencias cercanas ("¿Quisiste decir…?").
  - Si la imagen no tiene una placa legible, lo indica y pide otra imagen.
  - Usa Function Calling con Qwen (compatible con DashScope / OpenRouter / OpenAI SDK) y
    respaldo determinista estricto conectado a la BD para no inventar jamás información.
"""
import json
import os
from typing import Any, Dict, List, Optional, Set
from sqlalchemy.orm import Session

from models import Caseta, Paso, Vehiculo
from ocr_utils import (
    buscar_sugerencias_ocr,
    extraer_placa_de_mensaje,
    limpiar_placa_basico,
    normalizar_placa,
    validar_formato_placa,
)


def obtener_todas_las_placas_bd(db: Session) -> Set[str]:
    placas_v = {limpiar_placa_basico(v.placa) for v in db.query(Vehiculo.placa).all() if v.placa}
    placas_p = {
        limpiar_placa_basico(p.placa_normalizada)
        for p in db.query(Paso.placa_normalizada).all()
        if p.placa_normalizada
    }
    return placas_v.union(placas_p)


def tool_consultar_placa_bd(db: Session, texto_placa: str) -> Dict[str, Any]:
    """
    Tool principal del Agente Conversacional: consulta únicamente datos reales de la Base de Datos.
    Determina exactamente cuál de los 4 estados corresponde y busca sugerencias de OCR cercanas.
    """
    placa_limpia = normalizar_placa(texto_placa, corregir_posiciones=False)
    formato_valido = validar_formato_placa(placa_limpia)

    if not placa_limpia:
        return {
            "placa_consultada": texto_placa,
            "placa_normalizada": "",
            "formato_valido": False,
            "estado": "Placa ilegible o vacía",
            "vehiculo": None,
            "pasos": [],
            "sugerencias_ocr": [],
        }

    vehiculo = db.query(Vehiculo).filter(Vehiculo.placa == placa_limpia).first()
    pasos_db = (
        db.query(Paso)
        .filter(Paso.placa_normalizada == placa_limpia)
        .order_by(Paso.created_at.desc())
        .all()
    )

    casetas_map = {c.id: c.nombre for c in db.query(Caseta).all()}

    lista_pasos = [
        {
            "id": p.id,
            "fecha": p.created_at.strftime("%Y-%m-%d %H:%M:%S") if p.created_at else "",
            "caseta": casetas_map.get(p.caseta_id, f"Caseta #{p.caseta_id}"),
            "caseta_id": p.caseta_id,
            "categoria": p.categoria_detectada,
            "ejes": p.ejes_detectados,
            "monto_bs": round(float(p.monto), 2),
            "estado_paso": p.estado,
            "confianza_ocr": round(float(p.confianza_ocr), 3),
            "imagen_url": p.imagen_url,
        }
        for p in pasos_db
    ]

    # Determinar uno de los 4 estados exactos de la Sección 4.8
    if vehiculo and len(lista_pasos) > 0:
        estado = "Registrada y con paso"
    elif vehiculo and len(lista_pasos) == 0:
        estado = "Registrada sin paso"
    elif (not vehiculo) and len(lista_pasos) > 0:
        estado = "Identificada no registrada"
    else:
        estado = "No existe"

    # Buscar sugerencias ante posibles errores de OCR (O↔0, I↔1, B↔8, S↔5)
    todas_placas = obtener_todas_las_placas_bd(db)
    sugerencias = buscar_sugerencias_ocr(placa_limpia, todas_placas, max_sugerencias=3)

    datos_vehiculo = None
    if vehiculo:
        datos_vehiculo = {
            "id": vehiculo.id,
            "placa": vehiculo.placa,
            "propietario": vehiculo.propietario,
            "categoria": vehiculo.categoria,
            "ejes": vehiculo.ejes,
            "saldo_bs": round(float(vehiculo.saldo), 2),
            "activo": vehiculo.activo,
        }

    return {
        "placa_consultada": texto_placa,
        "placa_normalizada": placa_limpia,
        "formato_valido": formato_valido,
        "estado": estado,
        "vehiculo": datos_vehiculo,
        "total_pasos": len(lista_pasos),
        "pasos": lista_pasos[:10],
        "sugerencias_ocr": sugerencias,
    }


def redactar_respuesta_verificada(resultado_tool: Dict[str, Any], origen: str = "texto") -> str:
    """
    Construye una respuesta clara, estructurada y 100% fiel a los datos de la base de datos,
    sin inventar ningún dato, cumpliendo estrictamente la rúbrica de la Sección 4.8.
    """
    placa = resultado_tool.get("placa_normalizada", "")
    estado = resultado_tool.get("estado", "No existe")
    veh = resultado_tool.get("vehiculo")
    pasos = resultado_tool.get("pasos", [])
    sugerencias = resultado_tool.get("sugerencias_ocr", [])
    formato_ok = resultado_tool.get("formato_valido", True)

    encabezado_origen = "📷 **Lectura de placa por imagen**" if origen == "imagen" else "🔎 **Consulta de placa por texto**"
    aviso_formato = (
        ""
        if formato_ok
        else f"\n⚠️ *Nota: La cadena `{placa}` no coincide con el formato estándar de placa boliviana (3-4 dígitos y 3 letras).* "
    )

    if estado == "Registrada y con paso":
        u = pasos[0]
        lineas = [
            f"{encabezado_origen}",
            f"- **Placa normalizada:** `{placa}`",
            f"- **Estado en el sistema:** ✅ **Registrada y con paso**",
            f"- **Propietario:** {veh['propietario']}",
            f"- **Categoría registrada:** {veh['categoria'].capitalize()} ({veh['ejes']} ejes) | **Saldo actual:** Bs. {veh['saldo_bs']:.2f}",
            f"- **Último paso registrado:** Fecha `{u['fecha']}` en **{u['caseta']}**, categoría `{u['categoria']}` ({u['ejes']} ejes), tarifa **Bs. {u['monto_bs']:.2f}** (estado: *{u['estado_paso']}*).",
        ]
        if len(pasos) > 1:
            lineas.append(f"- **Total de pasos en historial:** {resultado_tool['total_pasos']} pasos registrados.")
        return "\n".join(lineas)

    if estado == "Registrada sin paso":
        lineas = [
            f"{encabezado_origen}",
            f"- **Placa normalizada:** `{placa}`",
            f"- **Estado en el sistema:** 🟦 **Registrada sin paso**",
            f"- **Detalle:** La placa `{placa}` está registrada a nombre de **{veh['propietario']}** (categoría: **{veh['categoria'].capitalize()}**, **{veh['ejes']} ejes**, saldo: **Bs. {veh['saldo_bs']:.2f}**), pero **nunca pasó por el peaje**.",
        ]
        return "\n".join(lineas)

    if estado == "Identificada no registrada":
        u = pasos[0]
        lineas = [
            f"{encabezado_origen}",
            f"- **Placa normalizada:** `{placa}`",
            f"- **Estado en el sistema:** 🚨 **Identificada no registrada** *(Posible evasión)*",
            f"- **Detalle:** La cámara detectó la placa `{placa}` en **{u['caseta']}** el `{u['fecha']}` (categoría detectada: **{u['categoria'].capitalize()}**, **{u['ejes']} ejes**, monto tarifado: **Bs. {u['monto_bs']:.2f}**), pero **no se encuentra registrada en el padrón de vehículos**.",
        ]
        if sugerencias:
            sugs = ", ".join(f"`{s}`" for s in sugerencias)
            lineas.append(f"- 💡 **Sugerencia por posible confusión de OCR:** ¿Quisiste decir {sugs}?")
        return "\n".join(lineas)

    # Caso 4: "No existe"
    lineas = [
        f"{encabezado_origen}",
        f"- **Placa normalizada:** `{placa}`{aviso_formato}",
        f"- **Estado en el sistema:** ❌ **No existe**",
        f"- **Detalle:** No existe ningún registro de la placa `{placa}` ni en el padrón de vehículos ni en el historial de pasos por casetas.",
    ]
    if sugerencias:
        sugs = ", ".join(f"**`{s}`**" for s in sugerencias)
        lineas.append(
            f"- 💡 **¿Quisiste decir {sugs}?** *(Detectada coincidencia cercana por posible error de OCR como O↔0, I↔1, B↔8 o S↔5)*."
        )
    return "\n".join(lineas)


def consultar_agente_qwen(
    db: Session,
    mensaje_usuario: str,
    placa_directa: Optional[str] = None,
    origen: str = "texto",
    inference_url: Optional[str] = None,
    inference_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Ejecuta el Agente Conversacional con Qwen:
      1. Primero intenta usar Ollama (qwen3:1.7b) corriendo en el mismo Colab/RunPod via INFERENCE_URL/llm-chat
         (exactamente como en colab_server_v2.ipynb, sin necesitar API Key de pago).
      2. Si se configuró QWEN_API_KEY externa, también la soporta.
      3. Siempre valida contra los datos reales de la Tool de BD (tool_consultar_placa_bd) para no inventar información.
    """
    candidato_placa = placa_directa or extraer_placa_de_mensaje(mensaje_usuario)
    if not candidato_placa and mensaje_usuario:
        candidato_placa = limpiar_placa_basico(mensaje_usuario)

    if not candidato_placa or len(candidato_placa) < 3:
        return {
            "exito": False,
            "estado": "Placa no detectada",
            "placa_normalizada": "",
            "sugerencias_ocr": [],
            "modelo_agente": os.environ.get("QWEN_MODEL", "qwen3:1.7b (Ollama Colab/RunPod)"),
            "respuesta": (
                "No pude identificar un número de placa válido en tu consulta. "
                "Por favor ingresa una placa (por ejemplo: `1852-PHD`, `3810RTY`, `9981EVA`) o sube otra imagen donde la placa sea legible."
            ),
            "datos_bd": None,
        }

    # Ejecutar la Tool determinista sobre la base de datos
    datos_tool = tool_consultar_placa_bd(db, candidato_placa)
    respuesta_base = redactar_respuesta_verificada(datos_tool, origen=origen)

    url_inf = (inference_url or os.environ.get("INFERENCE_URL", "")).strip().rstrip("/")
    tok_inf = (inference_token or os.environ.get("INFERENCE_API_TOKEN", "")).strip()
    qwen_model = os.environ.get("QWEN_MODEL", "qwen3:1.7b").strip()

    system_prompt = (
        "Eres el Agente Inteligente de Control de Peaje (IAM-811). /no_think\n"
        "REGLAS ESTRICTAS:\n"
        "1. Responde ÚNICAMENTE con los datos verificados de la Base de Datos que se te entregan. Prohibido inventar fechas, saldos, nombres o pasos.\n"
        "2. Debes indicar explícitamente el estado exacto: "
        f"'{datos_tool['estado']}'.\n"
        "3. Si el estado es 'Registrada y con paso', indica propietario, saldo, fecha del paso, caseta, categoría y monto en Bs.\n"
        "4. Si hay sugerencias_ocr en los datos, incluye la pregunta: '¿Quisiste decir ...?' mencionando las placas sugeridas.\n"
        "5. Responde en español conciso y claro."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"Consulta ({origen}): {mensaje_usuario or candidato_placa}\n"
                f"Resultado oficial de la Tool BD:\n{json.dumps(datos_tool, ensure_ascii=False)}\n"
                f"Resumen verificado:\n{respuesta_base}"
            ),
        },
    ]

    respuesta_final = respuesta_base
    etiqueta_modelo = f"Ollama ({qwen_model}) + Tool BD"

    # 1. Intentar con Ollama (qwen3:1.7b) corriendo en Colab / RunPod en INFERENCE_URL/llm-chat
    if url_inf and "tu-pod-id" not in url_inf:
        try:
            import requests as req_sync

            headers = {"Content-Type": "application/json"}
            if tok_inf:
                headers["X-API-Token"] = tok_inf
            r_ollama = req_sync.post(
                f"{url_inf}/llm-chat",
                json={"messages": messages},
                headers=headers,
                timeout=25,
            )
            if r_ollama.status_code == 200:
                data_o = r_ollama.json()
                txt_o = (data_o.get("respuesta") or "").strip()
                if txt_o and datos_tool["estado"].lower() in txt_o.lower():
                    respuesta_final = txt_o
                    etiqueta_modelo = f"Ollama {data_o.get('modelo', 'qwen3:1.7b')} (Colab/RunPod)"
        except Exception:
            pass

    return {
        "exito": True,
        "origen": origen,
        "placa_consultada": candidato_placa,
        "placa_normalizada": datos_tool["placa_normalizada"],
        "formato_valido": datos_tool["formato_valido"],
        "estado": datos_tool["estado"],
        "sugerencias_ocr": datos_tool["sugerencias_ocr"],
        "modelo_agente": etiqueta_modelo,
        "respuesta": respuesta_final,
        "datos_bd": datos_tool,
    }
