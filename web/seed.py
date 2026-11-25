"""
Poblado Inicial de la Base de Datos (Sección 4.4 y 4.6):
  - Autoriza como Administrador a doc.alvaro.pinto.ma@unifranz.edu.bo y jhairpinto8@gmail.com
  - Crea un usuario Operador de ejemplo
  - Crea 3 casetas de peaje
  - Crea el tarifario completo por categoría (moto, auto, minibus, bus, camion) y número de ejes
  - Registra 24 vehículos de prueba (>= 20 obligatorios) incluyendo la mitad de las placas reales
    del video de prueba (WhatsApp Video 2026-11-25):
      * REGISTRADAS del video (4 placas):
          - 2673TYH (00:03 Toyota Corolla Wagon Blanco Taxi -> Con saldo Bs. 120 y paso previo -> "Registrada y con paso")
          - 2760ZTA (00:12 Toyota Probox Blanco Taxi -> Con saldo Bs. 85 -> "Registrada sin paso" / Aprobado)
          - 5324DZG (00:17 Toyota Rush SUV Plateada -> Sin saldo Bs. 0 -> Alerta 'sin_saldo')
          - 6363KGD (00:33 Suzuki Jimny Oscuro -> Con saldo Bs. 150 -> "Registrada sin paso" / Aprobado)
      * NO REGISTRADAS del video (3 placas, dejadas fuera del padrón para disparar alerta 'placa_no_registrada'):
          - 6672LXL (00:08 Suzuki Jimny Azul Celeste -> "Identificada no registrada")
          - 4011XKH (00:30 Toyota Probox Azul Oscuro -> Al pasar en el video genera Alerta en vivo)
          - 2030ZUD (00:37 Toyota Corolla Wagon Plateado -> Al pasar en el video genera Alerta en vivo)
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
            Caseta(nombre="Caseta 3 - Transporte Pesado", ubicacion="Vía Viacha - Control Carga Pesada"),
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
    vehiculos_video_registrados = [
        {
            "placa": "2673TYH",
            "propietario": "Juan Carlos Quispe (Toyota Corolla Taxi Blanco)",
            "categoria": "auto",
            "ejes": 2,
            "saldo": 120.0,
            "activo": True,
        },
        {
            "placa": "2760ZTA",
            "propietario": "Roberto Mamani Condori (Toyota Probox Blanco)",
            "categoria": "auto",
            "ejes": 2,
            "saldo": 85.0,
            "activo": True,
        },
        {
            "placa": "5324DZG",
            "propietario": "María Elena Vargas (Toyota Rush SUV Plateada)",
            "categoria": "auto",
            "ejes": 2,
            "saldo": 0.0,  # Sin saldo -> Alerta 'sin_saldo'
            "activo": True,
        },
        {
            "placa": "6363KGD",
            "propietario": "Fernando Siles Torrez (Suzuki Jimny Oscuro)",
            "categoria": "auto",
            "ejes": 2,
            "saldo": 150.0,
            "activo": True,
        },
    ]

    if db.query(Vehiculo).count() == 0:
        vehiculos_prueba = [
            Vehiculo(**v) for v in vehiculos_video_registrados
        ] + [
            # Otros autos particulares
            Vehiculo(placa="1852PHD", propietario="Carlos Mendoza Quispe", categoria="auto", ejes=2, saldo=120.0, activo=True),
            Vehiculo(placa="2419TKR", propietario="María Fernanda Rojas", categoria="auto", ejes=2, saldo=85.0, activo=True),
            Vehiculo(placa="3045ABC", propietario="Jorge Luis Mamani", categoria="auto", ejes=2, saldo=64.0, activo=True),
            # Minibuses (servicio público / trufis)
            Vehiculo(placa="3810RTY", propietario="Sindicato Eduardo Avaroa - Unidad 14", categoria="minibus", ejes=2, saldo=210.0, activo=True),
            Vehiculo(placa="4720UIO", propietario="Sindicato Litoral - Unidad 08", categoria="minibus", ejes=2, saldo=175.0, activo=True),
            Vehiculo(placa="5612PAS", propietario="Cooperativa 16 de Julio", categoria="minibus", ejes=2, saldo=5.0, activo=True),
            Vehiculo(placa="2184MNB", propietario="Ramiro Choquehuanca", categoria="minibus", ejes=2, saldo=130.0, activo=True),
            Vehiculo(placa="3390VFR", propietario="Asociación Transporte del Sur", categoria="minibus", ejes=2, saldo=90.0, activo=True),
            # Camiones (transporte pesado de 2, 3, 4 y 5 ejes)
            Vehiculo(placa="4029CDX", propietario="Transportes Andinos S.R.L.", categoria="camion", ejes=3, saldo=450.0, activo=True),
            Vehiculo(placa="5108TRK", propietario="Logística Altiplano S.A.", categoria="camion", ejes=4, saldo=620.0, activo=True),
            Vehiculo(placa="3674HJK", propietario="Importadora Copacabana", categoria="camion", ejes=3, saldo=0.0, activo=True),
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
    else:
        # Asegurar que las 4 placas registradas del video existan en BD y las 3 no registradas NO estén en el padrón
        for v_data in vehiculos_video_registrados:
            existente = db.query(Vehiculo).filter(Vehiculo.placa == v_data["placa"]).first()
            if not existente:
                db.add(Vehiculo(**v_data))
        for placa_no_reg in ("6672LXL", "4011XKH", "2030ZUD"):
            v_borrar = db.query(Vehiculo).filter(Vehiculo.placa == placa_no_reg).first()
            if v_borrar:
                db.delete(v_borrar)
        db.commit()

    # --------------------------------------------------------------------------
    # 5. PASOS Y ALERTAS INICIALES CON PLACAS DEL VIDEO PARA LOS 4 ESTADOS
    # --------------------------------------------------------------------------
    if db.query(Paso).count() == 0:
        admin_user = db.query(Usuario).first()
        uid = admin_user.id if admin_user else 1
        ahora = datetime.datetime.now(datetime.timezone.utc)

        # Paso 1: 2673TYH (Toyota Corolla Taxi del video -> "Registrada y con paso")
        p1 = Paso(
            placa_leida="2673-TYH",
            placa_normalizada="2673TYH",
            confianza_ocr=0.96,
            categoria_detectada="auto",
            ejes_detectados=2,
            pasajeros=2,
            monto=7.0,
            caseta_id=1,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_2673TYH.svg",
            estado="aprobado",
            created_at=ahora - datetime.timedelta(minutes=30),
        )
        # Paso 2: 5324DZG (Toyota Rush SUV Plateada del video -> Registrada pero SIN SALDO -> Alerta 'sin_saldo')
        p2 = Paso(
            placa_leida="5324-DZG",
            placa_normalizada="5324DZG",
            confianza_ocr=0.93,
            categoria_detectada="auto",
            ejes_detectados=2,
            pasajeros=1,
            monto=7.0,
            caseta_id=1,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_5324DZG.svg",
            estado="sin_saldo",
            created_at=ahora - datetime.timedelta(minutes=16),
        )
        # Paso 3: 6672LXL (Suzuki Jimny Azul Celeste del video -> Detectada pero NO REGISTRADA -> "Identificada no registrada")
        p3 = Paso(
            placa_leida="6672-LXL",
            placa_normalizada="6672LXL",
            confianza_ocr=0.94,
            categoria_detectada="auto",
            ejes_detectados=2,
            pasajeros=2,
            monto=7.0,
            caseta_id=2,
            usuario_id=uid,
            imagen_url="/api/v1/evidencias/demo_6672LXL.svg",
            estado="no_registrada",
            created_at=ahora - datetime.timedelta(minutes=8),
        )
        db.add_all([p1, p2, p3])
        db.commit()
        db.refresh(p2)
        db.refresh(p3)

        alerta_saldo = Alerta(
            paso_id=p2.id,
            tipo="sin_saldo",
            atendida=False,
            created_at=p2.created_at,
        )
        alerta_evasion = Alerta(
            paso_id=p3.id,
            tipo="placa_no_registrada",
            atendida=False,
            created_at=p3.created_at,
        )
        db.add_all([alerta_saldo, alerta_evasion])
        db.commit()
