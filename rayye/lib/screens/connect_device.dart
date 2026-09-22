import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/plant_zone.dart';
import '../services/irrigation/irrigation_service.dart';
import '../theme/app_theme.dart';

class ConnectDeviceScreen extends StatefulWidget {
  const ConnectDeviceScreen({Key? key}) : super(key: key);

  @override
  State<ConnectDeviceScreen> createState() => _ConnectDeviceScreenState();
}

class _ConnectDeviceScreenState extends State<ConnectDeviceScreen> {
  final _formKey = GlobalKey<FormState>();
  final _wifiController = TextEditingController();
  final _macController = TextEditingController();
  ConnectionMethod _connectionMethod = ConnectionMethod.wifi;
  DeviceType _deviceType = DeviceType.esp32;

  @override
  void dispose() {
    _wifiController.dispose();
    _macController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<IrrigationService>();
    return Scaffold(
      backgroundColor: AppTheme.sand,
      appBar: AppBar(
        title: const Text('Connect Device'),
        backgroundColor: AppTheme.moss,
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            const Icon(Icons.sensors, size: 76, color: AppTheme.leaf),
            const SizedBox(height: 12),
            const Text('Connect your irrigation controller',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: AppTheme.soil)),
            const SizedBox(height: 24),
            const Text('Connection method',
                style: TextStyle(
                    fontWeight: FontWeight.w600, color: AppTheme.soil)),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: ConnectionMethod.values.map((method) {
                return ChoiceChip(
                  avatar: Icon(method.icon, size: 18),
                  label: Text(method.label),
                  selected: _connectionMethod == method,
                  onSelected: (_) => setState(() => _connectionMethod = method),
                );
              }).toList(),
            ),
            const SizedBox(height: 20),
            DropdownButtonFormField<DeviceType>(
              value: _deviceType,
              decoration: const InputDecoration(
                labelText: 'Device type',
                prefixIcon: Icon(Icons.memory),
                border: OutlineInputBorder(),
              ),
              items: DeviceType.values
                  .map((type) => DropdownMenuItem(
                        value: type,
                        child: Text(type.label),
                      ))
                  .toList(),
              onChanged: (type) {
                if (type != null) setState(() => _deviceType = type);
              },
            ),
            const SizedBox(height: 16),
            if (_connectionMethod.usesWifi)
              TextFormField(
                controller: _wifiController,
                keyboardType: TextInputType.url,
                decoration: const InputDecoration(
                  labelText: 'Wi-Fi address or hostname',
                  hintText: '192.168.1.50',
                  prefixIcon: Icon(Icons.wifi),
                  border: OutlineInputBorder(),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Enter the device Wi-Fi address'
                    : null,
              ),
            if (_connectionMethod.usesWifi && _connectionMethod.usesMac)
              const SizedBox(height: 16),
            if (_connectionMethod.usesMac)
              TextFormField(
                controller: _macController,
                keyboardType: TextInputType.text,
                decoration: const InputDecoration(
                  labelText: 'MAC address',
                  hintText: 'AA:BB:CC:DD:EE:FF',
                  prefixIcon: Icon(Icons.device_hub),
                  border: OutlineInputBorder(),
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Enter the device MAC address'
                    : null,
              ),
            const SizedBox(height: 24),
            SizedBox(
              height: 48,
              child: ElevatedButton.icon(
                onPressed: () => _connect(svc),
                icon: const Icon(Icons.link),
                label: const Text('Connect device'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _connect(IrrigationService svc) {
    if (!_formKey.currentState!.validate()) return;

    final random = Random();
    final zoneCount = random.nextInt(3) + 1;
    final zones = List.generate(zoneCount, (index) {
      return PlantZone(
        name: 'Zone ${index + 1}',
        icon: '🌱',
        threshold: random.nextDouble() * 70 + 10,
        id: '',
        plantType: '',
        soilType: '',
        sensorType: '',
        moisture: random.nextDouble() * 70 + 10,
      );
    });
    svc.setZones(zones);
    Navigator.pop(context);
  }
}

enum ConnectionMethod { wifi, mac, wifiAndMac }

extension on ConnectionMethod {
  String get label {
    switch (this) {
      case ConnectionMethod.wifi:
        return 'Wi-Fi';
      case ConnectionMethod.mac:
        return 'MAC address';
      case ConnectionMethod.wifiAndMac:
        return 'Wi-Fi + MAC';
    }
  }

  IconData get icon {
    switch (this) {
      case ConnectionMethod.wifi:
        return Icons.wifi;
      case ConnectionMethod.mac:
        return Icons.device_hub;
      case ConnectionMethod.wifiAndMac:
        return Icons.link;
    }
  }

  bool get usesWifi => this != ConnectionMethod.mac;
  bool get usesMac => this != ConnectionMethod.wifi;
}

enum DeviceType { arduino, esp32, raspberryPi }

extension on DeviceType {
  String get label {
    switch (this) {
      case DeviceType.arduino:
        return 'Arduino';
      case DeviceType.esp32:
        return 'ESP32';
      case DeviceType.raspberryPi:
        return 'Raspberry Pi';
    }
  }
}
