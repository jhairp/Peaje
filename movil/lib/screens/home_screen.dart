import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'caseta_screen.dart';
import 'consulta_screen.dart';
import 'login_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  int _indiceActual = 0;

  final List<Widget> _pantallas = const [
    CasetaScreen(),
    ConsultaScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final usuario = ApiService.usuarioActual ?? {};
    final nombre = usuario['nombre'] ?? 'Operador';
    final rol = (usuario['rol'] ?? 'operador').toString().toUpperCase();

    return Scaffold(
      backgroundColor: const Color(0xFF0B1120),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Control Inteligente de Peaje',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
            ),
            Text(
              '$nombre · Rol: $rol',
              style: const TextStyle(fontSize: 11, color: Colors.greenAccent),
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout_rounded, color: Colors.white70),
            onPressed: () {
              ApiService.tokenSesion = null;
              ApiService.usuarioActual = null;
              Navigator.of(context).pushReplacement(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
              );
            },
          ),
        ],
      ),
      body: _pantallas[_indiceActual],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _indiceActual,
        onTap: (i) => setState(() => _indiceActual = i),
        backgroundColor: const Color(0xFF1E293B),
        selectedItemColor: Colors.lightBlueAccent,
        unselectedItemColor: Colors.white54,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.videocam_rounded),
            label: 'Modo Caseta (2-5 fps)',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.smart_toy_rounded),
            label: 'Modo Consulta (Qwen)',
          ),
        ],
      ),
    );
  }
}
