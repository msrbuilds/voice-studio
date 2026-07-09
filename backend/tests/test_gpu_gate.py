"""GpuGate: one lock + one worker thread for every GPU consumer.

TTS synthesis and ASR transcription both submit through the gate, so a
transcription can never run concurrently with a synthesis on the GPU.
"""
import inspect
import threading
import time

import pytest

from backend.core.gpu_gate import GpuGate


def test_gate_serializes_concurrent_calls():
    gate = GpuGate(timeout_s=10)
    active = [0]
    max_active = [0]
    lock = threading.Lock()

    def work():
        with lock:
            active[0] += 1
            max_active[0] = max(max_active[0], active[0])
        time.sleep(0.05)
        with lock:
            active[0] -= 1
        return "ok"

    threads = [threading.Thread(target=lambda: gate.run(work)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert max_active[0] == 1, "two GPU jobs overlapped"


def test_gate_propagates_return_value():
    gate = GpuGate(timeout_s=5)
    assert gate.run(lambda a, b: a + b, 2, 3) == 5


def test_gate_propagates_exception():
    gate = GpuGate(timeout_s=5)

    def boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        gate.run(boom)


def test_gate_releases_lock_after_exception():
    """A failed job must not wedge the gate for every later caller."""
    gate = GpuGate(timeout_s=5)

    def boom():
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        gate.run(boom)
    assert gate.run(lambda: "still works") == "still works"


def test_synth_service_gate_param_defaults_to_none():
    """Regression: every existing caller constructs SynthService without a gate."""
    from backend.services.synthesize import SynthService

    sig = inspect.signature(SynthService.__init__)
    assert "gate" in sig.parameters
    assert sig.parameters["gate"].default is None
