import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:window_manager/window_manager.dart';

const String _apiBase = 'http://127.0.0.1:8412';

// ── Window sizes ───────────────────────────────────────────────
const double _orbSize = 96;
const double _panelWidth = 360;
const double _panelHeight = 460;
const double _settingsHeight = 520;

// ── Theme ──────────────────────────────────────────────────────
const Color _bg = Color(0xCC0F1119); // ~80% opacity deep navy
const Color _accent = Color(0xFF7C8CFF); // periwinkle
const Color _clrListen = Color(0xFF00E5A8);
const Color _clrSpeak = Color(0xFFB388FF);
const Color _clrAwait = Color(0xFFFFB74D);
const Color _clrOffline = Color(0xFF555866);
const Color _textPrimary = Color(0xFFE8EAF2);
const Color _textSecondary = Color(0xFF9AA0B4);

// ── Tiny HTTP helpers ──────────────────────────────────────────
Future<Map<String, dynamic>> _apiGet(String path) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
  try {
    final req = await client.getUrl(Uri.parse('$_apiBase$path'));
    final res = await req.close().timeout(const Duration(seconds: 2));
    final body = await res.transform(utf8.decoder).join();
    return json.decode(body) as Map<String, dynamic>;
  } catch (e) {
    return {'ok': false, 'error': e.toString()};
  } finally {
    client.close(force: true);
  }
}

Future<Map<String, dynamic>> _apiPost(String path, Map<String, dynamic> body) async {
  final client = HttpClient()..connectionTimeout = const Duration(seconds: 2);
  try {
    final req = await client.postUrl(Uri.parse('$_apiBase$path'));
    req.headers.contentType = ContentType.json;
    final bytes = utf8.encode(json.encode(body));
    req.contentLength = bytes.length; // disables chunked encoding
    req.add(bytes);
    final res = await req.close().timeout(const Duration(seconds: 4));
    final responseBody = await res.transform(utf8.decoder).join();
    return json.decode(responseBody) as Map<String, dynamic>;
  } catch (e) {
    return {'ok': false, 'error': e.toString()};
  } finally {
    client.close(force: true);
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await windowManager.ensureInitialized();

  const opts = WindowOptions(
    size: Size(_orbSize, _orbSize),
    minimumSize: Size(_orbSize, _orbSize),
    backgroundColor: Colors.transparent,
    skipTaskbar: false,
    titleBarStyle: TitleBarStyle.hidden,
    alwaysOnTop: true,
  );
  windowManager.waitUntilReadyToShow(opts, () async {
    await windowManager.setAsFrameless();
    await windowManager.setHasShadow(false);
    await windowManager.setAlignment(Alignment.bottomRight);
    await windowManager.show();
  });

  runApp(const ShorkaApp());
}

class ShorkaApp extends StatelessWidget {
  const ShorkaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Shorka',
      theme: ThemeData.dark(useMaterial3: true).copyWith(
        scaffoldBackgroundColor: Colors.transparent,
        textTheme: ThemeData.dark().textTheme.apply(
              fontFamily: 'Segoe UI',
              bodyColor: _textPrimary,
              displayColor: _textPrimary,
            ),
      ),
      home: const OverlayShell(),
    );
  }
}

enum Corner { topLeft, topRight, bottomLeft, bottomRight }

extension on Corner {
  Alignment get alignment => switch (this) {
        Corner.topLeft => Alignment.topLeft,
        Corner.topRight => Alignment.topRight,
        Corner.bottomLeft => Alignment.bottomLeft,
        Corner.bottomRight => Alignment.bottomRight,
      };
  bool get isLeft => this == Corner.topLeft || this == Corner.bottomLeft;
  bool get isBottom => this == Corner.bottomLeft || this == Corner.bottomRight;
  String get label => switch (this) {
        Corner.topLeft => 'Top Left',
        Corner.topRight => 'Top Right',
        Corner.bottomLeft => 'Bottom Left',
        Corner.bottomRight => 'Bottom Right',
      };
}

enum PanelView { collapsed, transcript, settings }

class OverlayShell extends StatefulWidget {
  const OverlayShell({super.key});
  @override
  State<OverlayShell> createState() => _OverlayShellState();
}

class _OverlayShellState extends State<OverlayShell>
    with TickerProviderStateMixin, WindowListener {
  // ── Backend state ─────────────────────────────────────────
  bool _connected = false;
  bool _listening = false;
  bool _speaking = false;
  bool _awaitingConfirm = false;
  String _voice = 'rachel';
  String _lastUser = '';
  String _lastAssistant = '';
  List<Map<String, dynamic>> _transcript = [];
  List<Map<String, dynamic>> _voices = [];

  Timer? _pollFast;
  Timer? _pollSlow;

  // ── UI state ──────────────────────────────────────────────
  Corner _corner = Corner.bottomRight;
  PanelView _view = PanelView.collapsed;

  late final AnimationController _expandCtrl;
  late final AnimationController _orbBreath; // slow breathing for idle
  late final AnimationController _orbActive; // ring ripple when active

  @override
  void initState() {
    super.initState();
    windowManager.addListener(this);

    _expandCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 240),
    );
    _orbBreath = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2400),
    )..repeat(reverse: true);
    _orbActive = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();

    _pollStatus();
    _fetchVoices();
    _pollFast = Timer.periodic(
      const Duration(milliseconds: 700),
      (_) => _pollStatus(),
    );
    _pollSlow = Timer.periodic(
      const Duration(seconds: 4),
      (_) => _pollTranscript(),
    );
  }

  @override
  void dispose() {
    _pollFast?.cancel();
    _pollSlow?.cancel();
    windowManager.removeListener(this);
    _expandCtrl.dispose();
    _orbBreath.dispose();
    _orbActive.dispose();
    super.dispose();
  }

  // ── Polling ──────────────────────────────────────────────
  Future<void> _pollStatus() async {
    final r = await _apiGet('/status');
    if (!mounted) return;
    if (r['ok'] == true) {
      setState(() {
        _connected = true;
        _listening = r['listening'] == true;
        _speaking = r['speaking'] == true;
        _awaitingConfirm = r['awaiting_confirm'] == true;
        final v = r['voice'] as String?;
        if (v != null && v.isNotEmpty) _voice = v;
        _lastUser = (r['last_user'] as String?) ?? '';
        _lastAssistant = (r['last_assistant'] as String?) ?? '';
      });
    } else if (_connected) {
      setState(() {
        _connected = false;
        _listening = false;
        _speaking = false;
      });
    }
  }

  Future<void> _pollTranscript() async {
    if (!_connected || _view != PanelView.transcript) return;
    final r = await _apiGet('/transcript');
    if (!mounted || r['ok'] != true) return;
    final lines = (r['lines'] as List?) ?? const [];
    setState(() {
      _transcript = lines.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    });
  }

  Future<void> _fetchVoices() async {
    final r = await _apiGet('/voices');
    if (!mounted || r['ok'] != true) return;
    final raw = (r['voices'] as List?) ?? const [];
    setState(() {
      _voices = raw.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      final cur = r['current'] as String?;
      if (cur != null && cur.isNotEmpty) _voice = cur;
    });
  }

  // ── Actions ──────────────────────────────────────────────
  Future<void> _toggleMic() async {
    if (!_connected) {
      // Try to launch the backend.
      try {
        final dir = Directory.current.parent;
        final pythonExe = '${dir.path}\\.venv\\Scripts\\python.exe';
        await Process.start(
          'cmd.exe',
          ['/c', 'start', 'cmd.exe', '/k', pythonExe, '-m', 'app.main'],
          workingDirectory: dir.path,
        );
      } catch (_) {/* ignore */}
      return;
    }
    await _apiGet('/toggle-listen');
    await _pollStatus();
  }

  Future<void> _setVoice(String key) async {
    if (key == _voice) return;
    setState(() => _voice = key); // optimistic
    final r = await _apiPost('/set-voice', {'name': key});
    if (r['ok'] != true) await _pollStatus();
  }

  // ── Window plumbing ──────────────────────────────────────
  Future<void> _resizeForView() async {
    final size = switch (_view) {
      PanelView.collapsed => const Size(_orbSize, _orbSize),
      PanelView.transcript => const Size(_orbSize + 16 + _panelWidth, _panelHeight),
      PanelView.settings => const Size(_orbSize + 16 + _panelWidth, _settingsHeight),
    };
    await windowManager.setSize(size, animate: false);
    await windowManager.setAlignment(_corner.alignment);
  }

  void _setView(PanelView v) async {
    if (v == _view) return;
    setState(() => _view = v);
    await _resizeForView();
    if (v == PanelView.collapsed) {
      _expandCtrl.reverse();
    } else {
      _expandCtrl.forward();
    }
    if (v == PanelView.transcript) _pollTranscript();
  }

  Future<void> _setCorner(Corner c) async {
    if (c == _corner) return;
    setState(() => _corner = c);
    await windowManager.setAlignment(_corner.alignment);
  }

  @override
  void onWindowBlur() {
    // Auto-collapse when focus leaves so the overlay stays out of the way.
    if (_view != PanelView.collapsed) _setView(PanelView.collapsed);
  }

  // ── Build ────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.transparent,
      body: Align(
        alignment: _corner.alignment,
        child: Padding(
          padding: const EdgeInsets.all(0),
          child: _buildLayout(),
        ),
      ),
    );
  }

  Widget _buildLayout() {
    final orb = _Orb(
      size: _orbSize,
      connected: _connected,
      listening: _listening,
      speaking: _speaking,
      awaiting: _awaitingConfirm,
      breath: _orbBreath,
      active: _orbActive,
      onTap: () {
        // Tap orb: if collapsed → open transcript; else collapse.
        if (_view == PanelView.collapsed) {
          _setView(PanelView.transcript);
        } else {
          _setView(PanelView.collapsed);
        }
      },
      onLongPress: _toggleMic,
    );

    if (_view == PanelView.collapsed) return orb;

    final panel = SizedBox(
      width: _panelWidth,
      height: _view == PanelView.settings ? _settingsHeight : _panelHeight,
      child: AnimatedBuilder(
        animation: _expandCtrl,
        builder: (_, child) {
          final t = Curves.easeOutCubic.transform(_expandCtrl.value);
          return Opacity(
            opacity: t,
            child: Transform.translate(
              offset: Offset((_corner.isLeft ? -1 : 1) * 12 * (1 - t), 0),
              child: child,
            ),
          );
        },
        child: _view == PanelView.settings ? _buildSettings() : _buildTranscript(),
      ),
    );

    final children = _corner.isLeft
        ? [orb, const SizedBox(width: 16), panel]
        : [panel, const SizedBox(width: 16), orb];

    return SizedBox(
      height: _view == PanelView.settings ? _settingsHeight : _panelHeight,
      child: Row(
        crossAxisAlignment: _corner.isBottom ? CrossAxisAlignment.end : CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: children,
      ),
    );
  }

  // ── Transcript panel ─────────────────────────────────────
  Widget _buildTranscript() {
    final lines = _transcript;
    return _PanelShell(
      header: _PanelHeader(
        title: 'Conversation',
        statusText: _statusLabel(),
        statusColor: _statusColor(),
        trailing: IconButton(
          icon: const Icon(Icons.tune, color: _textSecondary, size: 18),
          tooltip: 'Settings',
          onPressed: () => _setView(PanelView.settings),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: lines.isEmpty
                ? _EmptyTranscript(connected: _connected)
                : ListView.builder(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    itemCount: lines.length,
                    reverse: false,
                    itemBuilder: (_, i) => _TranscriptBubble(
                      role: lines[i]['role'] as String? ?? 'assistant',
                      text: lines[i]['text'] as String? ?? '',
                    ),
                  ),
          ),
          _LiveStatusStrip(
            listening: _listening,
            speaking: _speaking,
            connected: _connected,
            awaiting: _awaitingConfirm,
            lastUser: _lastUser,
            lastAssistant: _lastAssistant,
          ),
          _BottomActions(
            connected: _connected,
            listening: _listening,
            onToggleMic: _toggleMic,
            onCloseApp: () async => windowManager.close(),
          ),
        ],
      ),
    );
  }

  // ── Settings panel ───────────────────────────────────────
  Widget _buildSettings() {
    return _PanelShell(
      header: _PanelHeader(
        title: 'Settings',
        statusText: _connected ? 'Connected' : 'Offline',
        statusColor: _connected ? _accent : _clrOffline,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: _textSecondary, size: 20),
          tooltip: 'Back',
          onPressed: () => _setView(PanelView.transcript),
        ),
      ),
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
        children: [
          _SectionLabel('Voice'),
          const SizedBox(height: 6),
          if (_voices.isEmpty)
            const _Hint('No voices loaded — start the assistant first.')
          else
            ..._voices.map((v) => _VoiceTile(
                  voiceKey: v['key'] as String,
                  name: v['name'] as String,
                  aliases: ((v['aliases'] as List?) ?? const []).cast<String>(),
                  selected: (v['key'] as String) == _voice,
                  onTap: () => _setVoice(v['key'] as String),
                )),
          const SizedBox(height: 18),
          _SectionLabel('Window position'),
          const SizedBox(height: 8),
          _CornerPicker(
            current: _corner,
            onPick: _setCorner,
          ),
          const SizedBox(height: 18),
          _SectionLabel('About'),
          const SizedBox(height: 6),
          const _Hint(
            'Shorka is a voice-only assistant for blind users.\n'
            'Say "Hey Shorka" to wake. Say "stop" to dismiss.',
          ),
        ],
      ),
    );
  }

  String _statusLabel() {
    if (!_connected) return 'Offline';
    if (_awaitingConfirm) return 'Awaiting yes/no';
    if (_speaking) return 'Speaking';
    if (_listening) return 'Listening';
    return 'Idle';
  }

  Color _statusColor() {
    if (!_connected) return _clrOffline;
    if (_awaitingConfirm) return _clrAwait;
    if (_speaking) return _clrSpeak;
    if (_listening) return _clrListen;
    return _accent;
  }
}

// ════════════════════════════════════════════════════════════════
// The orb — animated, glowing, state-reactive
// ════════════════════════════════════════════════════════════════

class _Orb extends StatelessWidget {
  final double size;
  final bool connected;
  final bool listening;
  final bool speaking;
  final bool awaiting;
  final AnimationController breath;
  final AnimationController active;
  final VoidCallback onTap;
  final VoidCallback onLongPress;

  const _Orb({
    required this.size,
    required this.connected,
    required this.listening,
    required this.speaking,
    required this.awaiting,
    required this.breath,
    required this.active,
    required this.onTap,
    required this.onLongPress,
  });

  Color get _coreColor {
    if (!connected) return _clrOffline;
    if (awaiting) return _clrAwait;
    if (speaking) return _clrSpeak;
    if (listening) return _clrListen;
    return _accent;
  }

  String get _tooltip {
    if (!connected) return 'Click to start Shorka • Long-press: launch backend';
    if (awaiting) return 'Awaiting yes/no';
    if (speaking) return 'Speaking — speak to interrupt';
    if (listening) return 'Listening — long-press to stop';
    return 'Idle — long-press to wake';
  }

  @override
  Widget build(BuildContext context) {
    final isAnimated = listening || speaking || awaiting;
    return SizedBox(
      width: size,
      height: size,
      child: Tooltip(
        message: _tooltip,
        waitDuration: const Duration(milliseconds: 600),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          onLongPress: onLongPress,
          child: AnimatedBuilder(
            animation: Listenable.merge([breath, active]),
            builder: (_, __) => CustomPaint(
              painter: _OrbPainter(
                color: _coreColor,
                breath: breath.value,
                active: active.value,
                isAnimated: isAnimated,
                listening: listening,
                speaking: speaking,
                connected: connected,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  final Color color;
  final double breath; // 0..1..0
  final double active; // 0..1 looping
  final bool isAnimated;
  final bool listening;
  final bool speaking;
  final bool connected;

  _OrbPainter({
    required this.color,
    required this.breath,
    required this.active,
    required this.isAnimated,
    required this.listening,
    required this.speaking,
    required this.connected,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final c = Offset(size.width / 2, size.height / 2);
    final maxR = math.min(size.width, size.height) / 2 - 4;

    // Outer ripples — only when active
    if (isAnimated) {
      for (int i = 0; i < 2; i++) {
        final phase = (active + i * 0.5) % 1.0;
        final r = maxR * (0.55 + phase * 0.55);
        final opacity = (1.0 - phase) * 0.35;
        final paint = Paint()
          ..color = color.withOpacity(opacity)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.6;
        canvas.drawCircle(c, r, paint);
      }
    }

    // Glow
    final glowR = maxR * (isAnimated ? (0.62 + 0.06 * math.sin(active * math.pi * 2)) : 0.55);
    final glow = Paint()
      ..shader = RadialGradient(
        colors: [
          color.withOpacity(0.55),
          color.withOpacity(0.0),
        ],
      ).createShader(Rect.fromCircle(center: c, radius: glowR + 8));
    canvas.drawCircle(c, glowR + 8, glow);

    // Breath core (pulsing radius for idle state)
    final breathScale = isAnimated ? 1.0 : (0.94 + 0.06 * breath);
    final coreR = maxR * 0.42 * breathScale;

    // Core gradient
    final core = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.4),
        radius: 1.0,
        colors: [
          Color.lerp(Colors.white, color, 0.25)!,
          color,
          Color.lerp(color, Colors.black, 0.55)!,
        ],
        stops: const [0.0, 0.55, 1.0],
      ).createShader(Rect.fromCircle(center: c, radius: coreR));
    canvas.drawCircle(c, coreR, core);

    // Inner highlight
    final highlight = Paint()
      ..color = Colors.white.withOpacity(0.22)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 4);
    canvas.drawCircle(c.translate(-coreR * 0.25, -coreR * 0.3), coreR * 0.32, highlight);

    // Equalizer bars when speaking — gives a richer "speaking" cue
    if (speaking) {
      final barPaint = Paint()
        ..color = Colors.white.withOpacity(0.72)
        ..strokeCap = StrokeCap.round
        ..strokeWidth = 2.2;
      final n = 4;
      final spacing = coreR * 0.22;
      final start = c.dx - spacing * (n - 1) / 2;
      for (int i = 0; i < n; i++) {
        final h = coreR * (0.2 + 0.6 * math.sin(active * math.pi * 2 + i * 0.9).abs());
        final x = start + i * spacing;
        canvas.drawLine(
          Offset(x, c.dy - h / 2),
          Offset(x, c.dy + h / 2),
          barPaint,
        );
      }
    } else if (listening) {
      // Mic dot when listening
      final dot = Paint()..color = Colors.white;
      canvas.drawCircle(c, coreR * 0.16, dot);
    } else if (!connected) {
      // Power glyph
      final p = Paint()
        ..color = Colors.white.withOpacity(0.7)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round;
      canvas.drawArc(
        Rect.fromCircle(center: c, radius: coreR * 0.42),
        -math.pi * 0.65,
        math.pi * 1.3,
        false,
        p,
      );
      canvas.drawLine(c.translate(0, -coreR * 0.5), c.translate(0, -coreR * 0.1), p);
    }
  }

  @override
  bool shouldRepaint(covariant _OrbPainter old) =>
      old.breath != breath ||
      old.active != active ||
      old.color != color ||
      old.isAnimated != isAnimated ||
      old.listening != listening ||
      old.speaking != speaking ||
      old.connected != connected;
}

// ════════════════════════════════════════════════════════════════
// Panel chrome
// ════════════════════════════════════════════════════════════════

class _PanelShell extends StatelessWidget {
  final Widget header;
  final Widget child;
  const _PanelShell({required this.header, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: _bg,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: Colors.white.withOpacity(0.06), width: 1),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.45),
            blurRadius: 30,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          header,
          Container(height: 1, color: Colors.white.withOpacity(0.05)),
          Expanded(child: child),
        ],
      ),
    );
  }
}

class _PanelHeader extends StatelessWidget {
  final String title;
  final String statusText;
  final Color statusColor;
  final Widget? leading;
  final Widget? trailing;

  const _PanelHeader({
    required this.title,
    required this.statusText,
    required this.statusColor,
    this.leading,
    this.trailing,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      child: Row(
        children: [
          if (leading != null) ...[leading!, const SizedBox(width: 4)],
          Text(
            title,
            style: const TextStyle(
              color: _textPrimary,
              fontSize: 15,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.2,
            ),
          ),
          const Spacer(),
          _StatusPill(text: statusText, color: statusColor),
          if (trailing != null) ...[const SizedBox(width: 4), trailing!],
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  final String text;
  final Color color;
  const _StatusPill({required this.text, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: color.withOpacity(0.13),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withOpacity(0.35), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 6,
            height: 6,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════
// Transcript widgets
// ════════════════════════════════════════════════════════════════

class _TranscriptBubble extends StatelessWidget {
  final String role;
  final String text;
  const _TranscriptBubble({required this.role, required this.text});

  @override
  Widget build(BuildContext context) {
    final isUser = role == 'user';
    final bgColor = isUser ? _accent.withOpacity(0.16) : Colors.white.withOpacity(0.04);
    final textColor = isUser ? Colors.white : _textPrimary;
    final align = isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start;

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: align,
        children: [
          Padding(
            padding: const EdgeInsets.only(left: 4, right: 4, bottom: 2),
            child: Text(
              isUser ? 'You' : 'Shorka',
              style: const TextStyle(
                color: _textSecondary,
                fontSize: 10,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.4,
              ),
            ),
          ),
          ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: _panelWidth - 72),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: bgColor,
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(14),
                  topRight: const Radius.circular(14),
                  bottomLeft: Radius.circular(isUser ? 14 : 4),
                  bottomRight: Radius.circular(isUser ? 4 : 14),
                ),
              ),
              child: Text(
                text,
                style: TextStyle(color: textColor, fontSize: 13, height: 1.35),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyTranscript extends StatelessWidget {
  final bool connected;
  const _EmptyTranscript({required this.connected});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              connected ? Icons.graphic_eq : Icons.power_settings_new,
              color: _textSecondary,
              size: 36,
            ),
            const SizedBox(height: 10),
            Text(
              connected
                  ? 'Say "Hey Shorka" to start a conversation.'
                  : 'Backend offline — tap the orb to launch it.',
              textAlign: TextAlign.center,
              style: const TextStyle(color: _textSecondary, fontSize: 13, height: 1.4),
            ),
          ],
        ),
      ),
    );
  }
}

class _LiveStatusStrip extends StatelessWidget {
  final bool listening;
  final bool speaking;
  final bool connected;
  final bool awaiting;
  final String lastUser;
  final String lastAssistant;

  const _LiveStatusStrip({
    required this.listening,
    required this.speaking,
    required this.connected,
    required this.awaiting,
    required this.lastUser,
    required this.lastAssistant,
  });

  @override
  Widget build(BuildContext context) {
    String text;
    if (!connected) {
      text = 'Backend not running.';
    } else if (awaiting) {
      text = 'Waiting for yes / no…';
    } else if (speaking && lastAssistant.isNotEmpty) {
      text = lastAssistant;
    } else if (listening) {
      text = lastUser.isNotEmpty ? '"$lastUser"' : 'Listening…';
    } else if (lastAssistant.isNotEmpty) {
      text = lastAssistant;
    } else {
      text = 'Say "Hey Shorka" to begin.';
    }
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.03),
        border: Border(top: BorderSide(color: Colors.white.withOpacity(0.05))),
      ),
      child: Text(
        text,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: const TextStyle(
          color: _textSecondary,
          fontSize: 11.5,
          height: 1.4,
          fontStyle: FontStyle.italic,
        ),
      ),
    );
  }
}

class _BottomActions extends StatelessWidget {
  final bool connected;
  final bool listening;
  final VoidCallback onToggleMic;
  final VoidCallback onCloseApp;

  const _BottomActions({
    required this.connected,
    required this.listening,
    required this.onToggleMic,
    required this.onCloseApp,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
      child: Row(
        children: [
          Expanded(
            child: _PrimaryButton(
              icon: !connected
                  ? Icons.play_arrow_rounded
                  : (listening ? Icons.stop_rounded : Icons.mic_none_rounded),
              label: !connected
                  ? 'Start Shorka'
                  : (listening ? 'Stop listening' : 'Wake & listen'),
              color: !connected
                  ? _accent
                  : (listening ? _clrListen : _accent),
              onTap: onToggleMic,
            ),
          ),
          const SizedBox(width: 8),
          _IconBtn(
            icon: Icons.close_rounded,
            tooltip: 'Quit overlay',
            color: _textSecondary,
            onTap: onCloseApp,
          ),
        ],
      ),
    );
  }
}

class _PrimaryButton extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _PrimaryButton({
    required this.icon,
    required this.label,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Ink(
          padding: const EdgeInsets.symmetric(vertical: 11, horizontal: 14),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              colors: [color.withOpacity(0.85), color.withOpacity(0.55)],
            ),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: Colors.white, size: 18),
              const SizedBox(width: 8),
              Text(
                label,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.2,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final String tooltip;
  final Color color;
  final VoidCallback onTap;
  const _IconBtn({
    required this.icon,
    required this.tooltip,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.white.withOpacity(0.04),
        borderRadius: BorderRadius.circular(10),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(10),
          child: SizedBox(
            width: 40,
            height: 40,
            child: Icon(icon, color: color, size: 18),
          ),
        ),
      ),
    );
  }
}

// ════════════════════════════════════════════════════════════════
// Settings widgets
// ════════════════════════════════════════════════════════════════

class _SectionLabel extends StatelessWidget {
  final String label;
  const _SectionLabel(this.label);
  @override
  Widget build(BuildContext context) {
    return Text(
      label.toUpperCase(),
      style: const TextStyle(
        color: _textSecondary,
        fontSize: 10,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.2,
      ),
    );
  }
}

class _Hint extends StatelessWidget {
  final String text;
  const _Hint(this.text);
  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(color: _textSecondary, fontSize: 12, height: 1.4),
    );
  }
}

class _VoiceTile extends StatelessWidget {
  final String voiceKey;
  final String name;
  final List<String> aliases;
  final bool selected;
  final VoidCallback onTap;
  const _VoiceTile({
    required this.voiceKey,
    required this.name,
    required this.aliases,
    required this.selected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Material(
        color: selected ? _accent.withOpacity(0.13) : Colors.white.withOpacity(0.03),
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
            child: Row(
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: selected ? _accent : Colors.white.withOpacity(0.08),
                    shape: BoxShape.circle,
                  ),
                  alignment: Alignment.center,
                  child: Text(
                    name.isNotEmpty ? name[0] : '?',
                    style: TextStyle(
                      color: selected ? Colors.white : _textPrimary,
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        name,
                        style: const TextStyle(
                          color: _textPrimary,
                          fontSize: 13.5,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (aliases.isNotEmpty) ...[
                        const SizedBox(height: 2),
                        Text(
                          aliases.take(3).join(' · '),
                          style: const TextStyle(
                            color: _textSecondary,
                            fontSize: 11,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (selected)
                  const Icon(Icons.check_circle, color: _accent, size: 18),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CornerPicker extends StatelessWidget {
  final Corner current;
  final ValueChanged<Corner> onPick;
  const _CornerPicker({required this.current, required this.onPick});

  @override
  Widget build(BuildContext context) {
    Widget cell(Corner c) {
      final selected = c == current;
      return Expanded(
        child: AspectRatio(
          aspectRatio: 1,
          child: Padding(
            padding: const EdgeInsets.all(3),
            child: Material(
              color: selected ? _accent.withOpacity(0.18) : Colors.white.withOpacity(0.04),
              borderRadius: BorderRadius.circular(10),
              child: InkWell(
                onTap: () => onPick(c),
                borderRadius: BorderRadius.circular(10),
                child: Stack(
                  children: [
                    Align(
                      alignment: c.alignment,
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: Container(
                          width: 14,
                          height: 14,
                          decoration: BoxDecoration(
                            color: selected ? _accent : _textSecondary,
                            shape: BoxShape.circle,
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

    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.03),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        children: [
          Row(children: [cell(Corner.topLeft), cell(Corner.topRight)]),
          Row(children: [cell(Corner.bottomLeft), cell(Corner.bottomRight)]),
          const SizedBox(height: 4),
          Text(
            current.label,
            style: const TextStyle(color: _textSecondary, fontSize: 11),
          ),
        ],
      ),
    );
  }
}
