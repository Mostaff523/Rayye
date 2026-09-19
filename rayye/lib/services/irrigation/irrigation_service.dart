import 'dart:async';
import 'dart:math';
import 'package:flutter/foundation.dart';
import '../../models/plant_zone.dart';

class IrrigationService extends ChangeNotifier {
  final Random _rng = Random();
  Timer? _ticker;

  bool _autoMode = true;
  bool get autoMode => _autoMode;

  late SystemStatus _systemStatus;
  SystemStatus get systemStatus => _systemStatus;

  late List<PlantZone> _zones;
  List<PlantZone> get zones => List.unmodifiable(_zones);

  final List<Map<String, dynamic>> _notifications = [];
  List<Map<String, dynamic>> get notifications =>
      List.unmodifiable(_notifications);

  IrrigationService() {
    _init();
  }

  void _init() {
    _systemStatus = const SystemStatus(
      connected: false,
      waterTankLevel: 0,
      totalIrrigationsToday: 0,
      waterUsedTodayLiters: 0,
    );
    _zones = [];
    _ticker = Timer.periodic(const Duration(seconds: 4), (_) => _tick());
  }

  void _tick() {
    bool changed = false;
    for (int i = 0; i < _zones.length; i++) {
      final z = _zones[i];
      double newMoisture = z.moisture;

      if (z.pumpActive) {
        newMoisture += _rng.nextDouble() * 2.5 + 0.5;
        if (newMoisture >= z.threshold + 20) {
          _zones[i] = z.copyWith(
            moisture: newMoisture.clamp(0, 100),
            pumpActive: false,
            lastIrrigated: DateTime.now(),
            moistureHistory: [
              ...z.moistureHistory.skip(1),
              newMoisture.clamp(0, 100)
            ],
          );
          _addNotification('${z.name} watered',
              'Pump stopped. Moisture at ${newMoisture.clamp(0, 100).toStringAsFixed(0)}%.',
              isInfo: true);
          changed = true;
          continue;
        }
      } else {
        newMoisture -= _rng.nextDouble() * 0.8 + 0.1;
      }
      newMoisture = newMoisture.clamp(0, 100);

      bool newPump = z.pumpActive;
      if (_autoMode && !z.pumpActive && newMoisture < z.threshold) {
        newPump = true;
        _addNotification('Auto-watering started',
            '${z.name} moisture dropped below ${z.threshold.toInt()}%.',
            isWarning: true);
      }
      if (!z.pumpActive && newMoisture < 20 && z.moisture >= 20) {
        _addNotification('⚠️ Low moisture', '${z.name} is critically dry!',
            isWarning: true);
      }
      _zones[i] = z.copyWith(
        moisture: newMoisture,
        pumpActive: newPump,
        moistureHistory: [...z.moistureHistory.skip(1), newMoisture],
        lastIrrigated:
            (newPump && !z.pumpActive) ? DateTime.now() : z.lastIrrigated,
      );
      changed = true;
    }
    if (changed) notifyListeners();
  }

  void togglePump(String zoneId) {
    final idx = _zones.indexWhere((z) => z.id == zoneId);
    if (idx == -1) return;
    final z = _zones[idx];
    final active = !z.pumpActive;
    _zones[idx] = z.copyWith(
      pumpActive: active,
      lastIrrigated: active ? DateTime.now() : z.lastIrrigated,
    );
    _addNotification(active ? 'Pump ON' : 'Pump OFF',
        '${z.name} pump manually ${active ? "activated" : "stopped"}.',
        isInfo: true);
    notifyListeners();
  }

  void setThreshold(String zoneId, double value) {
    final idx = _zones.indexWhere((z) => z.id == zoneId);
    if (idx == -1) return;
    _zones[idx] = _zones[idx].copyWith(threshold: value);
    notifyListeners();
  }

  void setAutoMode(bool value) {
    _autoMode = value;
    _addNotification(value ? 'Auto Mode ON' : 'Auto Mode OFF',
        value ? 'System will water automatically.' : 'Manual control only.',
        isInfo: true);
    notifyListeners();
  }

  void addZone(PlantZone zone) {
    _zones = [..._zones, zone];
    _addNotification('Zone added', '${zone.name} is now being monitored.',
        isInfo: true);
    notifyListeners();
  }

  void removeZone(String zoneId) {
    _zones = _zones.where((z) => z.id != zoneId).toList();
    notifyListeners();
  }

  void clearNotifications() {
    _notifications.clear();
    notifyListeners();
  }

  void _addNotification(String title, String body,
      {bool isWarning = false, bool isInfo = false}) {
    _notifications.insert(0, {
      'title': title,
      'body': body,
      'time': DateTime.now(),
      'isWarning': isWarning,
      'isInfo': isInfo,
    });
    if (_notifications.length > 30) _notifications.removeLast();
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }
}
