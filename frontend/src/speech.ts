import type { ComputerPreferences } from "./types";

export type SpeechPriority = "ordinary" | "critical";

interface QueuedSpeech {
  text: string;
  settings: ComputerPreferences;
  priority: SpeechPriority;
}

class LocalSpeechOutput {
  private queue: QueuedSpeech[] = [];
  private speaking = false;
  private criticalFlightState = false;

  voices(): SpeechSynthesisVoice[] {
    return typeof window !== "undefined" && "speechSynthesis" in window
      ? window.speechSynthesis.getVoices()
      : [];
  }

  available(): boolean {
    return typeof window !== "undefined"
      && "speechSynthesis" in window
      && typeof SpeechSynthesisUtterance !== "undefined";
  }

  setCriticalFlightState(active: boolean): void {
    this.criticalFlightState = active;
    if (active) {
      this.queue = this.queue.filter((item) => item.priority === "critical");
    }
  }

  speak(
    text: string,
    settings: ComputerPreferences,
    priority: SpeechPriority = "ordinary",
  ): boolean {
    const value = text.trim();
    if (
      !value
      || !settings.speech_output_enabled
      || settings.verbosity === "silent"
      || !this.available()
      || (this.criticalFlightState && priority !== "critical")
    ) return false;

    if (
      this.queue.some((item) => item.text === value)
      || (window.speechSynthesis.speaking && this.queue.at(0)?.text === value)
    ) return false;

    if (priority === "critical") {
      window.speechSynthesis.cancel();
      this.speaking = false;
      this.queue = this.queue.filter((item) => item.priority === "critical");
      this.queue.unshift({ text: value, settings, priority });
    } else {
      this.queue.push({ text: value, settings, priority });
    }
    this.drain();
    return true;
  }

  dismiss(): void {
    this.queue = [];
    this.speaking = false;
    if (this.available()) window.speechSynthesis.cancel();
  }

  private drain(): void {
    if (this.speaking || !this.queue.length || !this.available()) return;
    const item = this.queue.shift()!;
    const utterance = new SpeechSynthesisUtterance(item.text);
    const voice = this.voices().find(
      (candidate) => candidate.voiceURI === item.settings.speech_voice
        || candidate.name === item.settings.speech_voice,
    );
    if (voice) utterance.voice = voice;
    utterance.rate = item.settings.speech_rate;
    utterance.volume = item.settings.speech_volume;
    utterance.onend = () => {
      this.speaking = false;
      this.drain();
    };
    utterance.onerror = () => {
      this.speaking = false;
      this.drain();
    };
    this.speaking = true;
    window.speechSynthesis.speak(utterance);
  }
}

export const speechOutput = new LocalSpeechOutput();
