# Aplicación Móvil Flutter - Sistema Inteligente de Control de Peaje (`/movil`)

Cumple todos los requisitos de la **Sección 4.1**:
1. **Inicio de sesión exclusivo con Google (`google_sign_in`)**: Valida el token con `POST /api/v1/auth/google` y muestra el rechazo si la cuenta no está en la lista blanca de la base de datos.
2. **Modo Caseta**: Captura video de la cámara y envía frames automáticamente a una frecuencia configurable de **2 a 5 fps** (o frame manual) hacia `POST /api/v1/pasos/frame`, mostrando en vivo la **placa leída**, la **categoría**, los **ejes**, la **tarifa (Bs.)** y el **estado**.
3. **Modo Consulta**: Permite tomar una foto de una placa (o subir imagen) hacia `POST /api/v1/placas/consultar-imagen` o escribir la placa en texto hacia `POST /api/v1/agente/chat` para consultar al **Agente Conversacional (Qwen)**.

## Pasos para compilar el APK de entrega (Sección 7.2)

1. Configurar en `lib/config.dart` la URL del subdominio HTTPS desplegado (por ejemplo `https://peaje.tudominio.com`).
2. Registrar la huella SHA-1 de compilación en **Google Cloud Console > Credenciales > ID de cliente OAuth 2.0 para Android** con el package name `bo.edu.unifranz.iam811.peaje_ia_movil`.
3. Ejecutar desde la carpeta `/movil`:
   ```bash
   flutter pub get
   flutter build apk --release
   ```
4. El archivo APK listo para subir a la carpeta en la nube se generará en:
   `movil/build/app/outputs/flutter-apk/app-release.apk`
