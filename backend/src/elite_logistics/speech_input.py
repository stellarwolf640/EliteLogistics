"""Explicit push-to-talk adapter for the local Windows speech recognizer.

The recognizer is deliberately activation-gated. It has no wake-word loop and
cannot execute a command by itself; callers must explicitly start and stop a
capture, then pass an accepted transcript through the normal Computer command
executor.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import threading
from typing import Any


_RECOGNIZER_SCRIPT = r"""
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$recognizer = New-Object System.Speech.Recognition.SpeechRecognitionEngine
$recognizer.SetInputToDefaultAudioDevice()
$recognizer.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
$results = [System.Collections.ArrayList]::Synchronized((New-Object System.Collections.ArrayList))
$recognizer.add_SpeechRecognized({
    param($sender, $eventArgs)
    $null = $results.Add([pscustomobject]@{
        text = $eventArgs.Result.Text
        confidence = [double]$eventArgs.Result.Confidence
    })
})
$recognizer.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
$null = [Console]::ReadLine()
$recognizer.RecognizeAsyncStop()
Start-Sleep -Milliseconds 350
$text = (($results | ForEach-Object { $_.text }) -join " ").Trim()
$confidence = if ($results.Count -gt 0) {
    [double](($results | Measure-Object -Property confidence -Average).Average)
} else { 0.0 }
[pscustomobject]@{ text = $text; confidence = $confidence } | ConvertTo-Json -Compress
$recognizer.Dispose()
"""


class PushToTalkRecognizer:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._process: subprocess.Popen[str] | None = None

    def _executable(self) -> str | None:
        if platform.system() != "Windows":
            return None
        return shutil.which("powershell.exe")

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = self._process is not None and self._process.poll() is None
        return {
            "available": self._executable() is not None,
            "active": active,
            "engine": "windows_system_speech",
            "microphone": "Windows default input",
            "activation": "push_to_talk",
            "wake_word_available": False,
            "local_only": True,
        }

    def start(self) -> dict[str, Any]:
        executable = self._executable()
        if executable is None:
            raise RuntimeError(
                "Local Windows speech recognition is unavailable on this system."
            )
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                raise RuntimeError("Push-to-talk capture is already active.")
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._process = subprocess.Popen(
                [
                    executable,
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _RECOGNIZER_SCRIPT,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                creationflags=creation_flags,
            )
        return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            process = self._process
            self._process = None
        if process is None or process.poll() is not None:
            raise RuntimeError("Push-to-talk capture is not active.")
        try:
            stdout, stderr = process.communicate(input="\n", timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            raise RuntimeError("The local speech recognizer did not stop cleanly.")
        if process.returncode:
            detail = stderr.strip().splitlines()[-1] if stderr.strip() else ""
            raise RuntimeError(
                f"Local speech recognition failed{f': {detail}' if detail else '.'}"
            )
        line = next(
            (value for value in reversed(stdout.splitlines()) if value.strip()),
            "",
        )
        if not line:
            return {"text": "", "confidence": 0.0}
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("The local speech recognizer returned invalid output.") from exc
        return {
            "text": str(payload.get("text") or "").strip()[:500],
            "confidence": max(
                0.0, min(1.0, float(payload.get("confidence") or 0.0))
            ),
        }

    def cancel(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()


speech_recognizer = PushToTalkRecognizer()
