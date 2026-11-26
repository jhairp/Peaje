"""
Poblado Inicial de la Base de Datos (Sección 4.4 y 4.6):
  - Autoriza como Administrador a doc.alvaro.pinto.ma@unifranz.edu.bo y jhairpinto8@gmail.com
  - Crea un usuario Operador de ejemplo
  - Crea 3 casetas de peaje
  - Crea el tarifario completo por categoría (moto, auto, minibus, bus, camion) y número de ejes
  - Registra los vehículos del video de prueba (la mitad registrados y la otra mitad no registrados)
    y los vehículos e historial de pasos reales de la carpeta 'placas pasos' (/static/pasos_img/*.jpg).
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
    # 4. VEHÍCULOS EN EL PADRÓN (4 DEL VIDEO + 18 DE LAS IMÁGENES + EXTRAS >= 24)
    # --------------------------------------------------------------------------
    catalogo_vehiculos = [
        # --- Mitad de placas del video en TV registradas (4 placas) ---
        {"placa": "2673TYH", "propietario": "Juan Carlos Quispe (Toyota Corolla Taxi Blanco)", "categoria": "auto", "ejes": 2, "saldo": 120.0, "activo": True},
        {"placa": "2760ZTA", "propietario": "Roberto Mamani Condori (Toyota Probox Blanco)", "categoria": "auto", "ejes": 2, "saldo": 85.0, "activo": True},
        {"placa": "5324DZG", "propietario": "María Elena Vargas (Toyota Rush SUV Plateada)", "categoria": "auto", "ejes": 2, "saldo": 0.0, "activo": True},
        {"placa": "6363KGD", "propietario": "Fernando Siles Torrez (Suzuki Jimny Oscuro)", "categoria": "auto", "ejes": 2, "saldo": 150.0, "activo": True},
        # --- Vehículos de las fotografías reales de 'placas pasos' ---
        {"placa": "653037", "propietario": "Rashid Al-Khalifa (Toyota iQ Plateado)", "categoria": "auto", "ejes": 2, "saldo": 95.0, "activo": True},
        {"placa": "190627", "propietario": "Tariq Salman (Toyota Crown Plateado)", "categoria": "auto", "ejes": 2, "saldo": 110.0, "activo": True},
        {"placa": "32789", "propietario": "Karim Mansoor (Subaru WRX STI Negro)", "categoria": "auto", "ejes": 2, "saldo": 140.0, "activo": True},
        {"placa": "582034", "propietario": "Nasser Al-Dosari (Nissan Skyline Blanco)", "categoria": "auto", "ejes": 2, "saldo": 0.0, "activo": True},
        {"placa": "2979", "propietario": "Omar Farooq (Lotus Emira Rojo)", "categoria": "auto", "ejes": 2, "saldo": 200.0, "activo": True},
        {"placa": "07D40426", "propietario": "Liam O'Connor (Mazda MX-5 Gris)", "categoria": "auto", "ejes": 2, "saldo": 75.0, "activo": True},
        {"placa": "232D17482", "propietario": "Sean Murphy (Porsche 911 Carrera)", "categoria": "auto", "ejes": 2, "saldo": 250.0, "activo": True},
        {"placa": "241D24258", "propietario": "Conor Walsh (Volkswagen Golf GTI)", "categoria": "auto", "ejes": 2, "saldo": 90.0, "activo": True},
        {"placa": "ZV45288", "propietario": "Hook & Ladder Catering (Furgón Citroën H)", "categoria": "camion", "ejes": 2, "saldo": 160.0, "activo": True},
        {"placa": "AA50689", "propietario": "Henrik Larsen (Land Rover Discovery)", "categoria": "auto", "ejes": 2, "saldo": 130.0, "activo": True},
        {"placa": "AS32347", "propietario": "Ingrid Solberg (Volkswagen Polo Celeste)", "categoria": "auto", "ejes": 2, "saldo": 80.0, "activo": True},
        {"placa": "AA59357", "propietario": "Magnus Johansen (Toyota Auris Celeste)", "categoria": "auto", "ejes": 2, "saldo": 105.0, "activo": True},
        {"placa": "ZE61026", "propietario": "Kari Nilsen (Nissan Micra Morado)", "categoria": "auto", "ejes": 2, "saldo": 0.0, "activo": True},
        {"placa": "BT92118", "propietario": "Erik Haugen (BMW X5 Negro)", "categoria": "auto", "ejes": 2, "saldo": 180.0, "activo": True},
        {"placa": "23KPAP", "propietario": "Michael Carter (Tesla Model 3 Negro)", "categoria": "auto", "ejes": 2, "saldo": 145.0, "activo": True},
        {"placa": "VSA530", "propietario": "Winchester Logistics (Chevrolet Express Van)", "categoria": "minibus", "ejes": 2, "saldo": 190.0, "activo": True},
        {"placa": "8217NT", "propietario": "Sarah Jenkins (Kia Sedona Minivan)", "categoria": "minibus", "ejes": 2, "saldo": 115.0, "activo": True},
        {"placa": "RJBF8", "propietario": "Robert J. Blake (Ferrari F8 Spider Amarillo)", "categoria": "auto", "ejes": 2, "saldo": 300.0, "activo": True},
        # --- Transporte pesado y motos adicionales ---
        {"placa": "4029CDX", "propietario": "Transportes Andinos S.R.L.", "categoria": "camion", "ejes": 3, "saldo": 450.0, "activo": True},
        {"placa": "5108TRK", "propietario": "Logística Altiplano S.A.", "categoria": "camion", "ejes": 4, "saldo": 620.0, "activo": True},
        {"placa": "4410BUS", "propietario": "Trans Copacabana S.A. - Bus 22", "categoria": "bus", "ejes": 3, "saldo": 540.0, "activo": True},
        {"placa": "1540MTA", "propietario": "Diego Armando Torrico", "categoria": "moto", "ejes": 2, "saldo": 45.0, "activo": True},
    ]

    for v_data in catalogo_vehiculos:
        existente = db.query(Vehiculo).filter(Vehiculo.placa == v_data["placa"]).first()
        if not existente:
            db.add(Vehiculo(**v_data))

    # Asegurar que las 3 placas NO registradas del video (6672LXL, 4011XKH, 2030ZUD)
    # y las 2 NO registradas de las fotos (92W7010, 6968DP) NO estén en vehiculos
    for placa_no_reg in ("6672LXL", "4011XKH", "2030ZUD", "92W7010", "6968DP"):
        v_borrar = db.query(Vehiculo).filter(Vehiculo.placa == placa_no_reg).first()
        if v_borrar:
            db.delete(v_borrar)
    db.commit()

    # --------------------------------------------------------------------------
    # 5. HISTORIAL DE PASOS: 20 FOTOS REALES DE 'placas pasos' + 3 DEL VIDEO
    # --------------------------------------------------------------------------
    admin_user = db.query(Usuario).first()
    uid = admin_user.id if admin_user else 1
    ahora = datetime.datetime.now(datetime.timezone.utc)

    pasos_semilla = [
        # --- Ejemplos del Video de Prueba ---
        {
            "placa_leida": "2673-TYH",
            "placa_normalizada": "2673TYH",
            "confianza_ocr": 0.96,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 2,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/api/v1/evidencias/demo_2673TYH.svg",
            "estado": "aprobado",
            "minutos_atras": 4,
            "alerta": None,
        },
        {
            "placa_leida": "6672-LXL",
            "placa_normalizada": "6672LXL",
            "confianza_ocr": 0.94,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 2,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/api/v1/evidencias/demo_6672LXL.svg",
            "estado": "no_registrada",
            "minutos_atras": 6,
            "alerta": "placa_no_registrada",
        },
        {
            "placa_leida": "5324-DZG",
            "placa_normalizada": "5324DZG",
            "confianza_ocr": 0.93,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/api/v1/evidencias/demo_5324DZG.svg",
            "estado": "sin_saldo",
            "minutos_atras": 9,
            "alerta": "sin_saldo",
        },
        # --- 20 Fotografías Reales de la carpeta 'placas pasos' ---
        {
            "placa_leida": "RJB-F8",
            "placa_normalizada": "RJBF8",
            "confianza_ocr": 0.97,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/USA_2229840.jpg",
            "estado": "aprobado",
            "minutos_atras": 12,
            "alerta": None,
        },
        {
            "placa_leida": "8217NT",
            "placa_normalizada": "8217NT",
            "confianza_ocr": 0.94,
            "categoria_detectada": "minibus",
            "ejes_detectados": 2,
            "pasajeros": 2,
            "monto": 10.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/USA_2071059.jpg",
            "estado": "aprobado",
            "minutos_atras": 15,
            "alerta": None,
        },
        {
            "placa_leida": "6968DP",
            "placa_normalizada": "6968DP",
            "confianza_ocr": 0.92,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/USA_1250580.jpg",
            "estado": "no_registrada",
            "minutos_atras": 18,
            "alerta": "placa_no_registrada",
        },
        {
            "placa_leida": "VSA 530",
            "placa_normalizada": "VSA530",
            "confianza_ocr": 0.95,
            "categoria_detectada": "minibus",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 10.0,
            "caseta_id": 3,
            "imagen_url": "/static/pasos_img/USA_1250561.jpg",
            "estado": "aprobado",
            "minutos_atras": 22,
            "alerta": None,
        },
        {
            "placa_leida": "23KPAP",
            "placa_normalizada": "23KPAP",
            "confianza_ocr": 0.98,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/USA_1122742.jpg",
            "estado": "aprobado",
            "minutos_atras": 25,
            "alerta": None,
        },
        {
            "placa_leida": "BT 92118",
            "placa_normalizada": "BT92118",
            "confianza_ocr": 0.97,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Norway_972429.jpg",
            "estado": "aprobado",
            "minutos_atras": 29,
            "alerta": None,
        },
        {
            "placa_leida": "ZE 61026",
            "placa_normalizada": "ZE61026",
            "confianza_ocr": 0.95,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Norway_1342295.jpg",
            "estado": "sin_saldo",
            "minutos_atras": 33,
            "alerta": "sin_saldo",
        },
        {
            "placa_leida": "AA 59357",
            "placa_normalizada": "AA59357",
            "confianza_ocr": 0.96,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Norway_1007405.jpg",
            "estado": "aprobado",
            "minutos_atras": 37,
            "alerta": None,
        },
        {
            "placa_leida": "AS 32347",
            "placa_normalizada": "AS32347",
            "confianza_ocr": 0.96,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 2,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Norway_1007353.jpg",
            "estado": "aprobado",
            "minutos_atras": 41,
            "alerta": None,
        },
        {
            "placa_leida": "AA 50689",
            "placa_normalizada": "AA50689",
            "confianza_ocr": 0.98,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 2,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Norway_1007306.jpg",
            "estado": "aprobado",
            "minutos_atras": 45,
            "alerta": None,
        },
        {
            "placa_leida": "ZV 45288",
            "placa_normalizada": "ZV45288",
            "confianza_ocr": 0.94,
            "categoria_detectada": "camion",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 15.0,
            "caseta_id": 3,
            "imagen_url": "/static/pasos_img/Ireland_1769921.jpg",
            "estado": "aprobado",
            "minutos_atras": 50,
            "alerta": None,
        },
        {
            "placa_leida": "92-W-7010",
            "placa_normalizada": "92W7010",
            "confianza_ocr": 0.97,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Ireland_1059740.jpg",
            "estado": "no_registrada",
            "minutos_atras": 54,
            "alerta": "placa_no_registrada",
        },
        {
            "placa_leida": "241-D-24258",
            "placa_normalizada": "241D24258",
            "confianza_ocr": 0.98,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Ireland_1059700.jpg",
            "estado": "aprobado",
            "minutos_atras": 58,
            "alerta": None,
        },
        {
            "placa_leida": "232-D-17482",
            "placa_normalizada": "232D17482",
            "confianza_ocr": 0.97,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Ireland_1029652.jpg",
            "estado": "aprobado",
            "minutos_atras": 63,
            "alerta": None,
        },
        {
            "placa_leida": "07-D-40426",
            "placa_normalizada": "07D40426",
            "confianza_ocr": 0.98,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Ireland_1005977.jpg",
            "estado": "aprobado",
            "minutos_atras": 68,
            "alerta": None,
        },
        {
            "placa_leida": "2979",
            "placa_normalizada": "2979",
            "confianza_ocr": 0.96,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Bahrain_831502.jpg",
            "estado": "aprobado",
            "minutos_atras": 72,
            "alerta": None,
        },
        {
            "placa_leida": "582034",
            "placa_normalizada": "582034",
            "confianza_ocr": 0.95,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Bahrain_1004217.jpg",
            "estado": "sin_saldo",
            "minutos_atras": 76,
            "alerta": "sin_saldo",
        },
        {
            "placa_leida": "32789",
            "placa_normalizada": "32789",
            "confianza_ocr": 0.94,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Bahrain_1004054.jpg",
            "estado": "aprobado",
            "minutos_atras": 81,
            "alerta": None,
        },
        {
            "placa_leida": "190627",
            "placa_normalizada": "190627",
            "confianza_ocr": 0.97,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 1,
            "imagen_url": "/static/pasos_img/Bahrain_1004012.jpg",
            "estado": "aprobado",
            "minutos_atras": 86,
            "alerta": None,
        },
        {
            "placa_leida": "653037",
            "placa_normalizada": "653037",
            "confianza_ocr": 0.96,
            "categoria_detectada": "auto",
            "ejes_detectados": 2,
            "pasajeros": 1,
            "monto": 7.0,
            "caseta_id": 2,
            "imagen_url": "/static/pasos_img/Bahrain_1003919.jpg",
            "estado": "aprobado",
            "minutos_atras": 92,
            "alerta": None,
        },
    ]

    for p_info in pasos_semilla:
        ya_existe = (
            db.query(Paso)
            .filter(Paso.placa_normalizada == p_info["placa_normalizada"])
            .first()
        )
        if not ya_existe:
            instante = ahora - datetime.timedelta(minutes=p_info["minutos_atras"])
            nuevo_p = Paso(
                placa_leida=p_info["placa_leida"],
                placa_normalizada=p_info["placa_normalizada"],
                confianza_ocr=p_info["confianza_ocr"],
                categoria_detectada=p_info["categoria_detectada"],
                ejes_detectados=p_info["ejes_detectados"],
                pasajeros=p_info["pasajeros"],
                monto=p_info["monto"],
                caseta_id=p_info["caseta_id"],
                usuario_id=uid,
                imagen_url=p_info["imagen_url"],
                estado=p_info["estado"],
                created_at=instante,
            )
            db.add(nuevo_p)
            db.commit()
            db.refresh(nuevo_p)

            if p_info["alerta"]:
                db.add(
                    Alerta(
                        paso_id=nuevo_p.id,
                        tipo=p_info["alerta"],
                        atendida=False,
                        created_at=instante,
                    )
                )
                db.commit()
