import 'package:flutter/material.dart';
import 'package:google_sign_in/google_sign_in.dart';
import '../config.dart';
import '../services/api_service.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final TextEditingController _urlController =
      TextEditingController(text: AppConfig.baseUrl);
  final GoogleSignIn _googleSignIn = GoogleSignIn(scopes: ['email', 'profile']);
  bool _cargando = false;
  String? _mensajeError;

  Future<void> _iniciarConGoogle() async {
    setState(() {
      _cargando = true;
      _mensajeError = null;
      AppConfig.baseUrl = _urlController.text.trim().replaceAll(RegExp(r'/$'), '');
    });

    try {
      await _googleSignIn.signOut();
      final cuenta = await _googleSignIn.signIn();
      if (cuenta == null) {
        setState(() => _cargando = false);
        return;
      }

      final auth = await cuenta.authentication;
      final token = auth.idToken ?? auth.accessToken ?? '';
      if (token.isEmpty) {
        setState(() {
          _cargando = false;
          _mensajeError =
              'No se obtuvo el token OAuth de Google. Verifique la huella SHA-1 en Google Cloud Console.';
        });
        return;
      }

      final res = await ApiService.loginConGoogleToken(token);
      if (!mounted) return;

      if (res['ok'] == true) {
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      } else {
        setState(() {
          _mensajeError = res['error']?.toString();
        });
      }
    } catch (e) {
      setState(() {
        _mensajeError = 'Error al autenticar con Google: $e';
      });
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B1120),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24.0),
            child: Container(
              padding: const EdgeInsets.all(24.0),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white12),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    padding: const EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.blueAccent.withOpacity(0.18),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: const Icon(
                      Icons.toll_rounded,
                      size: 48,
                      color: Colors.lightBlueAccent,
                    ),
                  ),
                  const SizedBox(height: 16),
                  const Text(
                    'TelePeaje IA · App Móvil',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.bold,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'IAM-811 Machine Learning y Aprendizaje Profundo\nAcceso Exclusivo con Google Sign-In (Lista Blanca)',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.white70),
                  ),
                  const SizedBox(height: 20),
                  TextField(
                    controller: _urlController,
                    style: const TextStyle(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      labelText: 'Subdominio HTTPS del Sistema',
                      labelStyle: const TextStyle(color: Colors.white70),
                      prefixIcon: const Icon(Icons.cloud_outlined, color: Colors.lightBlueAccent),
                      filled: true,
                      fillColor: const Color(0xFF0F172A),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                  ),
                  const SizedBox(height: 18),
                  if (_mensajeError != null)
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: 16),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: Colors.red.shade900.withOpacity(0.45),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.redAccent),
                      ),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Icon(Icons.block, color: Colors.redAccent, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              _mensajeError!,
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 12.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  SizedBox(
                    width: double.infinity,
                    height: 48,
                    child: ElevatedButton.icon(
                      onPressed: _cargando ? null : _iniciarConGoogle,
                      icon: _cargando
                          ? const SizedBox(
                              width: 18,
                              height: 18,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: Colors.white,
                              ),
                            )
                          : const Icon(Icons.login_rounded),
                      label: Text(
                        _cargando
                            ? 'Verificando con Google OAuth...'
                            : 'Iniciar Sesión con Google',
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF2563EB),
                        foregroundColor: Colors.white,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
