#!/usr/bin/env python3
"""
Aplicación Web, API REST, Tiempo Real y Agente Conversacional (/web)
IAM-811 Machine Learning y Aprendizaje Profundo - Laboratorio 3: Sistema de Control de Peaje
"""
import asyncio
import base64
import datetime
import json
import os
import uuid
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func
from sqlalchemy.orm import Session

from agent_qwen import consultar_agente_qwen, tool_consultar_placa_bd
from auth import (
    GOOGLE_CLIENT_ID,
    crear_token_sesion,
    exigir_administrador,
    obtener_usuario_actual,
    validar_usuario_lista_blanca,
    verificar_token_google,
)
from database import Base, SessionLocal, engine, get_db
from models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo
from ocr_utils import normalizar_placa
from realtime import gestor_rt
from schemas import (
    AgenteChatRequest,
    AuthResponse,
    CasetaCreate,
    CasetaOut,
    ConfigInferenciaRequest,
    ConsultaPlacaTextoRequest,
    GoogleAuthRequest,
    TarifaCreate,
    TarifaOut,
    UsuarioCreate,
    UsuarioOut,
    VehiculoCreate,
    VehiculoOut,
    VehiculoUpdate,
)
from seed import ejecutar_seed

load_dotenv()

# Crear tablas e insertar datos semilla (>=20 vehículos, tarifas, casetas, admin docente y jhairpinto8)
Base.metadata.create_all(bind=engine)
with SessionLocal() as _db_init:
    ejecutar_seed(_db_init)

UPLOADS_DIR = os.path.join(os.path.dirname(__file__), "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# Configuración dinámica del endpoint de inferencia (Sección 3: cambiar entre RunPod y Colab es solo cambiar INFERENCE_URL)
CONFIG_SISTEMA = {
    "inference_url": os.environ.get("INFERENCE_URL", "https://tu-pod-id-8000.proxy.runpod.net").rstrip("/"),
    "inference_api_token": os.environ.get("INFERENCE_API_TOKEN", "token_secreto_inferencia_peaje_2026"),
    "timeout": float(os.environ.get("INFERENCE_TIMEOUT_SECONDS", "45")),
}

app = FastAPI(
    title="Sistema Inteligente de Control de Peaje - API REST v1",
    version="1.0.0",
    description=(
        "API REST documentada con OpenAPI/Swagger para el Laboratorio 3 (IAM-811). "
        "Integra Google OAuth 2.0 con lista blanca, conexión al endpoint de inferencia (M1+M2+M3) en RunPod/Colab, "
        "actualización en tiempo real (WebSockets + SSE) y Agente Conversacional con Qwen."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ==============================================================================
# UTILIDADES INTERNAS (TARIFAS, SERIALIZACIÓN Y LLAMADA A INFERENCIA)
# ==============================================================================
def calcular_monto_tarifa(db: Session, categoria: str, ejes: int) -> float:
    cat = (categoria or "auto").lower().strip()
    n_ejes = max(2, int(ejes or 2))

    # Buscar coincidencia exacta de categoría y ejes
    tarifa = (
        db.query(Tarifa)
        .filter(Tarifa.categoria == cat, Tarifa.ejes == n_ejes)
        .first()
    )
    if tarifa:
        return round(float(tarifa.monto), 2)

    # Si tiene más ejes que el máximo tabulado, tomar la tarifa más cercana de esa categoría
    tarifas_cat = (
        db.query(Tarifa)
        .filter(Tarifa.categoria == cat)
        .order_by(Tarifa.ejes.desc())
        .all()
    )
    if tarifas_cat:
        return round(float(tarifas_cat[0].monto), 2)

    # Respaldo tarifario estándar en Bs.
    tabla_base = {"moto": 3.0, "auto": 7.0, "minibus": 10.0, "bus": 15.0, "camion": 15.0}
    base = tabla_base.get(cat, 7.0)
    if cat in ("camion", "bus") and n_ejes > 2:
        base += (n_ejes - 2) * 7.0
    return round(base, 2)


def serializar_paso(db: Session, paso: Paso) -> Dict[str, Any]:
    caseta = db.query(Caseta).filter(Caseta.id == paso.caseta_id).first()
    vehiculo = (
        db.query(Vehiculo).filter(Vehiculo.placa == paso.placa_normalizada).first()
        if paso.placa_normalizada
        else None
    )
    return {
        "id": paso.id,
        "placa_leida": paso.placa_leida,
        "placa_normalizada": paso.placa_normalizada,
        "confianza_ocr": round(float(paso.confianza_ocr), 3),
        "categoria_detectada": paso.categoria_detectada,
        "ejes_detectados": paso.ejes_detectados,
        "monto": round(float(paso.monto), 2),
        "caseta_id": paso.caseta_id,
        "caseta_nombre": caseta.nombre if caseta else f"Caseta #{paso.caseta_id}",
        "usuario_id": paso.usuario_id,
        "propietario": vehiculo.propietario if vehiculo else "No registrado",
        "saldo_restante": round(float(vehiculo.saldo), 2) if vehiculo else None,
        "imagen_url": paso.imagen_url,
        "estado": paso.estado,
        "created_at": paso.created_at.isoformat() if paso.created_at else "",
        "hora": paso.created_at.strftime("%H:%M:%S") if paso.created_at else "",
        "fecha_hora": paso.created_at.strftime("%Y-%m-%d %H:%M:%S") if paso.created_at else "",
    }


def serializar_alerta(db: Session, alerta: Alerta) -> Dict[str, Any]:
    paso = db.query(Paso).filter(Paso.id == alerta.paso_id).first()
    caseta = db.query(Caseta).filter(Caseta.id == paso.caseta_id).first() if paso else None
    return {
        "id": alerta.id,
        "paso_id": alerta.paso_id,
        "tipo": alerta.tipo,
        "atendida": alerta.atendida,
        "placa": paso.placa_normalizada if paso else "DESCONOCIDA",
        "categoria": paso.categoria_detectada if paso else "",
        "ejes": paso.ejes_detectados if paso else 2,
        "monto": round(float(paso.monto), 2) if paso else 0.0,
        "caseta_nombre": caseta.nombre if caseta else "Caseta 1",
        "imagen_url": paso.imagen_url if paso else "",
        "created_at": alerta.created_at.isoformat() if alerta.created_at else "",
        "fecha_hora": alerta.created_at.strftime("%Y-%m-%d %H:%M:%S") if alerta.created_at else "",
    }


def obtener_metricas_globales(db: Session) -> Dict[str, Any]:
    total_pasos = db.query(func.count(Paso.id)).scalar() or 0
    recaudacion_aprobada = (
        db.query(func.sum(Paso.monto)).filter(Paso.estado == "aprobado").scalar() or 0.0
    )
    alertas_activas = (
        db.query(func.count(Alerta.id)).filter(Alerta.atendida == False).scalar() or 0
    )
    total_vehiculos = db.query(func.count(Vehiculo.id)).scalar() or 0

    por_categoria = {}
    for cat in ("moto", "auto", "minibus", "camion", "bus"):
        cnt = db.query(func.count(Paso.id)).filter(Paso.categoria_detectada == cat).scalar() or 0
        por_categoria[cat] = cnt

    return {
        "total_pasos": total_pasos,
        "recaudacion_total_bs": round(float(recaudacion_aprobada), 2),
        "alertas_pendientes": alertas_activas,
        "vehiculos_registrados": total_vehiculos,
        "conteo_por_categoria": por_categoria,
    }


async def llamar_endpoint_inferencia(
    img_bytes: bytes,
    ruta: str = "/predict",
) -> Dict[str, Any]:
    """
    Envía los bytes JPEG/PNG al endpoint configurado en INFERENCE_URL (RunPod o Google Colab).
    """
    url_base = CONFIG_SISTEMA["inference_url"]
    token = CONFIG_SISTEMA["inference_api_token"]
    timeout = CONFIG_SISTEMA["timeout"]

    if not url_base or "tu-pod-id" in url_base:
        raise RuntimeError(
            "INFERENCE_URL aún tiene el valor de ejemplo. Configure la URL activa de RunPod o Google Colab en la pestaña 'Estado' o en el archivo .env."
        )

    url_destino = f"{url_base.rstrip('/')}{ruta}"
    headers = {"Content-Type": "image/jpeg"}
    if token:
        headers["X-API-Token"] = token

    async with httpx.AsyncClient(timeout=timeout, verify=False) as client:
        resp = await client.post(url_destino, content=img_bytes, headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Error HTTP {resp.status_code} desde INFERENCE_URL: {resp.text[:250]}")
        return resp.json()


# ==============================================================================
# 1. AUTENTICACIÓN CON GOOGLE OAUTH 2.0 (Sección 4.4 y 4.5)
# ==============================================================================
@app.get("/api/v1/auth/config", tags=["Autenticación"])
def obtener_config_oauth():
    """Devuelve el GOOGLE_CLIENT_ID público para inicializar el botón oficial de Google Sign-In en la web."""
    return {
        "google_client_id": GOOGLE_CLIENT_ID,
        "solo_google_oauth": True,
    }


@app.post("/api/v1/auth/google", response_model=AuthResponse, tags=["Autenticación"])
def login_con_google(req: GoogleAuthRequest, db: Session = Depends(get_db)):
    """
    Recibe el token de Google OAuth 2.0 desde la app móvil o la aplicación web,
    verifica la firma con Google, comprueba que el correo esté en la lista blanca (tabla usuarios)
    y devuelve el token JWT de sesión del sistema junto con el rol (administrador u operador).
    """
    token_recibido = req.token or req.id_token or req.access_token or ""
    info_google = verificar_token_google(token_recibido)
    usuario = validar_usuario_lista_blanca(db, info_google["email"], info_google.get("nombre"))
    jwt_sistema = crear_token_sesion(usuario)
    return {
        "access_token": jwt_sistema,
        "token_type": "bearer",
        "usuario": usuario,
    }


@app.post("/api/v1/auth/google-oauth-verify", response_model=AuthResponse, include_in_schema=False)
async def verificar_cuenta_google_lista_blanca(request: Request, db: Session = Depends(get_db)):
    """Valida una cuenta de Google contra la lista blanca de la BD (demostración de roles y rechazo 403)."""
    body = await request.json()
    email = (body.get("email") or "").lower().strip()
    nombre = body.get("nombre") or email
    usuario = validar_usuario_lista_blanca(db, email, nombre)
    jwt_sistema = crear_token_sesion(usuario)
    return {
        "access_token": jwt_sistema,
        "token_type": "bearer",
        "usuario": usuario,
    }


@app.get("/api/v1/auth/me", response_model=UsuarioOut, tags=["Autenticación"])
def perfil_actual(usuario: Usuario = Depends(obtener_usuario_actual)):
    """Devuelve los datos del usuario autenticado actualmente."""
    return usuario


# ==============================================================================
# 2. REGISTRO DE PASOS DESDE CASETA / APP MÓVIL Y TIEMPO REAL (Sección 4.3 y 4.5)
# ==============================================================================
@app.post("/api/v1/pasos/frame", tags=["Pasos y Caseta"])
async def procesar_frame_caseta(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    caseta_id: int = Form(default=1),
    imagen_b64: Optional[str] = Form(default=None),
    placa_override: Optional[str] = Form(default=None),
    categoria_override: Optional[str] = Form(default=None),
    ejes_override: Optional[int] = Form(default=None),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """
    Recibe un frame desde la app móvil (Modo Caseta a 2-5 fps) o desde el panel web,
    llama al endpoint de inferencia en la nube (INFERENCE_URL: M1+M2+M3),
    determina tarifa por categoría y ejes, valida saldo/registro, genera alertas si corresponde,
    guarda el paso y lo emite en tiempo real por WebSockets y SSE.
    """
    t_inicio_total = datetime.datetime.now(datetime.timezone.utc)
    img_bytes: Optional[bytes] = None

    if file is not None:
        img_bytes = await file.read()
    elif imagen_b64:
        b64_clean = imagen_b64.split(",", 1)[1] if "," in imagen_b64 else imagen_b64
        img_bytes = base64.b64decode(b64_clean)
    else:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            caseta_id = int(body.get("caseta_id", caseta_id))
            placa_override = body.get("placa_override") or placa_override
            categoria_override = body.get("categoria_override") or categoria_override
            ejes_override = body.get("ejes_override") or ejes_override
            b64 = body.get("imagen_b64") or body.get("image") or ""
            if b64:
                b64_clean = b64.split(",", 1)[1] if "," in b64 else b64
                img_bytes = base64.b64decode(b64_clean)
        else:
            raw = await request.body()
            if raw:
                img_bytes = raw

    resultado_inf: Dict[str, Any] = {}
    error_inferencia: Optional[str] = None

    if img_bytes:
        try:
            resultado_inf = await llamar_endpoint_inferencia(img_bytes, ruta="/predict")
        except Exception as exc:
            error_inferencia = str(exc)
            if not placa_override:
                raise HTTPException(
                    status_code=503,
                    detail=f"No se pudo completar la inferencia en INFERENCE_URL ({CONFIG_SISTEMA['inference_url']}): {error_inferencia}",
                )

    placa_leida = str(
        placa_override
        or resultado_inf.get("placa_leida")
        or resultado_inf.get("placa")
        or ""
    ).strip()
    placa_norm = normalizar_placa(
        placa_override or resultado_inf.get("placa_normalizada") or resultado_inf.get("placa") or placa_leida,
        corregir_posiciones=True,
    )
    confianza_ocr = float(resultado_inf.get("confianza_ocr") or resultado_inf.get("confianza") or 0.93)
    categoria_det = str(
        categoria_override or resultado_inf.get("categoria") or "auto"
    ).lower().strip()
    ejes_det = int(ejes_override or resultado_inf.get("ejes") or 2)
    latencia_inf = float(resultado_inf.get("latencia") or resultado_inf.get("latencia_ms") or 0.0)

    # Guardar imagen de evidencia (anotada por el servidor de inferencia o el frame original)
    nombre_archivo = f"paso_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}.jpg"
    ruta_archivo = os.path.join(UPLOADS_DIR, nombre_archivo)
    img_anotada_b64 = resultado_inf.get("imagen_anotada_b64", "")

    if img_anotada_b64:
        with open(ruta_archivo, "wb") as f:
            f.write(base64.b64decode(img_anotada_b64))
        imagen_url = f"/uploads/{nombre_archivo}"
    elif img_bytes:
        with open(ruta_archivo, "wb") as f:
            f.write(img_bytes)
        imagen_url = f"/uploads/{nombre_archivo}"
    else:
        imagen_url = f"/api/v1/evidencias/demo_{placa_norm or 'SINPLACA'}.svg"

    # Calcular tarifa según categoría detectada (M2) y número de ejes (M3)
    monto_tarifa = calcular_monto_tarifa(db, categoria_det, ejes_det)

    # Verificar estado del vehículo en la base de datos y generar alerta si corresponde (Sección 4.2)
    vehiculo = db.query(Vehiculo).filter(Vehiculo.placa == placa_norm).first() if placa_norm else None
    tipo_alerta: Optional[str] = None

    if not vehiculo:
        estado_paso = "no_registrada"
        tipo_alerta = "placa_no_registrada"
    elif not vehiculo.activo or float(vehiculo.saldo) < monto_tarifa:
        estado_paso = "sin_saldo"
        tipo_alerta = "sin_saldo"
    else:
        estado_paso = "aprobado"
        vehiculo.saldo = round(float(vehiculo.saldo) - monto_tarifa, 2)

    nuevo_paso = Paso(
        placa_leida=placa_leida or placa_norm or "ILEGIBLE",
        placa_normalizada=placa_norm or "ILEGIBLE",
        confianza_ocr=confianza_ocr,
        categoria_detectada=categoria_det,
        ejes_detectados=ejes_det,
        monto=monto_tarifa,
        caseta_id=caseta_id,
        usuario_id=usuario.id,
        imagen_url=imagen_url,
        estado=estado_paso,
    )
    db.add(nuevo_paso)
    db.commit()
    db.refresh(nuevo_paso)

    alerta_serializada = None
    if tipo_alerta:
        nueva_alerta = Alerta(
            paso_id=nuevo_paso.id,
            tipo=tipo_alerta,
            atendida=False,
        )
        db.add(nueva_alerta)
        db.commit()
        db.refresh(nueva_alerta)
        alerta_serializada = serializar_alerta(db, nueva_alerta)

    paso_serializado = serializar_paso(db, nuevo_paso)
    metricas = obtener_metricas_globales(db)

    # Emitir en tiempo real al panel web (WebSockets + SSE) sin recargar la página (Sección 4.3)
    await gestor_rt.emitir_evento(
        "nuevo_paso",
        {
            "paso": paso_serializado,
            "alerta": alerta_serializada,
            "metricas": metricas,
            "inferencia": {
                "latencia_ms": latencia_inf,
                "keypoints_ruedas": resultado_inf.get("keypoints_ruedas", []),
            },
        },
    )

    latencia_e2e_ms = round(
        (datetime.datetime.now(datetime.timezone.utc) - t_inicio_total).total_seconds() * 1000, 1
    )

    return {
        "exito": True,
        "placa": nuevo_paso.placa_normalizada,
        "placa_leida": nuevo_paso.placa_leida,
        "confianza": round(confianza_ocr, 3),
        "categoria": nuevo_paso.categoria_detectada,
        "ejes": nuevo_paso.ejes_detectados,
        "tarifa": monto_tarifa,
        "monto": monto_tarifa,
        "estado": nuevo_paso.estado,
        "latencia_inferencia_ms": latencia_inf,
        "latencia_total_ms": latencia_e2e_ms,
        "paso": paso_serializado,
        "alerta": alerta_serializada,
        "metricas": metricas,
    }


# ==============================================================================
# 3. CONSULTA DE PLACAS E HISTORIAL (Sección 4.5)
# ==============================================================================
@app.post("/api/v1/placas/consultar", tags=["Consultas de Placas"])
def consultar_placa_por_texto(
    req: ConsultaPlacaTextoRequest,
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Consulta una placa por texto, la normaliza y devuelve su estado entre los 4 estados del sistema."""
    return consultar_agente_qwen(db, mensaje_usuario=req.placa, placa_directa=req.placa, origen="texto")


@app.post("/api/v1/placas/consultar-imagen", tags=["Consultas de Placas"])
async def consultar_placa_por_imagen(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    imagen_b64: Optional[str] = Form(default=None),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """
    Consulta una placa enviando una imagen al modelo M1 + OCR en INFERENCE_URL
    y devuelve su estado en el sistema (los 4 estados del Agente Conversacional).
    """
    img_bytes: Optional[bytes] = None
    if file is not None:
        img_bytes = await file.read()
    elif imagen_b64:
        b64_clean = imagen_b64.split(",", 1)[1] if "," in imagen_b64 else imagen_b64
        img_bytes = base64.b64decode(b64_clean)
    else:
        ctype = request.headers.get("content-type", "")
        if "application/json" in ctype:
            body = await request.json()
            b64 = body.get("imagen_b64") or body.get("image") or ""
            if b64:
                b64_clean = b64.split(",", 1)[1] if "," in b64 else b64
                img_bytes = base64.b64decode(b64_clean)
        else:
            img_bytes = await request.body()

    if not img_bytes:
        raise HTTPException(status_code=400, detail="Debe adjuntar una imagen de la placa.")

    try:
        res_ocr = await llamar_endpoint_inferencia(img_bytes, ruta="/ocr-placa")
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Error al consultar M1+OCR en el endpoint de inferencia: {exc}",
        )

    placa_detectada = normalizar_placa(
        res_ocr.get("placa_normalizada") or res_ocr.get("placa") or "",
        corregir_posiciones=True,
    )
    conf_ocr = float(res_ocr.get("confianza") or 0.0)

    # Si la imagen no tiene una placa legible, indicarlo y pedir otra imagen (Sección 4.8)
    if not placa_detectada or len(placa_detectada) < 4 or conf_ocr < 0.20:
        return {
            "exito": False,
            "origen": "imagen",
            "placa_leida": res_ocr.get("placa_leida", ""),
            "placa_normalizada": "",
            "confianza_ocr": conf_ocr,
            "estado": "Placa ilegible",
            "respuesta": (
                "⚠️ **No se detectó una placa legible en la imagen enviada.** "
                "Por favor toma o sube otra fotografía con mejor iluminación y enfoque sobre la placa del vehículo."
            ),
        }

    respuesta_agente = consultar_agente_qwen(
        db,
        mensaje_usuario=f"Imagen de placa leída por OCR: {placa_detectada}",
        placa_directa=placa_detectada,
        origen="imagen",
    )
    respuesta_agente["confianza_ocr"] = round(conf_ocr, 3)
    respuesta_agente["latencia_ocr_ms"] = res_ocr.get("latencia", 0.0)
    return respuesta_agente


@app.get("/api/v1/placas/{placa}/historial", tags=["Consultas de Placas"])
def historial_por_placa(
    placa: str,
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Devuelve el historial completo de pasos de una placa normalizada."""
    datos = tool_consultar_placa_bd(db, placa)
    return {
        "placa_consultada": placa,
        "placa_normalizada": datos["placa_normalizada"],
        "estado": datos["estado"],
        "vehiculo": datos["vehiculo"],
        "total_pasos": datos["total_pasos"],
        "historial": datos["pasos"],
        "sugerencias_ocr": datos["sugerencias_ocr"],
    }


@app.get("/api/v1/casetas/{id}/resumen", tags=["Pasos y Caseta"])
def resumen_caseta_dia(
    id: int,
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Conteo de pasos y recaudación del día para una caseta específica (Sección 4.5)."""
    caseta = db.query(Caseta).filter(Caseta.id == id).first()
    if not caseta:
        raise HTTPException(status_code=404, detail=f"La caseta con id={id} no existe.")

    hoy_inicio = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    pasos_hoy = (
        db.query(Paso)
        .filter(Paso.caseta_id == id, Paso.created_at >= hoy_inicio)
        .all()
    )

    recaudacion_hoy = sum(float(p.monto) for p in pasos_hoy if p.estado == "aprobado")
    por_categoria: Dict[str, int] = {}
    for p in pasos_hoy:
        por_categoria[p.categoria_detectada] = por_categoria.get(p.categoria_detectada, 0) + 1

    return {
        "caseta_id": caseta.id,
        "nombre": caseta.nombre,
        "ubicacion": caseta.ubicacion,
        "fecha": hoy_inicio.strftime("%Y-%m-%d"),
        "total_pasos_hoy": len(pasos_hoy),
        "pasos_aprobados_hoy": sum(1 for p in pasos_hoy if p.estado == "aprobado"),
        "alertas_hoy": sum(1 for p in pasos_hoy if p.estado != "aprobado"),
        "recaudacion_dia_bs": round(recaudacion_hoy, 2),
        "desglose_categorias": por_categoria,
    }


# ==============================================================================
# 4. AGENTE CONVERSACIONAL QWEN (Sección 4.5 y 4.8)
# ==============================================================================
@app.post("/api/v1/agente/chat", tags=["Agente Conversacional Qwen"])
async def chat_agente_conversacional(
    request: Request,
    file: Optional[UploadFile] = File(default=None),
    mensaje: Optional[str] = Form(default=None),
    imagen_b64: Optional[str] = Form(default=None),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """
    Endpoint del Agente Conversacional con Qwen (Function Calling).
    Acepta consulta de placa por texto (JSON o Form) o por imagen (multipart file o imagen_b64).
    """
    texto_msg = mensaje or ""
    placa_directa = None
    b64_img = imagen_b64

    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body = await request.json()
        texto_msg = body.get("mensaje") or body.get("texto") or ""
        placa_directa = body.get("placa")
        b64_img = body.get("imagen_b64") or body.get("image")

    # Si el usuario envió una imagen al chat del agente, primero ejecutamos M1+OCR
    if file is not None or b64_img:
        return await consultar_placa_por_imagen(
            request=request,
            file=file,
            imagen_b64=b64_img,
            usuario=usuario,
            db=db,
        )

    return consultar_agente_qwen(
        db=db,
        mensaje_usuario=texto_msg,
        placa_directa=placa_directa,
        origen="texto",
    )


# ==============================================================================
# 5. CRUD DE VEHÍCULOS, PASOS, ALERTAS, TARIFAS, CASETAS Y USUARIOS (Sección 4.2)
# ==============================================================================
@app.get("/api/v1/dashboard/resumen", tags=["Panel en Tiempo Real"])
def resumen_dashboard(
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    pasos_recientes = db.query(Paso).order_by(Paso.created_at.desc()).limit(25).all()
    alertas_recientes = db.query(Alerta).order_by(Alerta.created_at.desc()).limit(20).all()
    casetas = db.query(Caseta).all()

    return {
        "metricas": obtener_metricas_globales(db),
        "pasos_recientes": [serializar_paso(db, p) for p in pasos_recientes],
        "alertas_recientes": [serializar_alerta(db, a) for a in alertas_recientes],
        "casetas": [{"id": c.id, "nombre": c.nombre, "ubicacion": c.ubicacion} for c in casetas],
    }


@app.get("/api/v1/vehiculos", response_model=List[VehiculoOut], tags=["Vehículos CRUD"])
def listar_vehiculos(
    q: Optional[str] = Query(default=None, description="Filtrar por placa o propietario"),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    query = db.query(Vehiculo)
    if q:
        q_clean = q.strip().upper()
        query = query.filter(
            (Vehiculo.placa.ilike(f"%{q_clean}%")) | (Vehiculo.propietario.ilike(f"%{q.strip()}%"))
        )
    return query.order_by(Vehiculo.id.desc()).all()


@app.post("/api/v1/vehiculos", response_model=VehiculoOut, tags=["Vehículos CRUD"])
def crear_vehiculo(
    datos: VehiculoCreate,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    placa_norm = normalizar_placa(datos.placa)
    if not placa_norm:
        raise HTTPException(status_code=400, detail="La placa no puede estar vacía.")
    existente = db.query(Vehiculo).filter(Vehiculo.placa == placa_norm).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"La placa {placa_norm} ya está registrada.")

    nuevo = Vehiculo(
        placa=placa_norm,
        propietario=datos.propietario.strip(),
        categoria=datos.categoria.lower().strip(),
        ejes=max(2, int(datos.ejes)),
        saldo=round(float(datos.saldo), 2),
        activo=datos.activo,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.put("/api/v1/vehiculos/{vehiculo_id}", response_model=VehiculoOut, tags=["Vehículos CRUD"])
def actualizar_vehiculo(
    vehiculo_id: int,
    datos: VehiculoUpdate,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado.")

    if datos.placa is not None:
        veh.placa = normalizar_placa(datos.placa)
    if datos.propietario is not None:
        veh.propietario = datos.propietario.strip()
    if datos.categoria is not None:
        veh.categoria = datos.categoria.lower().strip()
    if datos.ejes is not None:
        veh.ejes = max(2, int(datos.ejes))
    if datos.saldo is not None:
        veh.saldo = round(float(datos.saldo), 2)
    if datos.activo is not None:
        veh.activo = datos.activo

    db.commit()
    db.refresh(veh)
    return veh


@app.delete("/api/v1/vehiculos/{vehiculo_id}", tags=["Vehículos CRUD"])
def eliminar_vehiculo(
    vehiculo_id: int,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    veh = db.query(Vehiculo).filter(Vehiculo.id == vehiculo_id).first()
    if not veh:
        raise HTTPException(status_code=404, detail="Vehículo no encontrado.")
    db.delete(veh)
    db.commit()
    return {"eliminado": True, "id": vehiculo_id}


@app.get("/api/v1/pasos", tags=["Pasos y Caseta"])
def listar_historial_pasos(
    placa: Optional[str] = Query(default=None),
    estado: Optional[str] = Query(default=None),
    limite: int = Query(default=50, le=200),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    query = db.query(Paso)
    if placa:
        p_norm = normalizar_placa(placa)
        query = query.filter(Paso.placa_normalizada.ilike(f"%{p_norm}%"))
    if estado:
        query = query.filter(Paso.estado == estado)
    filas = query.order_by(Paso.created_at.desc()).limit(limite).all()
    return [serializar_paso(db, p) for p in filas]


@app.get("/api/v1/alertas", tags=["Alertas"])
def listar_alertas(
    solo_pendientes: bool = Query(default=False),
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    query = db.query(Alerta)
    if solo_pendientes:
        query = query.filter(Alerta.atendida == False)
    filas = query.order_by(Alerta.created_at.desc()).limit(100).all()
    return [serializar_alerta(db, a) for a in filas]


@app.patch("/api/v1/alertas/{alerta_id}/atender", tags=["Alertas"])
async def atender_alerta(
    alerta_id: int,
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    alerta = db.query(Alerta).filter(Alerta.id == alerta_id).first()
    if not alerta:
        raise HTTPException(status_code=404, detail="Alerta no encontrada.")
    alerta.atendida = True
    db.commit()
    db.refresh(alerta)
    alerta_ser = serializar_alerta(db, alerta)
    await gestor_rt.emitir_evento(
        "alerta_atendida",
        {"alerta": alerta_ser, "metricas": obtener_metricas_globales(db)},
    )
    return alerta_ser


@app.get("/api/v1/tarifas", response_model=List[TarifaOut], tags=["Administración"])
def listar_tarifas(
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return db.query(Tarifa).order_by(Tarifa.categoria, Tarifa.ejes).all()


@app.post("/api/v1/tarifas", response_model=TarifaOut, tags=["Administración"])
def guardar_tarifa(
    datos: TarifaCreate,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    cat = datos.categoria.lower().strip()
    existente = db.query(Tarifa).filter(Tarifa.categoria == cat, Tarifa.ejes == datos.ejes).first()
    if existente:
        existente.monto = round(float(datos.monto), 2)
        db.commit()
        db.refresh(existente)
        return existente
    nueva = Tarifa(categoria=cat, ejes=datos.ejes, monto=round(float(datos.monto), 2))
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@app.get("/api/v1/casetas", response_model=List[CasetaOut], tags=["Administración"])
def listar_casetas(
    usuario: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return db.query(Caseta).order_by(Caseta.id).all()


@app.post("/api/v1/casetas", response_model=CasetaOut, tags=["Administración"])
def crear_caseta(
    datos: CasetaCreate,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    nueva = Caseta(nombre=datos.nombre.strip(), ubicacion=datos.ubicacion.strip())
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


@app.get("/api/v1/usuarios", response_model=List[UsuarioOut], tags=["Administración"])
def listar_usuarios_lista_blanca(
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    return db.query(Usuario).order_by(Usuario.id).all()


@app.post("/api/v1/usuarios", response_model=UsuarioOut, tags=["Administración"])
def agregar_usuario_lista_blanca(
    datos: UsuarioCreate,
    usuario: Usuario = Depends(exigir_administrador),
    db: Session = Depends(get_db),
):
    correo = datos.email_google.lower().strip()
    existente = db.query(Usuario).filter(Usuario.email_google == correo).first()
    if existente:
        existente.nombre = datos.nombre.strip()
        existente.rol = datos.rol.lower().strip()
        existente.activo = datos.activo
        db.commit()
        db.refresh(existente)
        return existente
    nuevo = Usuario(
        email_google=correo,
        nombre=datos.nombre.strip(),
        rol=datos.rol.lower().strip(),
        activo=datos.activo,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


# ==============================================================================
# 6. ESTADO DEL ENDPOINT DE INFERENCIA EN RUNPOD / COLAB (Sección 4.2)
# ==============================================================================
@app.get("/api/v1/estado/inferencia", tags=["Estado de Inferencia"])
async def verificar_estado_inferencia(
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    """
    Consulta en vivo el endpoint /health del servidor de inferencia configurado en INFERENCE_URL
    (RunPod o Google Colab) e informa latencia, estado, GPU y modelos cargados.
    """
    url_base = CONFIG_SISTEMA["inference_url"]
    t0 = datetime.datetime.now(datetime.timezone.utc)

    try:
        async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
            r = await client.get(f"{url_base.rstrip('/')}/health")
            lat_ms = round((datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds() * 1000, 1)
            if r.status_code == 200:
                data = r.json()
                return {
                    "online": True,
                    "inference_url": url_base,
                    "latencia_ping_ms": lat_ms,
                    "detalle_servidor": data,
                    "qwen_model": os.environ.get("QWEN_MODEL", "qwen-plus"),
                }
            return {
                "online": False,
                "inference_url": url_base,
                "latencia_ping_ms": lat_ms,
                "error": f"HTTP {r.status_code}: {r.text[:200]}",
            }
    except Exception as exc:
        lat_ms = round((datetime.datetime.now(datetime.timezone.utc) - t0).total_seconds() * 1000, 1)
        return {
            "online": False,
            "inference_url": url_base,
            "latencia_ping_ms": lat_ms,
            "error": str(exc),
        }


@app.put("/api/v1/estado/inferencia/config", tags=["Estado de Inferencia"])
def actualizar_url_inferencia(
    datos: ConfigInferenciaRequest,
    usuario: Usuario = Depends(exigir_administrador),
):
    """
    Permite al Administrador cambiar INFERENCE_URL en caliente entre RunPod y Google Colab.
    """
    CONFIG_SISTEMA["inference_url"] = datos.inference_url.strip().rstrip("/")
    if datos.inference_api_token is not None and datos.inference_api_token.strip():
        CONFIG_SISTEMA["inference_api_token"] = datos.inference_api_token.strip()
    return {
        "actualizado": True,
        "inference_url": CONFIG_SISTEMA["inference_url"],
    }


# ==============================================================================
# 7. TIEMPO REAL: WEBSOCKETS + SERVER-SENT EVENTS (Sección 4.3)
# ==============================================================================
@app.websocket("/ws/eventos")
async def websocket_panel_tiempo_real(websocket: WebSocket):
    await gestor_rt.conectar_ws(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        gestor_rt.desconectar_ws(websocket)


@app.get("/api/v1/eventos/stream", tags=["Panel en Tiempo Real"])
async def sse_panel_tiempo_real(request: Request):
    """Stream Server-Sent Events (SSE) como respaldo compatible con cualquier proxy HTTPS o hosting compartido."""
    cola = gestor_rt.suscribir_sse()

    async def generador_eventos():
        try:
            yield "event: conectado\ndata: {\"estado\": \"conectado_sse\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    mensaje = await asyncio.wait_for(cola.get(), timeout=20.0)
                    yield f"data: {mensaje}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            gestor_rt.desuscribir_sse(cola)

    return StreamingResponse(generador_eventos(), media_type="text/event-stream")


# ==============================================================================
# 8. GENERADOR DE IMÁGENES DE EVIDENCIA SVG PARA DEMO Y FRONTEND SPA
# ==============================================================================
@app.get("/api/v1/evidencias/demo_{nombre_placa}.svg", include_in_schema=False)
def generar_evidencia_svg_demo(nombre_placa: str):
    placa = normalizar_placa(nombre_placa.replace(".svg", "")) or "1852PHD"
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="380" viewBox="0 0 640 380">
      <rect width="640" height="380" fill="#0f172a"/>
      <rect x="20" y="20" width="600" height="340" rx="12" fill="#1e293b" stroke="#334155" stroke-width="2"/>
      <!-- Silueta segmentación M2 -->
      <rect x="110" y="105" width="420" height="175" rx="18" fill="#3b82f6" fill-opacity="0.32" stroke="#38bdf8" stroke-width="3"/>
      <text x="125" y="96" fill="#38bdf8" font-family="monospace" font-size="15" font-weight="bold">M2 SEG: VEHICULO DETECTADO (0.94)</text>
      <!-- Ruedas y Keypoints M3 -->
      <circle cx="195" cy="285" r="32" fill="#0f172a" stroke="#64748b" stroke-width="5"/>
      <circle cx="195" cy="285" r="8" fill="#facc15"/>
      <text x="178" y="335" fill="#facc15" font-family="monospace" font-size="14" font-weight="bold">KP Eje 1</text>
      <circle cx="445" cy="285" r="32" fill="#0f172a" stroke="#64748b" stroke-width="5"/>
      <circle cx="445" cy="285" r="8" fill="#facc15"/>
      <text x="428" y="335" fill="#facc15" font-family="monospace" font-size="14" font-weight="bold">KP Eje 2</text>
      <!-- Placa M1 + OCR -->
      <rect x="235" y="195" width="170" height="58" rx="6" fill="#f8fafc" stroke="#22c55e" stroke-width="4"/>
      <text x="285" y="212" fill="#1e40af" font-family="sans-serif" font-size="11" font-weight="bold">BOLIVIA</text>
      <text x="252" y="242" fill="#0f172a" font-family="monospace" font-size="26" font-weight="bold">{placa}</text>
      <text x="235" y="185" fill="#22c55e" font-family="monospace" font-size="14" font-weight="bold">M1+OCR: {placa}</text>
    </svg>"""
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def servir_aplicacion_web():
    ruta_html = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(ruta_html):
        return FileResponse(ruta_html)
    return HTMLResponse("<h1>Sistema de Control de Peaje - API Activa</h1>")
