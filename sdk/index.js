"use strict";

const { spawn } = require("child_process");
const path = require("path");

const DEFAULT_PORT = 7627;
const POLL_INTERVAL = 2000;   // ms between status polls
const SERVER_TIMEOUT = 30000; // ms to wait for server to start

class NoteNinja {
  /**
   * @param {object} options
   * @param {string} [options.openaiKey]     - OpenAI API key (falls back to OPENAI_API_KEY env var)
   * @param {string} [options.anthropicKey]  - Anthropic API key (falls back to ANTHROPIC_API_KEY env var)
   * @param {number} [options.port=7627]     - Local port for the NoteNinja server
   * @param {string} [options.pythonDir]     - Path to the NoteNinja Python repo (defaults to parent of sdk/)
   */
  constructor(options = {}) {
    this.openaiKey    = options.openaiKey    || process.env.OPENAI_API_KEY    || "";
    this.anthropicKey = options.anthropicKey || process.env.ANTHROPIC_API_KEY || "";
    this.port         = options.port || DEFAULT_PORT;
    this.pythonDir    = options.pythonDir || path.resolve(__dirname, "..");
    this._proc        = null;
  }

  get _base() {
    return `http://127.0.0.1:${this.port}`;
  }

  // ── Server lifecycle ──────────────────────────────────────────────────────

  /** Start the local NoteNinja server (no-op if already running). */
  async start() {
    if (await this._ping()) return; // already up

    const python = path.join(this.pythonDir, ".venv", "bin", "python");
    const script = path.join(this.pythonDir, "server.py");

    this._proc = spawn(python, [script, "--port", this.port], {
      env: {
        ...process.env,
        OPENAI_API_KEY:    this.openaiKey,
        ANTHROPIC_API_KEY: this.anthropicKey,
      },
      stdio: ["ignore", "pipe", "pipe"],
    });

    this._proc.stderr.on("data", (d) => {
      const line = d.toString().trim();
      if (line) process.stderr.write(`[NoteNinja] ${line}\n`);
    });

    await this._waitForReady();
  }

  /** Stop the local server. */
  async stop() {
    if (this._proc) {
      this._proc.kill();
      this._proc = null;
    }
  }

  // ── API ───────────────────────────────────────────────────────────────────

  /** List available audio input devices. */
  async devices() {
    const { devices } = await this._get("/api/devices");
    return devices; // [{ id, name }]
  }

  /**
   * Start a recording session.
   * @param {object} [options]
   * @param {string} [options.meetingName]
   * @param {number} [options.deviceId]
   * @returns {RecordingSession}
   */
  async startRecording(options = {}) {
    const body = {
      meeting_name: options.meetingName || null,
      device_id:    options.deviceId    ?? null,
    };
    const res = await this._post("/api/record/start", body);
    return new RecordingSession(this, res.session_id);
  }

  /**
   * Generate notes from an existing transcript string (no recording needed).
   * @param {string} transcript
   * @param {object} [options]
   * @param {string} [options.meetingName]
   * @param {string} [options.extraContext]
   */
  async generateNotes(transcript, options = {}) {
    return this._post("/api/notes", {
      transcript,
      meeting_name:  options.meetingName  || "Meeting",
      extra_context: options.extraContext || "",
    });
  }

  // ── Internals ─────────────────────────────────────────────────────────────

  async _get(path) {
    const res = await fetch(`${this._base}${path}`);
    if (!res.ok) throw new Error(`NoteNinja API error ${res.status}: ${await res.text()}`);
    return res.json();
  }

  async _post(path, body) {
    const res = await fetch(`${this._base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`NoteNinja API error ${res.status}: ${await res.text()}`);
    return res.json();
  }

  async _ping() {
    try {
      await fetch(`${this._base}/health`);
      return true;
    } catch {
      return false;
    }
  }

  async _waitForReady() {
    const deadline = Date.now() + SERVER_TIMEOUT;
    while (Date.now() < deadline) {
      if (await this._ping()) return;
      await _sleep(500);
    }
    throw new Error("NoteNinja server failed to start within 30 seconds");
  }
}


class RecordingSession {
  constructor(client, sessionId) {
    this._client    = client;
    this._sessionId = sessionId;
  }

  /** Current status from the server. */
  async status() {
    return this._client._get("/api/record/status");
  }

  /**
   * Stop the recording and wait for transcript + notes to be generated.
   * @param {object} [options]
   * @param {string} [options.extraContext] - Job description, agenda, etc.
   * @returns {{ transcript, notes, transcriptPath, notesPath, audioPath, durationSeconds }}
   */
  async stop(options = {}) {
    await this._client._post("/api/record/stop", {
      session_id:    this._sessionId,
      extra_context: options.extraContext || "",
    });

    // Poll until done
    while (true) {
      await _sleep(POLL_INTERVAL);
      const s = await this.status();
      if (s.status === "done")   return _camelResult(s.result);
      if (s.status === "error")  throw new Error(`NoteNinja processing error: ${s.error}`);
    }
  }
}

function _camelResult(r) {
  return {
    transcript:      r.transcript,
    notes:           r.notes,
    transcriptPath:  r.transcript_path,
    notesPath:       r.notes_path,
    audioPath:       r.audio_path,
    durationSeconds: r.duration_seconds,
  };
}

function _sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

module.exports = NoteNinja;
