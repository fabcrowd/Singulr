/**

 * Singulr verification page — fingerprint + keystroke capture.

 */



const params = new URLSearchParams(window.location.search);

const token = params.get("token");



const $ = (id) => document.getElementById(id);

const states = ["loading", "blocked", "pending", "form", "success", "error"];



function show(id) {

  states.forEach((s) => $(s).classList.toggle("hidden", s !== id));

}



function deviceType() {

  return /iPhone|iPad|Android/i.test(navigator.userAgent) ? "mobile" : "desktop";

}



/** Obvious VM / automation signals from the browser environment. */

function collectEnvFlags() {

  const ua = navigator.userAgent || "";

  let webglRenderer = null;

  try {

    const canvas = document.createElement("canvas");

    const gl =

      canvas.getContext("webgl") || canvas.getContext("experimental-webgl");

    if (gl) {

      const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");

      if (debugInfo) {

        webglRenderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);

      }

    }

  } catch (err) {

    console.warn("WebGL probe unavailable", err);

  }



  return {

    webdriver: Boolean(navigator.webdriver),

    headless_ua: /HeadlessChrome/i.test(ua),

    plugins_count: navigator.plugins ? navigator.plugins.length : 0,

    languages_count: navigator.languages ? navigator.languages.length : 0,

    webgl_renderer: webglRenderer,

    outer_dims_zero: window.outerWidth === 0 && window.outerHeight === 0,

  };

}



/** Fallback visitor id when FingerprintJS is not configured. */

function fallbackVisitorId() {

  const parts = [

    navigator.userAgent,

    navigator.language,

    screen.width,

    screen.height,

    screen.colorDepth,

    Intl.DateTimeFormat().resolvedOptions().timeZone,

  ].join("|");

  let hash = 0;

  for (let i = 0; i < parts.length; i += 1) {

    hash = (hash << 5) - hash + parts.charCodeAt(i);

    hash |= 0;

  }

  return `fb_${Math.abs(hash)}`;

}



/** HMAC proof binding token + visitor_id to the precheck-issued secret. */

async function computeChallengeProof(secret, verifyToken, visitorId) {

  const enc = new TextEncoder();

  const key = await crypto.subtle.importKey(

    "raw",

    enc.encode(secret),

    { name: "HMAC", hash: "SHA-256" },

    false,

    ["sign"],

  );

  const sig = await crypto.subtle.sign(

    "HMAC",

    key,

    enc.encode(`${verifyToken}:${visitorId}`),

  );

  return Array.from(new Uint8Array(sig))

    .map((b) => b.toString(16).padStart(2, "0"))

    .join("");

}



async function loadFingerprint() {

  const pre = await fetch("/api/verify/precheck", {

    method: "POST",

    headers: { "Content-Type": "application/json" },

    body: JSON.stringify({ token, visitor_id: fallbackVisitorId() }),

  });



  if (!pre.ok) {

    show("blocked");

    return null;

  }



  const data = await pre.json();

  if (!data.allowed) {

    show("blocked");

    return null;

  }



  let visitorId = fallbackVisitorId();

  let requestId = null;



  if (data.fingerprint_public_key) {

    try {

      if (window.FingerprintJS) {

        const agent = await window.FingerprintJS.load();

        const result = await agent.get();

        visitorId = result.visitorId;

        requestId = result.requestId;

      }

    } catch (err) {

      console.warn("FingerprintJS unavailable, using fallback", err);

    }

  } else if (window.FingerprintJS) {

    try {

      const agent = await window.FingerprintJS.load();

      const result = await agent.get();

      visitorId = result.visitorId;

      requestId = result.requestId;

    } catch (err) {

      console.warn("FingerprintJS OSS failed", err);

    }

  }



  const pre2 = await fetch("/api/verify/precheck", {

    method: "POST",

    headers: { "Content-Type": "application/json" },

    body: JSON.stringify({ token, visitor_id: visitorId, request_id: requestId }),

  });

  const finalCheck = await pre2.json();

  if (!finalCheck.allowed) {

    show("blocked");

    return null;

  }



  return {

    visitorId,

    requestId,

    sentence: finalCheck.sentence,

    challengeSecret: finalCheck.challenge_secret,

  };

}



const keystrokes = [];

let startTime = null;

let errorCount = 0;



function attachKeystrokeCapture(input) {

  let lastUp = null;



  input.addEventListener("keydown", (e) => {

    if (e.isComposing) return;

    if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(e.key)) return;

    const now = performance.now();

    if (!startTime) startTime = now;

    const flight = lastUp === null ? 0 : now - lastUp;

    keystrokes.push({

      key: e.key,

      down: now - startTime,

      up: null,

      flight,

    });

  });



  input.addEventListener("keyup", (e) => {

    if (["Shift", "Control", "Alt", "Meta", "CapsLock"].includes(e.key)) return;

    const now = performance.now();

    lastUp = now;

    for (let i = keystrokes.length - 1; i >= 0; i -= 1) {

      if (keystrokes[i].key === e.key && keystrokes[i].up === null) {

        keystrokes[i].up = now - startTime;

        break;

      }

    }

  });



  input.addEventListener("paste", (e) => {

    e.preventDefault();

    errorCount += 1;

    $("match-hint").textContent = "Please type the sentence manually.";

    $("match-hint").className = "hint match-bad";

    input.value = "";

  });

}



function validateTyping(input, expected) {

  const typed = input.value;

  if (typed === expected) {

    $("match-hint").textContent = "Sentence matches.";

    $("match-hint").className = "hint match-ok";

    return true;

  }

  if (expected.startsWith(typed)) {

    $("match-hint").textContent = "Keep typing…";

    $("match-hint").className = "hint";

    return false;

  }

  $("match-hint").textContent = "Character mismatch — check spelling.";

  $("match-hint").className = "hint match-bad";

  errorCount += 1;

  return false;

}



function calcWpm(text, durationMs) {

  if (!durationMs) return null;

  const words = text.trim().split(/\s+/).length;

  return Math.round((words / durationMs) * 60000);

}



async function submit(session) {

  const input = $("typed");

  const privacy = $("privacy");

  const sentence = session.sentence;



  if (!validateTyping(input, sentence) || !privacy.checked) return;



  $("submit").disabled = true;



  const durationMs =

    keystrokes.length > 0 ? keystrokes[keystrokes.length - 1].down + 500 : 0;



  const challengeProof = await computeChallengeProof(

    session.challengeSecret,

    token,

    session.visitorId,

  );



  const res = await fetch("/api/verify/submit", {

    method: "POST",

    headers: { "Content-Type": "application/json" },

    body: JSON.stringify({

      token,

      visitor_id: session.visitorId,

      request_id: session.requestId,

      device_type: deviceType(),

      typed_text: input.value.trim(),

      keystrokes,

      wpm: calcWpm(input.value, durationMs),

      error_count: errorCount,

      privacy_accepted: true,

      env_flags: collectEnvFlags(),

      challenge_proof: challengeProof,

    }),

  });



  if (!res.ok) {

    show("error");

    return;

  }



  const result = await res.json();

  if (result.decision === "approve") {

    show("success");

    setTimeout(() => {

      window.location.href = "tg://";

    }, 1200);

  } else if (result.decision === "pending" || result.decision === "flag") {

    show("pending");

  } else {

    show("blocked");

  }

}



async function main() {

  if (!token) {

    show("error");

    $("error-text").textContent = "Missing verification token.";

    return;

  }



  const session = await loadFingerprint();

  if (!session) return;



  $("sentence").textContent = `"${session.sentence}"`;

  const input = $("typed");

  attachKeystrokeCapture(input);



  const update = () => {

    const ok = validateTyping(input, session.sentence);

    $("submit").disabled = !(ok && $("privacy").checked);

  };



  input.addEventListener("input", update);

  $("privacy").addEventListener("change", update);

  $("submit").addEventListener("click", () => submit(session));



  show("form");

}



main();


