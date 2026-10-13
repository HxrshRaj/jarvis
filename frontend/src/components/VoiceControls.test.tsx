import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceControls } from "./VoiceControls";

const { transcribe } = vi.hoisted(() => ({ transcribe: vi.fn() }));
vi.mock("@/lib/api", async (orig) => ({ ...(await orig<typeof import("@/lib/api")>()), api: { transcribe } }));

class FakeRecorder {
  static instances: FakeRecorder[] = [];
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: MediaStream) { FakeRecorder.instances.push(this); }
  start() { this.state = "recording"; }
  stop() { this.state = "inactive"; this.ondataavailable?.({ data: new Blob(["audio-bytes"]) }); this.onstop?.(); }
}

const speech = { muted: false, volume: 0.8, auto: false };
const setup = (canTranscribe = true, onTranscript = vi.fn()) => {
  render(<VoiceControls canTranscribe={canTranscribe} onTranscript={onTranscript} speech={speech} setSpeech={vi.fn()} speaking={false} stopSpeaking={vi.fn()} />);
  return onTranscript;
};
const button = () => screen.getByRole("button", { name: /push to talk|recording/i });

describe("VoiceControls", () => {
  const stopTrack = vi.fn();
  beforeEach(() => {
    vi.clearAllMocks(); FakeRecorder.instances = [];
    vi.stubGlobal("MediaRecorder", FakeRecorder);
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: stopTrack }] }) } });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("explains when no speech-to-text provider is configured and never opens the mic", async () => {
    setup(false);
    fireEvent.pointerDown(button());
    expect(await screen.findByText(/No speech-to-text provider/)).toBeInTheDocument();
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled();
  });

  it("shows a denied state when the user blocks the microphone", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValue(new DOMException("no", "NotAllowedError"));
    setup();
    fireEvent.pointerDown(button());
    expect(await screen.findByText(/Microphone access was denied/)).toBeInTheDocument();
    expect(FakeRecorder.instances).toHaveLength(0);
  });

  it("records only while held, uploads once, releases the mic, and delivers the transcript", async () => {
    transcribe.mockResolvedValue({ text: "  run the tests  " });
    const onTranscript = setup();
    fireEvent.pointerDown(button());
    await waitFor(() => expect(screen.getByRole("button", { name: /recording/i })).toBeInTheDocument());
    expect(transcribe).not.toHaveBeenCalled(); // nothing uploaded while recording
    await act(async () => { fireEvent.pointerUp(screen.getByRole("button", { name: /recording/i })); });
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("run the tests"));
    expect(transcribe).toHaveBeenCalledTimes(1);
    expect(stopTrack).toHaveBeenCalled(); // mic released immediately
  });

  it("cancel discards audio without uploading", async () => {
    setup();
    fireEvent.pointerDown(button());
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(stopTrack).toHaveBeenCalled());
    expect(transcribe).not.toHaveBeenCalled();
  });

  it("surfaces provider failures", async () => {
    transcribe.mockRejectedValue(new Error("transcription failed"));
    setup();
    fireEvent.pointerDown(button());
    await screen.findByRole("button", { name: /recording/i });
    await act(async () => { fireEvent.pointerUp(screen.getByRole("button", { name: /recording/i })); });
    expect(await screen.findByText(/transcription failed/)).toBeInTheDocument();
  });
});
