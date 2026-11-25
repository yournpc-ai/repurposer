import type { InternalSoundRecipe } from "./recipes.js";
import type { FmLayer, Layer, SoundCategory, SoundDomain, SoundGraph, SyncCue } from "./types.js";

type Bus = Omit<SoundGraph, "layers" | "durationMs">;

function ring(hz: number, ratio: number, index: number, decay: number, gain = 0.6, startMs = 0): FmLayer {
  return { kind: "fm", carrierFreqStart: hz, modRatio: ratio, modIndexStart: index,
    modIndexEnd: 0.05, gain, startMs, envelope: { attackMs: 1.8, decayMs: decay } };
}

function wood(hz: number, brightness: number, decay: number, gain = 0.7, startMs = 0): Layer {
  return { kind: "pluck", freqStart: hz, brightness, damping: 0.996, gain, startMs,
    envelope: { attackMs: 1.3, decayMs: decay } };
}

function glide(hz: number, end: number, decay: number, gain = 0.6, startMs = 0,
  waveform: "sine" | "triangle" | "sawtooth" = "sine"): Layer {
  return { kind: "oscillator", waveform, freqStart: hz, freqEnd: end, curve: 0.48,
    gain, startMs, envelope: { attackMs: 3, decayMs: decay } };
}

function brush(low: number, high: number, decay: number, gain = 0.35, startMs = 0): Layer {
  return { kind: "noise", color: "pink", gain, startMs,
    filter: { kind: "bandpass", freqStart: low, freqEnd: high, q: 0.95 },
    envelope: { attackMs: 1.4, decayMs: decay } };
}

function swell(layer: Layer, pan = 0.5): Layer {
  return { ...layer, pan: { start: -pan, end: pan }, envelope: { attackMs: 8, bellPower: 2.5 } };
}

const brake = (end: number, exponent: number) => ({ start: 1, end, exponent });
const echo = (delayMs: number, mix: number) => ({ delayMs, mix, feedback: 0.32, dampHz: 2800 });
const glitch = (sampleHoldSteps: number, bitDepth: number, mix: number) => ({ sampleHoldSteps, bitDepth, mix });

function patch(domain: SoundDomain, category: SoundCategory, id: string, zh: string,
  use: string, mood: string, durationMs: number, layers: Layer[], bus: Bus = {}, cue: SyncCue = "onset"): InternalSoundRecipe {
  const name = id.split("_").map(word => word[0].toUpperCase() + word.slice(1)).join(" ");
  const energy = ["urgent", "heavy", "punchy", "abrasive"].includes(mood) ? "high"
    : domain === "interface" ? "subtle" : "medium";
  return {
    catalog: {
      id, domain, category, version: 1, name, name_zh: zh, moods: [mood], energy,
      desc: use, use_for: [use], avoid: [domain === "interface" ? "continuous cursor movement" : "unaccented dialogue"],
      suggested_duration_ms: [Math.round(durationMs * 0.65), Math.round(durationMs * 1.5)],
      sync_cue: cue, mix_hint: cue === "onset" ? "Seat the attack on contact, around −14 dB under speech."
        : "Align the measured peak with the picture cut and leave room for the tail.",
      params: {},
    },
    buildGraph: () => ({ durationMs, layers, lowpass: 10500, tailFadeMs: Math.min(32, durationMs / 6), ...bus }),
  };
}

type PatchArgs = Parameters<typeof patch> extends [SoundDomain, ...infer Rest] ? Rest : never;
const ui = (...args: PatchArgs) => patch("interface", ...args);
const film = (...args: PatchArgs) => patch("video", ...args);

export const additionalRecipes = [
  ui("tap", "tap_glass", "玻璃轻点", "Touch a glass control", "crystalline", 186, [ring(1420, 2.01, 1.6, 33), ring(3550, 3.5, 0.3, 9, 0.09)]),
  ui("tap", "tap_soft", "触屏软拍", "Tap a padded touch surface", "muted", 62, [glide(280, 110, 12), brush(620, 300, 5)]),
  ui("tap", "tap_wood", "温木轻击", "Touch a wooden key", "organic", 122, [wood(410, 0.43, 34), brush(1450, 700, 3)]),
  ui("select", "select_lock", "卡片锁定", "Seat a card in its slot", "precise", 136, [brush(3100, 1100, 8), wood(360, 0.81, 25, 0.6, 14)]),
  ui("select", "select_pill", "胶囊微弹", "Highlight a selected chip", "playful", 204, [glide(405, 780, 46), ring(980, 2, 0.2, 19, 0.1, 32)]),
  ui("toggle", "toggle_off", "拨片关闭", "Disable a switch", "muted", 88, [glide(430, 185, 18, 0.6, 0, "triangle"), brush(840, 390, 6)]),
  ui("toggle", "toggle_magnetic", "双段磁吸", "Latch a magnetic switch", "tactile", 173, [wood(770, 0.88, 15), ring(350, 1.414, 1.2, 24, 0.36, 23)]),
  ui("feedback", "feedback_success", "温暖成功双音", "Confirm a successful action", "warm", 435, [wood(523, 0.54, 105), ring(784, 2, 0.7, 77, 0.25, 68)]),
  ui("feedback", "feedback_complete", "完成和弦", "Resolve a completed sequence", "bright", 640, [ring(659, 2, 0.75, 140), ring(831, 2, 0.5, 110, 0.31, 34), wood(988, 0.68, 120, 0.4, 72)]),
  ui("feedback", "feedback_error", "克制双低音", "Signal a rejected input", "reserved", 305, [glide(221, 194, 37, 0.5, 0, "triangle"), glide(175, 152, 32, 0.39, 83, "triangle")]),
  ui("notify", "notify_crystal", "晶莹双响", "Announce a new notification", "crystalline", 560, [ring(1046, 3.5, 1.2, 110), ring(1568, 2, 0.8, 84, 0.29, 91)]),
  ui("notify", "notify_bubble", "气泡到达", "Surface a quiet notification", "soft", 182, [glide(360, 880, 44), glide(720, 1030, 18, 0.12)]),
  ui("motion", "motion_drawer_open", "抽屉滑开", "Slide a drawer into view", "fluid", 285, [swell(brush(430, 2650, 100)), swell(glide(160, 290, 80, 0.16))], {}, "energy_peak"),
  ui("motion", "motion_drawer_close", "阻尼收起", "Close a damped panel", "muted", 195, [swell(brush(1800, 240, 65)), wood(245, 0.36, 14, 0.22, 108)], {}, "energy_peak"),
  ui("motion", "motion_spring", "弹性归位", "Settle a spring-loaded control", "elastic", 324, [glide(630, 265, 57, 0.5, 0, "triangle"), glide(235, 420, 32, 0.22, 72), wood(370, 0.34, 18, 0.2, 120)]),
  ui("type", "type_mech_thock", "机械轴沉击", "Press a lubricated mechanical key", "tactile", 116, [wood(185, 0.66, 30), brush(2050, 710, 8), wood(450, 0.35, 10, 0.26, 13)]),
  ui("type", "type_soft_key", "薄键轻打", "Type on a low-profile keyboard", "muted", 49, [brush(1160, 490, 6), glide(455, 280, 7, 0.18)]),
  ui("type", "type_enter", "回车重键", "Commit a terminal command", "punchy", 192, [wood(142, 0.92, 43), brush(3100, 430, 12), ring(315, 1.414, 1.8, 22, 0.18, 27)]),
  ui("type", "type_backspace", "退格轻敲", "Remove the preceding character", "dry", 78, [ring(780, 1.414, 2.1, 8), brush(2570, 950, 6, 0.33, 12)]),
  ui("system", "system_unlock", "系统解锁", "Release a secure lock", "precise", 292, [ring(920, 2.5, 1.8, 49), ring(1380, 2, 0.5, 45, 0.26, 49)]),
  ui("system", "system_deploy", "上线确认", "Confirm a deployment", "confident", 498, [wood(330, 0.51, 85), glide(495, 660, 89, 0.22, 76, "triangle")]),
  ui("system", "system_connect", "连接建立", "Establish a connection", "fluid", 188, [glide(370, 1110, 46), brush(1100, 3200, 12, 0.1)]),
  ui("navigate", "nav_forward", "页面前推", "Navigate to the next page", "fluid", 220, [swell(brush(750, 3000, 65), 0.8)], {}, "energy_peak"),
  ui("navigate", "nav_back", "返回轻退", "Return to the preceding page", "soft", 162, [swell(glide(630, 210, 60, 0.4, 0, "triangle"), -0.65), swell(brush(1500, 510, 45), -0.65)], {}, "energy_peak"),
  ui("navigate", "nav_tab", "标签横切", "Switch the active tab", "crisp", 75, [ring(1220, 1.5, 0.9, 13), wood(600, 0.6, 8, 0.22, 7)]),
  ui("drag", "drag_pickup", "抓起微震", "Lift an item for dragging", "elastic", 158, [glide(145, 320, 38), wood(510, 0.47, 14, 0.3)]),
  ui("drag", "drag_snap", "磁吸对准", "Snap a handle onto a guide", "precise", 81, [brush(3400, 1200, 6), ring(810, 1.414, 1.6, 13)]),
  ui("drag", "drag_drop", "柔和落位", "Release a dragged item", "warm", 236, [wood(220, 0.34, 59), glide(140, 78, 37, 0.3, 9)]),
  ui("progress", "progress_tick", "步进滴答", "Mark one progress increment", "dry", 57, [wood(1510, 0.88, 10), brush(2800, 1300, 3)]),
  ui("progress", "progress_pulse", "加载脉冲", "Pulse a loading indicator", "soft", 340, [glide(143, 108, 51), glide(130, 97, 31, 0.22, 82)]),
  ui("progress", "progress_milestone", "里程达成", "Mark the final progress milestone", "bright", 510, [ring(880, 2.5, 1.2, 98), wood(1320, 0.78, 55, 0.34, 61)]),
  ui("message", "msg_send", "消息发出", "Send an outgoing message", "fluid", 166, [glide(520, 1430, 44), brush(1200, 3900, 28, 0.14)]),
  ui("message", "msg_receive", "回复气泡", "Receive an incoming reply", "playful", 248, [glide(760, 390, 46), glide(525, 810, 31, 0.28, 41)]),
  ui("message", "msg_ai_start", "思考晶音", "Signal the assistant beginning to think", "crystalline", 426, [ring(698, 3.5, 1.4, 79), ring(1047, 2, 0.7, 69, 0.24, 42)]),
  film("risers", "riser_snap_half", "半秒快推", "Anticipate a rapid cut", "urgent", 500, [
    { ...brush(420, 6400, 90), envelope: { attackMs: 8, risePower: 2.4, releaseMs: 13 } },
    { ...glide(180, 720, 90, 0.28, 0, "sawtooth"), envelope: { attackMs: 4, risePower: 2, releaseMs: 12 } }], {}, "end_peak"),
  film("impacts", "impact_metal_cold", "冷金属撞击", "Strike a steel surface on the cut", "heavy", 748, [ring(247, 1.414, 4.6, 138), glide(129, 47, 86), brush(4700, 730, 15)], { drive: 1.2, bias: 0.08, echo: echo(76, 0.15) }),
  film("whooshes", "whoosh_micro", "极速短甩", "Whip a close cut across the frame", "kinetic", 220, [swell(brush(550, 5500, 80), 0.95), swell(glide(280, 95, 65, 0.18))], {}, "energy_peak"),
  film("transitions", "trans_tape_stop", "磁带急停", "Brake a tape transport into a cut", "dramatic", 695, [glide(219, 219, 228, 0.4, 0, "sawtooth"), ring(328, 2, 1.4, 180), brush(700, 180, 80)], { pitchCurve: brake(0.08, 1.5), drive: 0.6 }),
  film("transitions", "trans_vinyl_pull", "黑胶回拉", "Pull a record back across a transition", "kinetic", 472, [swell(glide(102, 520, 98, 0.5, 0, "sawtooth")), swell(brush(590, 3100, 80))], { pitchCurve: brake(0.12, 3.2) }, "energy_peak"),
  film("transitions", "trans_shutter", "机械快门", "Cut on a two-curtain shutter", "punchy", 168, [brush(3600, 810, 13), wood(470, 0.91, 18), brush(2100, 670, 14, 0.25, 34)]),
  film("accents", "accent_spark", "点睛闪音", "Highlight a key word", "bright", 275, [ring(1880, 3.5, 1.1, 44), ring(2790, 2, 0.6, 26, 0.19, 6)]),
  film("accents", "accent_counter", "数字跃升", "Accent a counter increment", "precise", 145, [wood(795, 0.78, 28), glide(625, 990, 15, 0.2, 12)]),
  film("drops", "drop_vacuum", "瞬间抽空", "Pull the air out of a reveal", "dramatic", 890, [swell(brush(2300, 130, 80)), swell(glide(125, 44, 150))], { pitchCurve: brake(0.48, 1.6) }, "energy_peak"),
  film("drops", "drop_pitch_dive", "失重俯冲", "Dive into a low electronic downbeat", "heavy", 475, [glide(370, 83, 108, 0.48, 0, "sawtooth"), glide(164, 54, 130)], { pitchCurve: brake(0.22, 0.7), drive: 0.9 }),
  film("glitches", "glitch_rip", "像素撕裂", "Rip a frame into pixels", "abrasive", 148, [brush(4300, 780, 38), ring(460, 1.414, 4, 27)], { glitch: glitch(9, 5, 0.88) }),
  film("glitches", "glitch_data", "数据流扫频", "Sweep through a stream of data", "technical", 410, [swell(glide(190, 2300, 70, 0.5, 0, "sawtooth")), swell(brush(700, 4500, 80))], { glitch: glitch(17, 8, 0.8) }, "energy_peak"),
  film("glitches", "glitch_stutter", "数字卡顿", "Interrupt playback with three clipped packets", "urgent", 267, [ring(880, 1.5, 3, 11), wood(660, 1, 14, 0.5, 37), brush(3000, 500, 18, 0.24, 79)], { glitch: glitch(5, 6, 0.74) }),
  film("ambience", "ambience_obsidian", "暗石低鸣", "Hold a dark interior under a reveal", "dark", 2230, [swell(glide(57, 61, 300, 0.5, 0, "triangle")), swell(brush(210, 95, 90), -0.6)], { drive: 0.25 }, "energy_peak"),
  film("ambience", "ambience_warm_pad", "暖空气垫", "Float a warm chord under a pause", "warm", 2890, [swell(ring(196, 2, 0.55, 200)), swell(glide(294, 296, 100, 0.27, 0, "triangle"), -0.45), swell(brush(770, 1680, 100), 0.8)], { echo: echo(143, 0.22) }, "energy_peak"),
  film("titles", "title_slam", "大字压屏", "Land a bold title on screen", "heavy", 482, [glide(190, 52, 78), wood(168, 0.9, 54), brush(2350, 310, 22)], { drive: 1.5, echo: echo(63, 0.17) }),
  film("titles", "title_shimmer", "标题鎏光", "Pass a metallic highlight over type", "luminous", 1060, [swell(ring(740, 1.414, 2.2, 140)), swell(brush(2100, 7400, 100), -0.5)], { echo: echo(97, 0.22) }, "energy_peak"),
  film("pops", "pop_crisp", "清脆蹦点", "Pop a small graphic into view", "crisp", 65, [ring(1260, 2.4, 1.5, 9), brush(3900, 1200, 4)]),
  film("pops", "pop_droplet", "水滴微弹", "Accent a small liquid bounce", "playful", 234, [glide(1380, 490, 39), ring(930, 2, 0.35, 27, 0.23, 34)]),
  film("stingers", "stinger_marimba", "木琴三音", "Resolve a brand sign-off on wooden bars", "warm", 915, [wood(392, 0.64, 100), wood(494, 0.68, 110, 0.6, 94), wood(587, 0.7, 148, 0.54, 188)], { echo: echo(105, 0.21) }),
  film("stingers", "stinger_tech", "未来定音", "Sign off with a compact electronic chord", "technical", 670, [{ ...ring(330, 1.5, 2, 110), modIndexEnd: 0.12, secondaryRatio: 3, secondaryIndex: 0.6 }, ring(495, 2, 0.8, 100, 0.27, 42)], { echo: echo(79, 0.25) }),
  film("tension", "tension_radar", "雷达微扫描", "Track a distant contact before a reveal", "suspenseful", 1530,
    [swell(ring(590, 2.03, 0.45, 250), 0.9), swell(brush(380, 960, 200), -0.4)], { echo: echo(184, 0.24) }, "energy_peak"),
  film("tension", "tension_clock", "秒表滴答", "Count down to a decision", "tense", 1120, [wood(1250, 0.86, 20, 0.27, 25), ring(960, 1.414, 1.8, 28, 0.65, 505), brush(3450, 1400, 9, 0.16, 1005)], {}, "energy_peak"),
  film("tension", "tension_heartbeat", "双搏心跳", "Build suspense with a double heartbeat", "tense", 825, [glide(105, 54, 70), glide(88, 48, 51, 0.45, 146), brush(240, 100, 45, 0.18)], { drive: 0.8 }),
];
