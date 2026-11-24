import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'home_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  bool _cargando = false;
  String? _mensajeError;

  Future<void> _autenticarCuentaSeleccionada(String email, String nombre) async {
    setState(() {
      _cargando = true;
      _mensajeError = null;
    });

    try {
      final res = await ApiService.loginConCuentaGoogle(
        email: email.trim().toLowerCase(),
        nombre: nombre.trim(),
      );
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
      if (mounted) {
        setState(() {
          _mensajeError = 'Error al conectar con el servidor en la nube: $e';
        });
      }
    } finally {
      if (mounted) setState(() => _cargando = false);
    }
  }

  void _mostrarSelectorCuentasGoogle() {
    final TextEditingController otroCorreoCtrl = TextEditingController();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: const Color(0xFF1E293B),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (ctx) {
        return Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 20,
            bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    width: 36,
                    height: 36,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(18),
                    ),
                    alignment: Alignment.center,
                    child: const Text(
                      'G',
                      style: TextStyle(
                        fontSize: 22,
                        fontWeight: FontWeight.w900,
                        color: Color(0xFF2563EB),
                      ),
                    ),
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Iniciar sesión con Google',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                        Text(
                          'Elige una cuenta para continuar a TelePeaje IA',
                          style: TextStyle(fontSize: 12, color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const Divider(color: Colors.white12, height: 24),
              _itemCuentaGoogle(
                ctx: ctx,
                email: 'jhairpinto8@gmail.com',
                nombre: 'Jhair Pinto',
                subtitulo: 'Administrador',
                colorAvatar: Colors.blueAccent,
              ),
              _itemCuentaGoogle(
                ctx: ctx,
                email: 'doc.alvaro.pinto.ma@unifranz.edu.bo',
                nombre: 'Ing. Alvaro Pinto Mamani',
                subtitulo: 'Administrador Docente',
                colorAvatar: Colors.teal,
              ),
              _itemCuentaGoogle(
                ctx: ctx,
                email: 'operador.peaje.unifranz@gmail.com',
                nombre: 'Operador Caseta 1',
                subtitulo: 'Operador de Peaje',
                colorAvatar: Colors.indigo,
              ),
              _itemCuentaGoogle(
                ctx: ctx,
                email: 'usuario.no.autorizado@gmail.com',
                nombre: 'Cuenta Externa No Autorizada',
                subtitulo: 'Prueba de rechazo (Lista Blanca)',
                colorAvatar: Colors.redAccent,
              ),
              const SizedBox(height: 10),
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: otroCorreoCtrl,
                      keyboardType: TextInputType.emailAddress,
                      style: const TextStyle(color: Colors.white, fontSize: 13),
                      decoration: InputDecoration(
                        hintText: 'Usar otra cuenta (@gmail.com)...',
                        hintStyle: const TextStyle(color: Colors.white54),
                        filled: true,
                        fillColor: const Color(0xFF0F172A),
                        contentPadding: const EdgeInsets.symmetric(
                          horizontal: 14,
                          vertical: 10,
                        ),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    onPressed: () {
                      final correo = otroCorreoCtrl.text.trim();
                      if (correo.isEmpty) return;
                      Navigator.pop(ctx);
                      _autenticarCuentaSeleccionada(correo, correo.split('@').first);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2563EB),
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('Entrar'),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _itemCuentaGoogle({
    required BuildContext ctx,
    required String email,
    required String nombre,
    required String subtitulo,
    required Color colorAvatar,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
      leading: CircleAvatar(
        backgroundColor: colorAvatar,
        child: Text(
          nombre.substring(0, 1).toUpperCase(),
          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
      ),
      title: Text(
        nombre,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 13.5,
          fontWeight: FontWeight.w600,
        ),
      ),
      subtitle: Text(
        '$email · $subtitulo',
        style: const TextStyle(color: Colors.white60, fontSize: 11.5),
      ),
      onTap: () {
        Navigator.pop(ctx);
        _autenticarCuentaSeleccionada(email, nombre);
      },
    );
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
              padding: const EdgeInsets.all(26.0),
              decoration: BoxDecoration(
                color: const Color(0xFF1E293B),
                borderRadius: BorderRadius.circular(22),
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
                    'IAM-811 Machine Learning y Aprendizaje Profundo\nAcceso Exclusivo con Google OAuth 2.0 (Lista Blanca)',
                    textAlign: TextAlign.center,
                    style: TextStyle(fontSize: 12, color: Colors.white70),
                  ),
                  const SizedBox(height: 24),
                  if (_mensajeError != null)
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: 18),
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
                    height: 50,
                    child: ElevatedButton.icon(
                      onPressed: _cargando ? null : _mostrarSelectorCuentasGoogle,
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
                            ? 'Verificando Lista Blanca...'
                            : 'Iniciar Sesión con Google',
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 14,
                        ),
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
