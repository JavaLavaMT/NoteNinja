/**
 * Local test — run with: node sdk/test.js
 * Tests the server start, device list, and a short recording.
 */

const NoteNinja = require("./index");
const path = require("path");

async function main() {
  const nn = new NoteNinja({
    pythonDir: path.resolve(__dirname, ".."),
    // Keys fall back to OPENAI_API_KEY / ANTHROPIC_API_KEY env vars
  });

  console.log("Starting NoteNinja server...");
  await nn.start();
  console.log("✓ Server is up on localhost:7627\n");

  console.log("Available audio devices:");
  const devices = await nn.devices();
  devices.forEach((d) => console.log(`  [${d.id}] ${d.name}`));

  console.log("\nStarting a 5-second test recording...");
  const session = await nn.startRecording({ meetingName: "SDK Test Recording" });
  console.log("✓ Recording started — waiting 5 seconds...");

  await new Promise((r) => setTimeout(r, 5000));

  console.log("Stopping and generating notes...");
  const result = await session.stop({
    extraContext: "This is a test recording to verify the SDK works.",
  });

  console.log("\n✓ Done!\n");
  console.log("Transcript:", result.transcript || "(empty — no speech detected)");
  console.log("Notes path:", result.notesPath);
  console.log("Audio path:", result.audioPath);

  await nn.stop();
  console.log("\n✓ Server stopped.");
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
