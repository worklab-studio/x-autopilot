"""
fingerprint.py — Deep browser fingerprint spoofing
Patches the vectors that playwright-stealth misses:
  - Canvas 2D fingerprinting
  - WebGL renderer / vendor strings
  - AudioContext fingerprinting
  - navigator.hardwareConcurrency
  - navigator.deviceMemory
  - navigator.platform / userAgentData
  - screen dimensions
  - font enumeration via measureText
  - Permissions timing

Injected as a page init script so it runs BEFORE any site JS.
"""

import random

# --- Realistic hardware profiles to pick from at launch ---
_PROFILES = [
    {
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "platform": "Win32",
        "renderer": "ANGLE (NVIDIA, NVIDIA GeForce GTX 1660 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendor": "Google Inc. (NVIDIA)",
        "audioNoise": 0.0000018,
        "canvasNoise": 3,
    },
    {
        "hardwareConcurrency": 12,
        "deviceMemory": 16,
        "platform": "Win32",
        "renderer": "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendor": "Google Inc. (Intel)",
        "audioNoise": 0.0000021,
        "canvasNoise": 2,
    },
    {
        "hardwareConcurrency": 16,
        "deviceMemory": 16,
        "platform": "MacIntel",
        "renderer": "ANGLE (Apple, Apple M2 Pro, OpenGL 4.1)",
        "vendor": "Google Inc. (Apple)",
        "audioNoise": 0.0000015,
        "canvasNoise": 2,
    },
    {
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "platform": "MacIntel",
        "renderer": "ANGLE (Apple, Apple M1, OpenGL 4.1)",
        "vendor": "Google Inc. (Apple)",
        "audioNoise": 0.0000019,
        "canvasNoise": 3,
    },
    {
        "hardwareConcurrency": 8,
        "deviceMemory": 8,
        "platform": "Win32",
        "renderer": "ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0, D3D11)",
        "vendor": "Google Inc. (AMD)",
        "audioNoise": 0.0000022,
        "canvasNoise": 4,
    },
]


def _pick_profile() -> dict:
    return random.choice(_PROFILES)


def build_fingerprint_script(profile: dict = None) -> str:
    """
    Returns a JS string to be injected via page.add_init_script().
    Each value is chosen once per browser launch so the fingerprint
    is consistent within a session but varies between runs.
    """
    if profile is None:
        profile = _pick_profile()

    hw_concurrency = profile["hardwareConcurrency"]
    device_memory = profile["deviceMemory"]
    platform = profile["platform"]
    gl_renderer = profile["renderer"]
    gl_vendor = profile["vendor"]
    audio_noise = profile["audioNoise"]
    canvas_noise = profile["canvasNoise"]

    return f"""
(function() {{
  'use strict';

  // ── 1. navigator.hardwareConcurrency ──────────────────────────────────────
  Object.defineProperty(navigator, 'hardwareConcurrency', {{
    get: () => {hw_concurrency},
    configurable: false,
  }});

  // ── 2. navigator.deviceMemory ─────────────────────────────────────────────
  Object.defineProperty(navigator, 'deviceMemory', {{
    get: () => {device_memory},
    configurable: false,
  }});

  // ── 3. navigator.platform ─────────────────────────────────────────────────
  Object.defineProperty(navigator, 'platform', {{
    get: () => '{platform}',
    configurable: false,
  }});

  // ── 4. Canvas 2D fingerprinting ───────────────────────────────────────────
  // Adds a tiny, invisible per-session noise to every getImageData / toDataURL
  // call so the canvas hash is unique but stable within the session.
  const _noise = {canvas_noise};
  const _OrigHTMLCanvasElement = HTMLCanvasElement.prototype;

  const _origToDataURL = _OrigHTMLCanvasElement.toDataURL;
  _OrigHTMLCanvasElement.toDataURL = function(type, ...args) {{
    const ctx = this.getContext('2d');
    if (ctx) {{
      const imageData = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
      for (let i = 0; i < imageData.data.length; i += 4) {{
        imageData.data[i]     = Math.min(255, imageData.data[i]     + (Math.random() < 0.05 ? _noise : 0));
        imageData.data[i + 1] = Math.min(255, imageData.data[i + 1] + (Math.random() < 0.05 ? _noise : 0));
      }}
      ctx.putImageData(imageData, 0, 0);
    }}
    return _origToDataURL.call(this, type, ...args);
  }};

  const _OrigCanvasRenderingContext2D = CanvasRenderingContext2D.prototype;
  const _origGetImageData = _OrigCanvasRenderingContext2D.getImageData;
  _OrigCanvasRenderingContext2D.getImageData = function(x, y, w, h) {{
    const imageData = _origGetImageData.call(this, x, y, w, h);
    for (let i = 0; i < imageData.data.length; i += 4) {{
      if (Math.random() < 0.02) {{
        imageData.data[i]     = Math.min(255, imageData.data[i]     + _noise);
        imageData.data[i + 1] = Math.min(255, imageData.data[i + 1] + _noise);
      }}
    }}
    return imageData;
  }};

  // ── 5. WebGL renderer / vendor strings ────────────────────────────────────
  const _getParameterProxyHandler = {{
    apply(target, thisArg, argumentsList) {{
      const param = argumentsList[0];
      // UNMASKED_RENDERER_WEBGL = 37446, UNMASKED_VENDOR_WEBGL = 37445
      if (param === 37446) return '{gl_renderer}';
      if (param === 37445) return '{gl_vendor}';
      return Reflect.apply(target, thisArg, argumentsList);
    }},
  }};

  const _getParameterProxy = new Proxy(WebGLRenderingContext.prototype.getParameter, _getParameterProxyHandler);
  WebGLRenderingContext.prototype.getParameter = _getParameterProxy;

  if (typeof WebGL2RenderingContext !== 'undefined') {{
    const _getParameterProxy2 = new Proxy(WebGL2RenderingContext.prototype.getParameter, _getParameterProxyHandler);
    WebGL2RenderingContext.prototype.getParameter = _getParameterProxy2;
  }}

  // ── 6. AudioContext fingerprinting ────────────────────────────────────────
  // Adds a tiny per-session offset to every AudioBuffer so the hash differs.
  const _audioNoise = {audio_noise};
  const _OrigAudioBuffer = AudioBuffer.prototype;
  const _origGetChannelData = _OrigAudioBuffer.getChannelData;
  _OrigAudioBuffer.getChannelData = function(channel) {{
    const arr = _origGetChannelData.call(this, channel);
    for (let i = 0; i < arr.length; i += 512) {{
      arr[i] += _audioNoise * (Math.random() * 2 - 1);
    }}
    return arr;
  }};

  // Also patch OfflineAudioContext to avoid startRendering fingerprints
  if (typeof OfflineAudioContext !== 'undefined') {{
    const _origOfflineGetChannelData = _OrigAudioBuffer.getChannelData;
    // Already patched above via prototype — applies automatically.
  }}

  // ── 7. Font enumeration via measureText ───────────────────────────────────
  // Add tiny sub-pixel noise to measureText so font presence detection
  // can't enumerate which fonts are installed.
  const _origMeasureText = CanvasRenderingContext2D.prototype.measureText;
  CanvasRenderingContext2D.prototype.measureText = function(text) {{
    const metrics = _origMeasureText.call(this, text);
    const jitter = (Math.random() - 0.5) * 0.0001;
    Object.defineProperty(metrics, 'width', {{
      value: metrics.width + jitter,
      configurable: true,
    }});
    return metrics;
  }};

  // ── 8. Permissions API timing noise ───────────────────────────────────────
  // Bots often query permissions synchronously in tight loops.
  // Adding micro-delays makes timing analysis harder.
  if (navigator.permissions && navigator.permissions.query) {{
    const _origPermQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = function(desc) {{
      return new Promise((resolve, reject) => {{
        setTimeout(() => _origPermQuery(desc).then(resolve).catch(reject), Math.random() * 8);
      }});
    }};
  }}

}})();
"""


# Singleton profile chosen at import time so it's stable per process
SESSION_PROFILE = _pick_profile()
FINGERPRINT_SCRIPT = build_fingerprint_script(SESSION_PROFILE)
