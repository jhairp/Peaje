/// Configuración del subdominio HTTPS de producción del sistema de peaje.
/// Prohibido usar localhost o IPs privadas en la entrega (Sección 5).
class AppConfig {
  /// URL por defecto del subdominio en producción (también editable desde la pantalla de Login)
  static String baseUrl = "https://peaje-62tb.onrender.com";

  /// Frecuencia de captura por defecto en Modo Caseta (entre 2 y 5 fps según Sección 4.1)
  static double defaultFps = 2.0;
}
