"""
Poblado Inicial de la Base de Datos (Sección 4.4 y 4.6):
  - Autoriza como Administrador a doc.alvaro.pinto.ma@unifranz.edu.bo y jhairpinto8@gmail.com
  - Crea un usuario Operador de ejemplo
  - Crea 3 casetas de peaje
  - Crea el tarifario completo por categoría (moto, auto, minibus, bus, camion) y número de ejes
  - Registra 24 vehículos de prueba (>= 20 obligatorios) cubriendo:
      * Vehículos con saldo y pasos registrados ("Registrada y con paso")
      * Vehículos registrados sin pasos ("Registrada sin paso")
      * Vehículos registrados sin saldo (para generar alerta 'sin_saldo')
  - Registra pasos iniciales incluyendo una placa captada por cámara pero no registrada
    ("Identificada no registrada" + alerta 'placa_no_registrada')
"""
import datetime
import os
from sqlalchemy.orm import Session

from models import Alerta, Caseta, Paso, Tarifa, Usuario, Vehiculo


def ejecutar_seed(db: Session):
    # --------------------------------------------------------------------------
    # 1. USUARIOS AUTORIZADOS EN LISTA BLANCA (GOOGLE OAUTH 2.0)
    # --------------------------------------------------------------------------
    usuarios_iniciales = [
        {
            "email_google": "doc.alvaro.pinto.ma@unifranz.edu.bo",
            "nombre": "Ing. Alvaro Pinto Mamani (Docente Admin)",
            "rol": "administrador",
            "activo": True,
        },
        {
            "email_google": "jhairpinto8@gmail.com",
            "nombre": "Jhair Pinto (Administrador)",
            "rol": "administrador",
            "activo": True,
        },
        {
            "email_google": "operador.peaje.unifranz@gmail.com",
            "nombre": "Operador Caseta 1",
            "rol": "operador",
            "activo": True,
        },
    ]

    # Agregar correos extra de ADMIN_EMAILS si están en .env
    extra_admins = os.environ.get("ADMIN_EMAILS", "")
    for correo in extra_admins.split(","):
        c = correo.strip().lower()
        if c and not any(u["email_google"] == c for u in usuarios_iniciales):
            usuarios_iniciales.append(
                {
                    "email_google": c,
                    "nombre": f"Admin ({c.split('@')[0]})",
                    "rol": "administrador",
                    "activo": True,
                }
            )

    for u_data in usuarios_iniciales:
        existe = db.query(Usuario).filter(Usuario.email_google == u_data["email_google"]).first()
        if not existe:
            db.add(Usuario(**u_data))
        else:
            existe.rol = u_data["rol"]
            existe.activo = True
    db.commit()

    # --------------------------------------------------------------------------
    # 2. CASETAS DE PEAJE
    # --------------------------------------------------------------------------
    if db.query(Caseta).count() == 0:
        casetas = [
            Caseta(nombre="Caseta 1 - Autopista Carril Norte", ubicacion="Km 12 Autopista La Paz - El Alto"),
            Caseta(nombre="Caseta 2 - Autopista Carril Sur", ubicacion="Km 12 Autopista El Alto - La Paz"),
            Caseta(nombre="Caseta 3 - Transporte Pesado", ubicacion=" Vía Viacha - Control Carga Pesada"),
        ]
        db.add_all(casetas)
        db.commit()

    # --------------------------------------------------------------------------
    # 3. TARIFAS EN BOLIVIANOS (Bs.) POR CATEGORÍA Y EJES
    # --------------------------------------------------------------------------
    if db.query(Tarifa).count() == 0:
        tarifas = [
            Tarifa(categoria="moto", ejes=2, monto=3.0),
            Tarifa(categoria="auto", ejes=2, monto=7.0),
            Tarifa(categoria="minibus", ejes=2, monto=10.0),
            Tarifa(categoria="bus", ejes=2, monto=15.0),
            Tarifa(categoria="bus", ejes=3, monto=20.0),
            Tarifa(categoria="bus", ejes=4, monto=25.0),
            Tarifa(categoria="camion", ejes=2, monto=15.0),
            Tarifa(categoria="camion", ejes=3, monto=22.0),
            Tarifa(categoria="camion", ejes=4, monto=30.0),
            Tarifa(categoria="camion", ejes=5, monto=38.0),
            Tarifa(categoria="camion", ejes=6, monto=45.0),
        ]
        db.add_all(tarifas)
        db.commit()

    # --------------------------------------------------------------------------
    # 4. VEHÍCULOS DE PRUEBA (24 VEHÍCULOS >= 20 MÍNIMOS OBLIGATORIOS)
    # --------------------------------------------------------------------------
    if db.query(Vehiculo).count() == 0:
        vehiculos_prueba = [
            # Autos particulares
            Vehiculo(placa="1852PHD", propietario="Carlos Mendoza Quispe", categoria="auto", ejes=2, saldo=120.0, activo=True),
            Vehiculo(placa="2419TKR", propietario="María Fernanda Rojas", categoria="auto", ejes=2, saldo=85.0, activo=True),
            Vehiculo(placa="3045ABC", propietario="Jorge Luis Mamani", categoria="auto", ejes=2, saldo=64.0, activo=True),
            Vehiculo(placa="4198LKM", propietario="Ana Gabriela Vargas", categoria="auto", ejes=2, saldo=0.0, activo=True),   # Sin saldo -> Alerta
            Vehiculo(placa="5280BNC", propietario="Roberto Siles Torrez", categoria="auto", ejes=2, saldo=150.0, activo=True),
            Vehiculo(placa="1049XYZ", propietario="Lucía Condori Flores", categoria="auto", ejes=2, saldo=95.0, activo=True),
            Vehiculo(placa="2951DFG", propietario="Pedro Pablo Gutiérrez", categoria="auto", ejes=2, saldo=42.0, activo=True),
            # Minibuses (servicio público / trufis)
            Vehiculo(placa="3810RTY", propietario="Sindicato Eduardo Avaroa - Unidad 14", categoria="minibus", ejes=2, saldo=210.0, activo=True),
            Vehiculo(placa="4720UIO", propietario="Sindicato Litoral - Unidad 08", categoria="minibus", ejes=2, saldo=175.0, activo=True),
            Vehiculo(placa="5612PAS", propietario="Cooperativa 16 de Julio", categoria="minibus", ejes=2, saldo=5.0, activo=True),  # Saldo insuficiente (<10 Bs)
            Vehiculo(placa="2184MNB", propietario="Ramiro Choquehuanca", categoria="minibus", ejes=2, saldo=130.0, activo=True),
            Vehiculo(placa="3390VFR", propietario="Asociación Transporte del Sur", categoria="minibus", ejes=2, saldo=90.0, activo=True),
            # Camiones (transporte pesado de 2, 3, 4 y 5 ejes)
            Vehiculo(placa="4029CDX", propietario="Transportes Andinos S.R.L.", categoria="camion", ejes=3, saldo=450.0, activo=True),
            Vehiculo(placa="5108TRK", propietario="Logística Altiplano S.A.", categoria="camion", ejes=4, saldo=620.0, activo=True),
            Vehiculo(placa="3674HJK", propietario="Importadora Copacabana", categoria="camion", ejes=3, saldo=0.0, activo=True),    # Sin saldo -> Alerta
            Vehiculo(placa="4892QWE", propietario="Transporte Pesado Illimani", categoria="camion", ejes=5, saldo=800.0, activo=True),
            Vehiculo(placa="2765ZXC", propietario="Distribuidora Oriental", categoria="camion", ejes=2, saldo=180.0, activo=True),
            Vehiculo(placa="5931PLM", propietario="Constructora Cumbre S.R.L.", categoria="camion", ejes=4, saldo=310.0, activo=True),
            # Buses / Flotas
            Vehiculo(placa="4410BUS", propietario="Trans Copacabana S.A. - Bus 22", categoria="bus", ejes=3, saldo=540.0, activo=True),
            Vehiculo(placa="5329FLT", propietario="Flota Bolívar - Unidad 05", categoria="bus", ejes=3, saldo=480.0, activo=True),
            Vehiculo(placa="3195OMN", propietario="Expreso Mopar S.R.L.", categoria="bus", ejes=4, saldo=390.0, activo=True),
            # Motocicletas
            Vehiculo(placa="1540MTA", propietario="Diego Armando Torrico", categoria="moto", ejes=2, saldo=45.0, activo=True),
            Vehiculo(placa="2873MTB", propietario="Valeria Paz Campero", categoria="moto", ejes=2, saldo=30.0, activo=True),
            Vehiculo(placa="3904MTC", propietario="Sergio Alarcón Zeballos", categoria="moto", ejes=2, saldo=60.0, activo=True),
        ]
        db.add_all(vehiculos_prueba)
        db.commit()

    # --------------------------------------------------------------------------
    # 5. PASOS Y ALERTAS INICIALES PARA DEMOSTRAR LOS 4 ESTADOS DEL AGENTE
    # --------------------------------------------------------------------------
    if db.query(Paso).count() == 0:
        admin_user = db.query(Usuario).first()
        uid = admin_user.id if admin_user else 1
        ahora = datetime.datetime.now(datetime.timezone.utc)

        # Paso 1: Vehículo registrado con paso exitoso (1852PHD -> "Registrada y con paso")
        p1 = Paso(
            placa_leida="1852-PHD",
            placa_normalizada="1852PHD",
            confianza_ocr=0.96,
            categoria_detectada="auto",
            ejes_detectados=2,
            monto=7.0,
            caseta_id=1,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_1852PHD.svg",
            estado="aprobado",
            created_at=ahora - datetime.timedelta(minutes=35),
        )
        # Paso 2: Camión pesado 3 ejes registrado con paso exitoso (4029CDX -> "Registrada y con paso")
        p2 = Paso(
            placa_leida="4029 CDX",
            placa_normalizada="4029CDX",
            confianza_ocr=0.94,
            categoria_detectada="camion",
            ejes_detectados=3,
            monto=22.0,
            caseta_id=3,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_4029CDX.svg",
            estado="aprobado",
            created_at=ahora - datetime.timedelta(minutes=22),
        )
        # Paso 3: Vehículo registrado pero SIN SALDO (4198LKM -> genera Alerta 'sin_saldo')
        p3 = Paso(
            placa_leida="4198-LKM",
            placa_normalizada="4198LKM",
            confianza_ocr=0.92,
            categoria_detectada="auto",
            ejes_detectados=2,
            monto=7.0,
            caseta_id=1,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_4198LKM.svg",
            estado="sin_saldo",
            created_at=ahora - datetime.timedelta(minutes=14),
        )
        # Paso 4: Placa detectada por cámara pero NO REGISTRADA en BD (9981EVA -> "Identificada no registrada" + Alerta)
        p4 = Paso(
            placa_leida="9981-EVA",
            placa_normalizada="9981EVA",
            confianza_ocr=0.91,
            categoria_detectada="camion",
            ejes_detectados=3,
            monto=22.0,
            caseta_id=2,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_9981EVA.svg",
            estado="no_registrada",
            created_at=ahora - datetime.timedelta(minutes=6),
        )
        db.add_all([p1, p2, p3, p4])
        db.commit()
        db.refresh(p3)
        db.refresh(p4)

        alerta_saldo = Alerta(
            paso_id=p3.id,
            tipo="sin_saldo",
            atendida=False,
            created_at=p3.created_at,
        )
        alerta_evasion = Alerta(
            paso_id=p4.id,
            tipo="placa_no_registrada",
            atendida=False,
            created_at=p4.created_at,
        )
        db.add_all([alerta_saldo, alerta_evasion])
        db.commit()
