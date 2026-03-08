import sounddevice as sd
import numpy as np
import matplotlib.pyplot as plt
from collections import deque

# Settings
sample_rate = 44100
block_size = 1024
history_length = 500  # how many points shown on graph

volume_history = deque(maxlen=history_length)

# Audio callback
def audio_callback(indata, frames, time, status):
    if status:
        print(status)
    volume = np.linalg.norm(indata)  # loudness
    volume_history.append(volume)
    return audio_callback

# Setup plot
plt.ion()
fig, ax = plt.subplots()
line, = ax.plot(volume_history)
ax.set_ylim(0, 20)
ax.set_title("🎤 Live Voice Loudness")
ax.set_ylabel("Volume")
ax.set_xlabel("Time")

# Start microphone stream
with sd.InputStream(callback=audio_callback,
                    channels=1,
                    samplerate=sample_rate,
                    blocksize=block_size):
    print("🎙 Speak into the microphone (Ctrl+C to stop)")
    while True:
        line.set_ydata(volume_history)
        line.set_xdata(range(len(volume_history)))
        ax.relim()
        ax.autoscale_view()
        plt.pause(0.05)
