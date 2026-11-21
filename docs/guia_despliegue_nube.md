# Guía Paso a Paso de Despliegue 100% en la Nube (Sin Recursos Locales y con Subdominio Gratis)

Para cumplir con la **Sección 4.2** (*"Publicada en un subdominio accesible por HTTPS"*) y la **Sección 5** (*"Aplicación web, API, base de datos, tiempo real y agente: VPS, hosting compartido o servicios en la nube"*), **primero** obtendremos tu subdominio HTTPS gratuito en la nube y **luego** lo registraremos en Google Cloud Console.

---

## Paso 0: Cómo conseguir tu Subdominio HTTPS Gratis en la Nube (Elige 1 de estas 3 opciones)

No necesitas comprar un dominio. Puedes obtener un subdominio HTTPS 100% gratuito alojando la carpeta `/web` en cualquiera de estos servicios en la nube:

### Opción A (Recomendada - 100% Gratis): Render.com (`https://peaje-ia-iam811.onrender.com`)
Ya dejé creado el archivo `render.yaml` en la raíz de tu proyecto para que se configure solo:
1. Sube este proyecto a tu cuenta de **GitHub**.
2. Entra a [https://render.com](https://render.com/) e inicia sesión con tu cuenta de GitHub.
3. Haz clic en **New +** $\rightarrow$ **Web Service** y selecciona tu repositorio de GitHub.
4. Render detectará la carpeta `web` (o configura:
   - **Root Directory:** `web`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free`).
5. Al darle a **Deploy**, Render te asignará inmediatamente tu subdominio público con HTTPS:
   👉 **`https://peaje-ia-iam811.onrender.com`** (o el nombre que elijas).

### Opción B (100% Gratis y sin límite de reposo): Hugging Face Spaces Docker (`https://tu-usuario-peaje.hf.space`)
1. Crea una cuenta gratuita en [https://huggingface.co](https://huggingface.co/).
2. Haz clic en **New Space**:
   - **Space name:** `peaje-iam811`
   - **Select the Space SDK:** **Docker** (Blank)
   - **Hardware:** `CPU basic (Free - 16 GB RAM)`
3. Sube los archivos de la carpeta `/web` (ya incluye un `Dockerfile` configurado en el puerto `7860` o `8080`).
4. Tu subdominio HTTPS público será:
   👉 **`https://tuusuario-peaje-iam811.hf.space`**

### Opción C (Si tienes un VPS gratuito como Oracle Cloud / AWS / Azure Estudiante y quieres un dominio gratis)
1. Entra a **[DuckDNS.org](https://www.duckdns.org/)** e inicia sesión con tu cuenta de Google (`jhairpinto8@gmail.com`).
2. Escribe en *sub domain*: `peaje-iam811` y apunta a la IP pública de tu VPS.
3. Tendrás el subdominio gratuito **`https://peaje-iam811.duckdns.org`** (le activas HTTPS gratis con `certbot --nginx -d peaje-iam811.duckdns.org`).
*(Nota: También con tu correo institucional de Unifranz puedes activar el **GitHub Student Developer Pack** que regala 1 dominio `.tech` o `.live` por 1 año en Namecheap y \$200 en DigitalOcean).*

---

## Paso 1: Configurar Google OAuth 2.0 en Google Cloud Console (Usando tu Subdominio Gratis)

Una vez que tengas la URL de tu subdominio del Paso 0 (por ejemplo, `https://peaje-ia-iam811.onrender.com`):

1. Entra a [Google Cloud Console](https://console.cloud.google.com/) y crea un proyecto llamado `TelePeaje-IAM811`.
2. Ve a **APIs y servicios > Pantalla de consentimiento de OAuth**:
   - Tipo de usuario: **Externo**.
   - Nombre de la aplicación: `TelePeaje IA - IAM-811`.
   - En **Usuarios de prueba** (o pulsa **"Publicar aplicación"** para que no tenga límite de usuarios de prueba), asegúrate de incluir:
     - `doc.alvaro.pinto.ma@unifranz.edu.bo`
     - `jhairpinto8@gmail.com`
3. Ve a **Credenciales > + Crear credenciales > ID de cliente de OAuth**:
   - **Credencial 1 (Tipo: Aplicación Web):**
     - **Nombre:** `Cliente Web Peaje`
     - **Orígenes de JavaScript autorizados:** pega exactamente tu subdominio HTTPS del Paso 0 (sin barra `/` al final), por ejemplo:
       `https://peaje-ia-iam811.onrender.com`
     - **URI de redireccionamiento autorizados:**
       `https://peaje-ia-iam811.onrender.com`
     - Haz clic en **Crear** y copia el **`GOOGLE_CLIENT_ID`** y **`GOOGLE_CLIENT_SECRET`** en las variables de entorno (Environment Variables) de tu servidor web.
   - **Credencial 2 (Tipo: Android - para la App Móvil Flutter):**
     - **Nombre del paquete:** `bo.edu.unifranz.iam811.peaje_ia_movil`
     - **Huella digital del certificado SHA-1:** la obtienes ejecutando en la carpeta `movil/android`:
       `./gradlew signingReport` (o `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android -keypass android`).

---

## Paso 2: Desplegar el Endpoint Único de Inferencia (RunPod o Google Colab)

### Opción A: RunPod en Vivo (+5 puntos adicionales - Sección 10)
1. En [RunPod](https://www.runpod.io/), lanza un GPU Pod con plantilla **PyTorch 2.4** y expón el puerto HTTP **8000**.
2. Sube el contenido de la carpeta `/inferencia` (incluyendo tus pesos `.pt` en `weights/` si ya los entrenaste, o úsalo directamente con el modo *fallback* preconfigurado).
3. Abre `servidor_inferencia_runpod.ipynb` y ejecuta todas las celdas.
4. Copia la URL pública generada: `https://<POD_ID>-8000.proxy.runpod.net` y descarga el archivo `diagnostico_inferencia.txt` (para tu carpeta en Drive).

### Opción B: Google Colab (100% Gratis)
1. Sube `/inferencia/servidor_inferencia_colab.ipynb`, `/inferencia/app_inferencia.py` y `/inferencia/diagnosticar_entorno.py` a [Google Colab](https://colab.research.google.com/) activando **GPU T4**.
2. Ejecuta todas las celdas. La celda 4 imprimirá tu URL pública HTTPS de Cloudflare:
   `https://xxxx-xxxx.trycloudflare.com`
3. Entra a tu aplicación web (`https://peaje-ia-iam811.onrender.com`), ve a la pestaña **Estado GPU**, pega esa URL en **`INFERENCE_URL`** y dale a **Guardar INFERENCE_URL**.

---

## Paso 3: Configurar las Variables de Entorno en tu Servicio Web (Render / Railway / VPS)

En el panel de variables de entorno de tu servicio web (o archivo `/web/.env`), configura:

```env
DATABASE_URL=sqlite:///./peaje.db
GOOGLE_CLIENT_ID=tu-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=tu-client-secret
JWT_SECRET_KEY=clave_secreta_produccion_peaje_2026
ADMIN_EMAILS=doc.alvaro.pinto.ma@unifranz.edu.bo,jhairpinto8@gmail.com
INFERENCE_URL=https://xxxx-xxxx.trycloudflare.com
INFERENCE_API_TOKEN=token_secreto_inferencia_peaje_2026
QWEN_API_KEY=sk-tu-api-key-de-qwen
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

---

## Paso 4: Compilar el APK de la Aplicación Móvil (`/movil`)

1. Abre `movil/lib/config.dart` y pon tu subdominio HTTPS en `AppConfig.baseUrl`:
   ```dart
   static String baseUrl = "https://peaje-ia-iam811.onrender.com";
   ```
   *(También puedes escribir o cambiar esa URL directamente en la caja de texto de la pantalla de inicio de sesión de la App Móvil sin recompilar el APK).*
2. Ejecuta:
   ```bash
   cd movil
   flutter pub get
   flutter build apk --release
   ```
3. Sube el APK generado (`movil/build/app/outputs/flutter-apk/app-release.apk`) a tu carpeta compartida en Google Drive.
